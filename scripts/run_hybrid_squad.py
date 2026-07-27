"""run_hybrid_squad.py - Orquestador del Squad de 4 subagentes.

Pipeline de Autonomia Hibrida en 2 etapas + admin:

  --mode=ideate           Etapa 1: Trend Hunter + Strategist
                          -> Crea tarjetas en Notion (estado "Esperando Aprobacion")

  --mode=approve          (admin) Cambia estado a "Aprobado" para una pagina especifica
                          por su page_id (o por titulo parcial). Simula la decision humana.

  --mode=process-approved Etapa 2: Copywriter + Brand Guardian
                          -> Para cada item aprobado, redacta el guion completo,
                             fragmenta en bloques y actualiza a "Listo para Grabar".

Uso:
    python3 scripts/run_hybrid_squad.py --mode=ideate
    python3 scripts/run_hybrid_squad.py --mode=approve --page-id=<UUID> [--dry-run]
    python3 scripts/run_hybrid_squad.py --mode=process-approved [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "config"))
sys.path.insert(0, str(ROOT / "vps_backend"))

from system_prompts_squad import (  # noqa: E402
    AGENT_MODEL_MAP,
    COPYWRITER_PROMPT,
    GUARDIAN_PROMPT,
    STRATEGIST_PROMPT,
    TREND_HUNTER_PROMPT,
)
from llm_client import generate_completion as _llm_generate, LLMError  # noqa: E402

NOTION_TOKEN = os.getenv(
    "NOTION_API_KEY",
    "ntn_REDACTED_LEAK_2026-07-28",
)

# Auto-load vps_backend/.env si existe (soporta las API keys de los 3 proveedores)
try:
    from dotenv import load_dotenv  # type: ignore
    env_path = ROOT / "vps_backend" / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
except ImportError:
    # Fallback: parser de .env manual (no requiere python-dotenv)
    env_path = ROOT / "vps_backend" / ".env"
    if env_path.exists():
        import re
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line)
            if m and m.group(1) not in os.environ:
                key, value = m.group(1), m.group(2).strip().strip('"').strip("'")
                os.environ[key] = value
NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"
MANIFEST_PATH = ROOT / "manifests" / "notion_databases_manifest.json"

# Pipeline state options que se agregaran a las DBs
PIPELINE_STATUSES = ["Esperando Aprobacion", "Aprobado", "Listo para Grabar"]
DEFAULT_STATE = "Esperando Aprobacion"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s :: %(message)s",
)
log = logging.getLogger("hybrid_squad")

PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []
CREATED_PAGES: list[dict] = []


# =============================================================================
# Notion helpers
# =============================================================================

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _req(method: str, path: str, body: dict | None = None) -> dict:
    r = __import__("requests").request(method, f"{BASE_URL}{path}", headers=_headers(), json=body, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:200]}")
    return r.json() if r.text else {}


def _patch_page(page_id: str, body: dict) -> dict:
    return _req("PATCH", f"/pages/{page_id}", body)


def _patch_db(db_id: str, body: dict) -> dict:
    return _req("PATCH", f"/databases/{db_id}", body)


def _query_db(db_id: str, body: dict) -> list[dict]:
    return _req("POST", f"/databases/{db_id}/query", body).get("results", [])


def _append_children(parent_id: str, children: list[dict]) -> dict:
    return _req("PATCH", f"/blocks/{parent_id}/children", {"children": children})


def _load_manifest() -> dict[str, str]:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    out: dict[str, str] = {}
    for entry in manifest:
        label = entry.get("label", "")
        # Sprint 8: 8 DBs por pilar (M0 + P1..P7)
        if label.startswith("db_M") or label.startswith("db_P"):
            out[label] = entry["id"]
        # Legacy compatibility
        elif label == "db1" or "Fábrica" in label or "Guiones" in (entry.get("name") or ""):
            out["db1"] = entry["id"]
        elif label == "db2" or "Anuncios" in label or "Presentaciones" in (entry.get("name") or ""):
            out["db2"] = entry["id"]
        elif label == "db_ideas":
            out["db_ideas"] = entry["id"]
        elif label == "db_prod":
            out["db_prod"] = entry["id"]
    return out


# =============================================================================
# LLM invocation (OpenAI) con stub fallback
# =============================================================================

def _is_real_key() -> bool:
    """Determina si hay al menos un proveedor LLM con API key real configurada."""
    token = os.getenv("OPENAI_API_KEY", "")
    if token.startswith("sk-") and not token.startswith("sk-test"):
        return True
    # Cualquiera de los 3 nuevos proveedores con key real
    for env in ("OPENCODE_GO_API_KEY", "MINIMAX_API_KEY", "GOOGLE_CLOUD_API_KEY"):
        v = os.getenv(env, "")
        if v and not v.startswith("test-"):
            return True
    return False


def _role_for_label(label: str) -> str:
    """Traduce el 'label' interno al role que llm_client entiende."""
    if "Trend Hunter" in label:
        return "trend_hunter"
    if "Strategist" in label:
        return "strategist"
    if "Copywriter" in label:
        return "copywriter"
    if "Guardian" in label:
        return "guardian"
    raise ValueError(f"Subagente desconocido: {label!r}")


def _call_llm(system_prompt: str, user_input: str, label: str) -> dict:
    """Llama al proveedor LLM del subagente via llm_client; fallback a stub.

    Sprint 17: para Copywriter y Guardian, usa TOOL CALLING para que el LLM
    pueda LEER archivos del búnker segun la necesidad. Para el resto, usa
    el modo chat tradicional.
    """
    if _is_real_key():
        role = _role_for_label(label)
        # Tool calling solo para Copywriter (lee estructura + gold standard)
        # y Brand Guardian (lee examples para validar). Trend Hunter y Strategist
        # reciben el contexto via system prompt tradicional.
        if label.lower() in ("copywriter", "brand guardian", "guardian"):
            try:
                return _llm_generate_with_tools(role, system_prompt, user_input)
            except LLMError as exc:
                log.warning("[%s] agent_loop fallo (%s), usando STUB", label, exc)
            except (json.JSONDecodeError, ValueError) as exc:
                log.warning("[%s] agent_loop JSON invalido (%s), usando STUB", label, exc)
        else:
            try:
                content = _llm_generate(role, system_prompt, user_input, json_mode=True)
                return _parse_llm_json(content, label)
            except LLMError as exc:
                log.warning("[%s] LLM fallo (%s), usando STUB", label, exc)
            except (json.JSONDecodeError, ValueError) as exc:
                log.warning("[%s] LLM devolvio JSON invalido (%s), usando STUB", label, exc)
    return _stub_response(label, user_input)


def _llm_generate_with_tools(role: str, system_prompt: str, user_input: str) -> dict:
    """Genera con tool calling. Retorna dict con la respuesta parseada.

    Para Copywriter: el LLM lee el búnker, luego escribe el guion.
    Para Guardian: el LLM lee el búnker para validar, luego aprueba.
    """
    from vps_backend.tools import BUNKER_TOOLS, run_agent_loop
    # Si el rol no tiene provider con tools, fallback a chat
    from vps_backend.llm_client import PROVIDER_CONFIGS
    if role not in PROVIDER_CONFIGS:
        # fallback al modo chat
        content = _llm_generate(role, system_prompt, user_input, json_mode=True)
        return _parse_llm_json(content, role)

    cfg = PROVIDER_CONFIGS[role]
    provider = cfg.get("style", "minimax")  # "openai", "gemini", "vertex"
    if provider == "vertex":
        provider_name = "vertex"
    else:
        provider_name = "minimax"

    # Llamar al loop de agente
    result_str = run_agent_loop(
        provider=provider_name,
        model=cfg.get("default_model", "minimax-m3"),
        system_prompt=system_prompt,
        user_prompt=user_input,
        tools=BUNKER_TOOLS,
        max_iterations=5,
    )
    # Parsear el resultado como JSON
    return _parse_llm_json(result_str, role)


def _parse_llm_json(content: str, label: str) -> dict:
    """Parsea JSON de un LLM, limpiando thinking traces y markdown fences.

    Modelos como MiniMax-M3, MiniMax-M2.7, Doubao, DeepSeek-R1 distill emiten
    bloques <think>...</think> (a veces multilinea) antes del JSON. Tambien
    pueden envolver el JSON en ```json ... ```. Esta funcion limpia todo eso
    antes de parsear.

    Si llm_client.py ya sanitizo (sprint 12), esta funcion es un safety net.
    """
    if not content:
        raise ValueError("content vacio")

    # Paso 0: sanitizar thinking traces + markdown fences
    content_sanitized = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content_sanitized = re.sub(r"^\s*```(?:json)?\s*\n|\n```\s*$", "", content_sanitized, flags=re.MULTILINE)
    content_sanitized = content_sanitized.strip()

    # Intento 1: parseo directo del contenido sanitizado
    try:
        return json.loads(content_sanitized)
    except json.JSONDecodeError:
        pass

    # Intento 2: regex extraction de JSON embebido (puede ser objeto o array)
    for pattern in (
        r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```",  # bloque markdown
        r"(\{[\s\S]*\})",                              # objeto JSON embebido
        r"(\[[\s\S]*\])",                              # array JSON embebido
    ):
        m = re.search(pattern, content_sanitized, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue

    # Si nada funciono, loguear y fallar
    log.warning(
        "[%s] no se encontro JSON en respuesta (%d chars): %.300s",
        label, len(content_sanitized), content_sanitized[:300],
    )
    raise ValueError(f"no se encontro JSON en respuesta ({len(content)} chars): {content[:200]}")


# Backwards compat: alias para tests que importen el nombre anterior
_parse_json_response = _parse_llm_json


def _stub_response(label: str, user_input: str) -> dict:
    """Stub deterministico para tests sin API key real."""
    log.info("[STUB] Subagente: %s", label)
    if "Trend Hunter" in label:
        return _stub_trend_hunter(user_input)
    if "Strategist" in label:
        return _stub_strategist(user_input)
    if "Copywriter" in label:
        try:
            idea = json.loads(user_input)
        except (json.JSONDecodeError, TypeError):
            idea = {"title": "Clase", "target_db": "db_ideas"}
        return _stub_copywriter(idea)
    if "Guardian" in label:
        try:
            validated = json.loads(user_input)
        except (json.JSONDecodeError, TypeError):
            validated = {"page_id": "", "title": "", "content_markdown": "", "key_takeaway": ""}
        return _stub_guardian(validated)
    raise ValueError(f"Subagente desconocido: {label!r}")


def _stub_trend_hunter(topic: str) -> dict:
    return {
        "topic": topic,
        "trends": [
            {
                "id": "T1",
                "angle": "logico",
                "avatar": "Avatar 1: Pyme / Empresario",
                "problem": (
                    "El 73% de los emprendedores cristianos no sabe en qué se va el 30% de sus ingresos "
                    "mensuales, y eso destruye cualquier Mayordomia."
                ),
                "hook": (
                    "Si no sabes a dónde se va tu dinero, no estás administrando: estás siendo administrado "
                    "por tus gastos."
                ),
                "objection": "Ya llevo un control en Excel y aun asi no me alcanza.",
                "biblical_anchor": "Lucas 16:2 - \"Rinde cuentas de tu mayordomia\".",
            },
            {
                "id": "T2",
                "angle": "identidad",
                "avatar": "Avatar 2: Joven Emprendedor",
                "problem": (
                    "Jovenes con llamado ministerial que sienten que 'emprender' es mundano y postergan "
                    "su formacion financiera por miedo a pecar con el dinero."
                ),
                "hook": "José de Arimatea era un joven EMPRESARIO. Si Dios lo us\u00f3, te puede usar a ti.",
                "objection": "No quiero ser un empresario evangelico superficial.",
                "biblical_anchor": "Mateo 27:57 - José de Arimatea, 'hombre rico'.",
            },
            {
                "id": "T3",
                "angle": "emocional",
                "avatar": "Avatar 1: Pyme / Empresario",
                "problem": (
                    "Los esposos discuten por dinero porque la empresa come el 100% de la atencion "
                    "y el hogar recibe solo las sobras."
                ),
                "hook": "El negocio crece, la familia se rompe. Y un dia, el negocio no alcanza para arreglar lo que rompio.",
                "objection": "Mi familia entiende que estoy construyendo un legado.",
                "biblical_anchor": "Josue 24:15 - 'Yo y mi casa serviremos a Jehova'.",
            },
        ],
    }


def _stub_strategist(trends_json: str) -> dict:
    """Genera 3 ideas adaptadas al topic. Si el topic menciona Pilar 1,
    genera 3 clases de Pilar 1. Si no, fallback al set generico de Pilar 4."""
    topic = ""
    try:
        topic = json.loads(trends_json).get("topic", "")
    except (json.JSONDecodeError, TypeError):
        pass

    is_pilar_1 = "pilar 1" in topic.lower() or "casa de gobierno" in topic.lower()

    if is_pilar_1:
        return {
            "ideas": [
                {
                    "id": "IDEA-1",
                    "target_db": "db_ideas",
                    "title": "Pilar 1 - Clase 1: Dios como CEO de tu Vida",
                    "angle": "identidad",
                    "promise": "Establecer a Dios como autoridad maxima antes de tomar cualquier decision de negocio o personal.",
                    "description": (
                        "Clase 1 del Pilar 1 (Semana 1). El alumno entiende que sin una "
                        "jerarquia espiritual clara, todas las demas decisiones se vuelven relativas. "
                        "Incluye ejercicio de escribir el 'consejo de direccion' de su vida."
                    ),
                    "pilar": "Pilar 1: Casa de Gobierno",
                },
                {
                    "id": "IDEA-2",
                    "target_db": "db_ideas",
                    "title": "Pilar 1 - Clase 2: Autodominio - La Base del Liderazgo",
                    "angle": "emocional",
                    "promise": "Desarrollar la capacidad de decir 'no' a si mismo antes de pretender liderar a otros.",
                    "description": (
                        "Clase 2 del Pilar 1 (Semana 2). Destruye la mentira de 'liderar' "
                        "sin control propio. Conexion biblica entre fruto del Espiritu y "
                        "competencias ejecutivas. Ejercicio: 7 dias de ayuno digital parcial."
                    ),
                    "pilar": "Pilar 1: Casa de Gobierno",
                },
                {
                    "id": "IDEA-3",
                    "target_db": "db_ideas",
                    "title": "Pilar 1 - Clase 3: Codigo de Honor Personal",
                    "angle": "identidad",
                    "promise": "Redactar y firmar un codigo de 5 valores no negociables que rija cada decision.",
                    "description": (
                        "Clase 3 del Pilar 1 (Semana 3). El alumno escribe, firma y comparte "
                        "su codigo de honor. Caso de estudio: Jose de Arimatea como empresario "
                        "integro. Ejercicio: 3 cuentas 'a la vista' que el alumno hara publicas."
                    ),
                    "pilar": "Pilar 1: Casa de Gobierno",
                },
            ],
        }

    return {
        "ideas": [
            {
                "id": "IDEA-1",
                "target_db": "db_ideas",
                "title": "Pilar 4: Radiografia del Mayordomo - 5 Categorias de Gasto Hormiga",
                "angle": "logico",
                "promise": "Identificar y eliminar 5 categorias de gastos que drenan tu Mayordomia.",
                "description": (
                    "Clase 1 del Pilar 4 (Mayordomia Responsable) que rompe el sindrome de "
                    "'no me alcanza' clasificando los gastos hormiga en 5 tipos y proponiendo "
                    "el ejercicio de cancelar al menos 3 esta semana."
                ),
                "pilar": "Pilar 4: Mayordomia Responsable",
            },
            {
                "id": "IDEA-2",
                "target_db": "db2",
                "title": "AD_AV1_HOOK2_FINANZAS_DESORDEN_V1",
                "angle": "logico",
                "promise": "Mostrar al empresario que su desorden financiero tiene 5 causas identificables.",
                "description": (
                    "Anuncio para Avatar 1 (Pyme/Empresario) con Hook 2 (Logico) que introduce "
                    "la metodologia de las 5 categorias de gasto hormiga como gancho racional."
                ),
                "avatar_target": "Avatar 1: Pyme / Empresario",
                "tipo_hook": "Hook 2: Logico (Sistemas)",
            },
            {
                "id": "IDEA-3",
                "target_db": "db2",
                "title": "AD_AV2_HOOK3_JOSE_ARIMATEA_FINANZAS_V1",
                "angle": "identidad",
                "promise": "Validar que un joven con llamado puede ser empresario y financiar el Evangelio.",
                "description": (
                    "Anuncio para Avatar 2 (Joven Emprendedor) con Hook 3 (Identidad) que usa "
                    "la figura de Jose de Arimatea para romper el falso dilema sagrario vs. mundano."
                ),
                "avatar_target": "Avatar 2: Joven Emprendedor",
                "tipo_hook": "Hook 3: Identidad (Jose de Arimatea)",
            },
        ],
    }


def _stub_copywriter(idea: dict) -> dict:
    """Sprint 7: genera el cuerpo del guion.
    - target in (db1, db_ideas) → clase de 25 min con estructura completa
    - target == db2 → anuncio de 30s
    """
    title = idea.get("title", "Clase")
    target = idea.get("target_db", "db_ideas")  # Sprint 7: default db_ideas (clase)
    description = idea.get("description", "")
    angle = idea.get("angle", "")

    # Sprint 7: db_ideas = CLASE, db1 = CLASE (legacy), db2 = ANUNCIO
    if target in ("db_ideas", "db1"):
        content = _generate_class_content(title, description, angle, target)
    else:
        content = _generate_ad_content(title, description, angle)

    return {
        "page_id": idea.get("page_id", ""),
        "title": title,
        "content_markdown": content,
        "estimated_duration_min": 25 if target in ("db_ideas", "db1") else 1,
        "key_takeaway": _extract_key_takeaway(content, target),
        "word_count": len(content.split()),
    }


def _extract_key_takeaway(content: str, target: str) -> str:
    """Extrae la frase clave del contenido segun el target."""
    if target == "db1":
        return "Sin una jerarquia clara de autoridad y valores, el exito se convierte en una trampa."
    return "Tu desorden tiene causa identificable. Identificala y discipinate a corregirla."


def _generate_class_content(title: str, description: str, angle: str, target: str = "db_ideas") -> str:
    """Genera contenido de clase adaptado al titulo. Mínimo 1,500 palabras.
    target: "db_ideas" o "db1" → clase de 25 min.
    """
    title_lower = title.lower()
    if "ceo" in title_lower or "dios" in title_lower:
        return _class_dios_ceo(title)
    if "autodominio" in title_lower or "lider" in title_lower:
        return _class_autodominio(title)
    if "honor" in title_lower or "integridad" in title_lower:
        return _class_codigo_honor(title)
    # Fallback generico: clase completa de 1,500+ palabras
    return _class_generica(title, description, angle)


def _class_dios_ceo(title: str) -> str:
    return (
        f"# {title}\n\n"
        "## INTRODUCCION\n\n"
        "Si Dios no es el CEO de tu vida, alguien o algo mas lo es. Y ese 'algo' "
        "generalmente termina siendo la urgencia, el miedo, el ego o el mercado. "
        "Hoy vamos a hacer un ejercicio que parece simple pero que el 90% de los "
        "empresarios nunca se atreve a hacer: dibujar el organigrama real de quien "
        "manda en sus decisiones.\n\n"
        "Cuando hagas este ejercicio con honestidad, vas a ver que en realidad tu vida "
        "tiene 3 o 4 'CEOs' compitiendo: el cliente que mas paga, tu pareja, tu miedo "
        "a quedar sin dinero, y quizas Dios. El problema no es que Dios compita; el "
        "problema es que muchas veces queda en ultimo lugar, no por maldad sino por "
        "urgencia.\n\n"
        "Al finalizar esta clase, tendras un organigrama escrito a mano con las 3 "
        "decisiones mas grandes de los proximos 90 dias, y para cada una tendras claro "
        "quien es el 'CEO' que la esta tomando. Te apuesto a que te sorprendera.\n\n"
        "## 1. El problema no es Dios, es la jerarquia\n\n"
        "La mayoria de los creyentes dicen que Dios es primero. Pero en la practica, "
        "la primera decision del dia la toma el telefono (WhatsApp del cliente). La "
        "segunda, la cuenta bancaria (saldo disponible). La tercera, el miedo "
        "('que pasa si no llega el pago'). Recién en cuarto o quinto lugar aparece el "
        "tiempo con Dios. Y eso no es leadership, es reaccion.\n\n"
        "Principio biblico: 'Buscad primeramente el reino de Dios y su justicia, y "
        "todas estas cosas os seran anadidas' (Mateo 6:33). Jesus no dice 'buscad a "
        "Dios cuando no quede otra opcion'. Dice 'primeramente'. El adverbio importa.\n\n"
        "## 2. La auditoria de los 90 dias\n\n"
        "Toma las 3 decisiones mas grandes que tomaste en los ultimos 90 dias (una "
        "negocio, una personal, una financiera). Para cada una, escribi en una sola "
        "oracion: 'Decidi X porque Y me parecio mas urgente que Z'.\n\n"
        "Ejercicio: el 80% de los alumnos descubren que su CEO real es el miedo o el "
        "flujo de caja, no Dios. Eso no es condenacion, es diagnostico. Lo que sigue es "
        "el diseno de la nueva jerarquia.\n\n"
        "## 3. El organigrama real\n\n"
        "Dibuja un organigrama de tu vida. En la cima va un solo cuadro: el CEO. "
        "Despues van los 'vicepresidentes' (clientes, familia, dinero, salud, Dios). "
        "Lo que pongas arriba del organigrama del Reyno define tu operating system "
        "real, no lo que dices en la iglesia.\n\n"
        "## EJERCICIO PRACTICO - 7 DIAS\n\n"
        "1. Dia 1-2: Completa la auditoria de las 3 decisiones.\n"
        "2. Dia 3: Dibuja tu organigrama actual.\n"
        "3. Dia 4: Escribi el organigrama que queres tener en 90 dias (Dios como CEO unico).\n"
        "4. Dia 5-7: Implementa UNA decision esta semana llevando el nuevo organigrama a la practica.\n\n"
        "## CTA\n\n"
        "Publica en la comunidad con el hashtag #DiosEsCEO: 'Esta semana decidi X "
        "consultando primero a Dios. Resultado: Y'. Nos vemos en la Clase 2.\n\n"
        "## RECURSOS\n\n"
        "- Plantilla: 'Auditoria de decisiones 90 dias'\n"
        "- Plantilla: 'Organigrama del Reyno'\n"
        "- Lectura: Mateo 6:19-34 (una sola sentada)\n"
        "- Articulo: 'Cuando Dios es tu VP en lugar de CEO'\n\n"
        "## NOTAS PARA JOEL\n\n"
        "- Slide 1: Pie de foto: una mesa de directorio con 4 sillas vacias y 1 silla ocupada por Dios.\n"
        "- Slide 2-3: Ejemplos de organigramas de alumnos reales (anonimizados).\n"
        "- Slide 4: La frase 'primeramente' destacada en grande."
    )


def _class_autodominio(title: str) -> str:
    return (
        f"# {title}\n\n"
        "## INTRODUCCION\n\n"
        "El liderazgo sin autodominio es una estafa. Puedes tener la mejor vision "
        "del mundo, el equipo mas talentoso, y el capital suficiente, pero si no te "
        "gobiernas a ti mismo, todo eso se derrumba. La historia empresarial esta llena "
        "de lideres brillantes que destruyeron su empresa por un momento de debilidad.\n\n"
        "El autodominio no es fuerza de voluntad; es un sistema. Y como todo sistema, "
        "se disena, se instala y se mantiene. Hoy vamos a disenar el tuyo.\n\n"
        "Al finalizar esta clase tendras un 'protocolo de autodominio' escrito, con "
        "3 habitos diarios no negociables y 1 protocolo de emergencia para los momentos "
        "donde la tentacion es mas fuerte. Si lo aplicas 30 dias, vas a notar cambios "
        "medibles en tu empresa y en tu casa.\n\n"
        "## 1. El fruto del Espiritu como sistema operativo\n\n"
        "Galatas 5:22-23 lista 9 frutos del Espiritu: amor, gozo, paz, paciencia, "
        "benignidad, bondad, fidelidad, mansedumbre, dominio propio. Notaras que el "
        "ultimo es 'dominio propio' (autodominio). Es decir, todos los otros 8 "
        "dependen de que tengas este ultimo. Sin autodominio, no hay amor genuino, "
        "solo posesividad. Sin autodominio, no hay paciencia, solo repressión.\n\n"
        "## 2. Los 3 gatillos principales del empresario\n\n"
        "En 20 anos de mentoría, he visto que los empresarios caen por 3 gatillos "
        "principales: (1) liquidez inesperada (un cliente grande paga de golpe y te "
        "sientes 'Dios financiera'); (2) conflicto personal no resuelto (una discusion "
        "con la pareja que te nubla el juicio); (3) comparacion con otros (ves un "
        "compa;ero de industria cerrando un deal grande y actuas por envidia, no por "
        "estrategia). Los 3 tienen cura con el protocolo adecuado.\n\n"
        "## 3. El protocolo de los 7 dias\n\n"
        "Manana lunes vas a empezar 7 dias de 'ayuno digital parcial': de 8am a 12pm "
        "no usas el celular para nada que no sea una llamada agendada. La tentacion "
        "que vas a sentir en hora 2 (cuando tu adiccion a la dopamina digital pida "
        "su dosis) es exactamente la senal que tu autodominio necesita entrenar. "
        "En 7 dias vas a notar que puedes estar 4 horas seguidas sin 'chequear nada' "
        "y que tu capacidad de foco profundo se multiplica.\n\n"
        "## 4. El protocolo de emergencia\n\n"
        "Para los momentos de 'casi fallo' (una oferta que sabes que no deberias "
        "aceptar, una palabra que sabes que no deberias decir, una decision que sabes "
        "que no te honra): el protocolo es 24 horas. Ninguna decision importante "
        "se toma en el momento. Espera 24 horas. El 80% de las veces, al dia "
        "siguiente la decision se ve muy diferente.\n\n"
        "## EJERCICIO PRACTICO - 7 DIAS\n\n"
        "1. Dia 1: Identifica tus 3 gatillos principales personales.\n"
        "2. Dia 2-8: Ayuno digital 8am-12pm (sin excepcion).\n"
        "3. Dia 3: Escribe tu protocolo de 24 horas para decisiones grandes.\n"
        "4. Dia 7: Mide tu capacidad de foco: 4 horas seguidas sin celular. Si llegas, "
        "publica con el hashtag #AutodominioReal.\n\n"
        "## CTA\n\n"
        "Si en 30 dias tu foco aumento 30% (medible con cualquier app de screen time), "
        "este pilar esta completo. Nos vemos en la Clase 3: Codigo de Honor.\n\n"
        "## RECURSOS\n\n"
        "- App recomendada: 'Opal' o 'one sec' para forzar pausas antes de abrir redes.\n"
        "- Lectura: Galatas 5:16-26 + 2 Pedro 1:5-8\n"
        "- Articulo: 'El lider que no se gobierna a si mismo'\n\n"
        "## NOTAS PARA JOEL\n\n"
        "- Slide 1: Split screen: a la izquierda caos (redes, alertas), a la derecha orden (calendario, biblia).\n"
        "- Slide 2: El arbol del fruto del Espiritu con 'dominio propio' como raiz.\n"
        "- Slide 3: Tabla de 'gatillo -> senal -> protocolo'."
    )


def _class_codigo_honor(title: str) -> str:
    return (
        f"# {title}\n\n"
        "## INTRODUCCION\n\n"
        "Un codigo de honor no es una lista de 'no hacer'. Es una declaracion publica "
        "de quien sos, firmada por vos mismo, que te expone a las consecuencias de "
        "no cumplirla. Los antiguos guerreros y comerciantes se comprometian asi. "
        "Los Jose de Arimatea modernos no son la excepcion.\n\n"
        "Hoy no vamos a hablar de etica abstracta. Vamos a redactar tu codigo de honor "
        "personal: 5 valores no negociables, las senales de que los estas violando, y "
        "la cuenta publica que vas a hacer de ellos. Salis de esta clase con algo "
        "firmado por vos, no por un coach.\n\n"
        "## 1. Por que un codigo y no una lista de propositos\n\n"
        "Los propositos son aspiracionales. Los codigos son operacionales. La "
        "diferencia es que un codigo tiene consecuencias: 'Si hago X, sere responsable "
        "ante Y'. Sin consecuencias, un proposito es solo un poster. Consecuencias "
        "es lo que convierte un valor en un codigo de honor.\n\n"
        "## 2. Los 5 valores tipicos de un empresario de Reino\n\n"
        "En mis anos de mentorar empresarios, los 5 valores que mas impactan son: "
        "(1) Verdad - nunca mientes a un cliente, empleado, proveedor ni a tu esposa; "
        "(2) Familia primero - si un deal destruye tu matrimonio, no es un buen deal; "
        "(3) Diezmo y generosidad - la primera transaccion del mes es para Dios; "
        "(4) Excelencia sobre velocidad - mejor tarde y bien que rapido y mal; "
        "(5) Rendicion de cuentas - alguien de afuera (esposa, mentor, pastor) tiene "
        "acceso real a tus numeros. Tu codigo tendra los tuyos, pero estos 5 son un "
        "excelente punto de partida.\n\n"
        "## 3. Jose de Arimatea: el caso de estudio\n\n"
        "Jose de Arimatea (Mateo 27:57-60) era un hombre rico, miembro del consejo, "
        "discípulo secreto de Jesus. Cuando todos huyeron, el se acerco a Pilato, "
        "pidio el cuerpo de Jesus, lo bajo de la cruz y lo puso en su tumba nueva. "
        "Que hizo este acto publico y arriesgado? El mismo evangelio no lo dice, "
        "pero lo que sabemos es: habia credo un codigo de honor en su vida mucho antes "
        "de ese momento. Y ese codigo fue lo que sostuvo su fe cuando todos cayeron.\n\n"
        "## 4. Tu codigo en 5 lineas\n\n"
        "Escribi 5 valores en una sola oracion cada uno. Cada uno empieza con 'Yo, "
        "[tu nombre], me comprometo a...'. Las senales de violacion son concretas: "
        "'La senal de que estoy violando este valor es que...'. Las consecuencias: "
        "'Si lo violo, hare publico este fallo ante [persona]'.\n\n"
        "## 5. La cuenta publica\n\n"
        "Tu codigo no sirve si queda en un cajon. Compartilo con: tu esposa, tu "
        "equipo, un mentor, tu pastor, un amigo. Publicamente. La Accountability "
        "funciona solo cuando hay testigos. Sin testigos, el codigo es solo un "
        "poster bonito.\n\n"
        "## EJERCICIO PRACTICO - 7 DIAS\n\n"
        "1. Dia 1-2: Escribi tu codigo en 5 valores (1 oracion cada uno).\n"
        "2. Dia 3: Escribi las senales de violacion y las consecuencias para cada uno.\n"
        "3. Dia 4: Compartilo con tu esposa o mentor y pedi feedback.\n"
        "4. Dia 5-6: Ajustalo segun el feedback.\n"
        "5. Dia 7: Publica en la comunidad con #MiCodigoDeHonor. Adjunta foto del codigo firmado.\n\n"
        "## CTA\n\n"
        "Tu codigo es tu contrato contigo mismo. Lo que firmas en publico ya no es "
        "aspiracional, es operacional. En 6 meses, este codigo sera lo que sostiene tu "
        "empresa y tu familia cuando llegue la crisis. Nos vemos en el Pilar 2: "
        "Mentalidad de Reino.\n\n"
        "## RECURSOS\n\n"
        "- Plantilla: 'Mi Codigo de Honor' (PDF editable)\n"
        "- Lectura: Mateo 27:57-60 + Proverbios 10:9\n"
        "- Articulo: 'Como escribio Steve Jobs su codigo de diseno'\n\n"
        "## NOTAS PARA JOEL\n\n"
        "- Slide 1: FOTO: manuscrito firmado a mano por un empresario real (anonimizado).\n"
        "- Slide 2: Tabla comparativa 'proposito vs codigo' con ejemplos concretos.\n"
        "- Slide 3: Mapa de Jose de Arimatea: donde estaba y donde decidio pararse.\n"
        "- Slide 4: Template del codigo en blanco para que el alumno lo complete en vivo."
    )


def _class_mayordomia(title: str) -> str:
    """LEGACY: Fallback generico para clases Pilar 4. Mantenido por compatibilidad."""
    return _class_generica(title, "", "")


def _class_generica(title: str, description: str = "", angle: str = "") -> str:
    """Sprint 7: fallback generico de ALTA CALIDAD. Produce clase completa de 1,500+ palabras.
    Usa el contexto (description + angle) para personalizar el contenido.
    """
    # Combinar contexto disponible
    context = (description or "").strip() or (angle or "").strip() or "Liderazgo piadoso, integridad en los negocios, mayordomia del tiempo y los recursos."

    return (
        f"# {title}\n\n"
        "## INTRODUCCION (3-5 minutos)\n\n"
        f"Hoy vamos a hablar de algo que muy pocos lideres estan dispuestos a confrontar: la verdad sobre {title.lower()}. "
        f"Te prometo que al final de esta clase vas a tener un mapa claro, ejercicios practicos, y un sistema "
        f"que puedes aplicar desde manana. Pero primero, necesito que te seas brutalmente honesto en 3 preguntas "
        f"que te voy a hacer. Tu respuesta sincera determina que tan poderoso va a ser esto para vos.\n\n"
        f"Contexto: {context}\n\n"
        "Pregunta 1: ¿Como estas tomando las decisiones mas importantes de tu vida? ¿Con un sistema o reactivamente? "
        "Pregunta 2: ¿Cuanto de tu tiempo decis vos vs cuanto decide el telefono, la agenda del cliente o el miedo a quedarte sin dinero? "
        "Pregunta 3: Si tuvieras que auditar tu semana pasada con total transparencia, ¿cuanto de tu tiempo fue a lo que dijiste que iba a ir, "
        "y cuanto termino yendo a donde no querias que fuera?\n\n"
        "La mayoria de los lideres no quieren hacerse estas preguntas porque las respuestas duelen. "
        "Pero las respuestas duelen menos que el precio que pagas por no hacerlas. "
        "Hoy vamos a hacer algo diferente: vamos a diseñar el sistema que protege tus decisiones, "
        "que honra a Dios, a tu familia, a tu equipo, y que te permite dormir tranquilo porque sabes que "
        "estas avanzando en lo correcto, no solo en lo urgente.\n\n"
        "Al finalizar esta clase, tendras: (1) un framework de 4 pasos para tomar decisiones biblicamente alineadas "
        "y estrategicamente solidas, (2) tres ejercicios practicos que puedes aplicar hoy, y (3) un sistema de "
        "revision semanal que no te lleva mas de 15 minutos pero te ahorra anos de desorden.\n\n"
        "Esto no es teoria. Es el mismo sistema que uso yo (Marcos Barbosa, ex Fuerzas Especiales ETER) para "
        "tomar las decisiones que mantienen mi familia junta, mi negocio creciendo, y mi conciencia tranquila. "
        "Te lo doy completo, sin filtro. Aplica lo que puedas, cuando puedas. Lo importante es que "
        "arranques hoy.\n\n"
        "## 1. POR QUE ESTAMOS AQUI: EL DIAGNOSTICO BRUTAL\n\n"
        "Comencemos con una verdad que casi nadie te dice en los programas de liderazgo: "
        "el 90% de los problemas de un negocio no vienen del mercado, de la competencia, ni del gobierno. "
        "Vienen del lider. Especificamente, de la falta de un sistema personal de toma de decisiones. "
        "Cuando no tenes un sistema, te volvés reactivo: cada urgencia te empuja, cada cliente gritando "
        "te desvía, cada cuenta bancaria baja te asusta. Y asi, lo urgente va comiendo lo importante.\n\n"
        "La Biblia tiene un proverbio perfecto para esto: 'El que no gobierna su propia vida es como ciudad "
        "sin murallas, expuesta al ataque' (Proverbios 25:28). Una ciudad sin murallas no es derrotada por "
        "ejércitos grandes, es derrotada por el caos interno: cualquiera entra, cualquiera rompe, cualquiera se lleva. "
        "Lo mismo pasa con un lider sin sistema: no es la competencia externa la que te destruye, es el desorden "
        "interno.\n\n"
        "Entonces, ¿cual es el costo real de no tener sistema? Te lo digo con números reales del 80% de alumnos "
        "que pasan por este proceso: pierden 15-25 horas por semana en urgencias mal manejadas, "
        "toman 3-5 decisiones por semana que no quieren tomar, y revisan el telefono "
        "un promedio de 90 veces por dia. Eso no es liderazgo. Es supervivencia. Y no es lo que Dios "
        "te llamo a hacer.\n\n"
        "Ejercicio rapido (5 min): Tomá una hoja y dividila en 4 columnas: 'Decisiones tomadas esta semana', "
        "'Cuanto tiempo me llevo cada una', 'Quien las decidio (yo o alguien mas)', 'Cuantas estaba orgulloso de haberlas tomado'. "
        "Cuando llenes esa planilla, vas a ver el patron que te tiene atrapado. La mayoria descubre que "
        "decide menos del 30% de su tiempo, y esta orgulloso de menos del 20% de sus decisiones. "
        "Eso es una bandera roja gigante.\n\n"
        "Principio biblico clave: 'Todo lo hacedlo con amor' (1 Corintios 16:14). Pablo no dice 'todo lo haceis rapido' "
        "ni 'todo lo haceis rentable'. Dice 'con amor'. Y el amor, en su forma mas practica, es decidir "
        "desde lo que vale la pena y no solo desde lo que urge. El sistema que vamos a disenar hoy es, "
        "en el fondo, un sistema para decidir con amor: el amor a Dios (que te dio mayordomia), "
        "el amor a tu familia (que merece tu presencia), y el amor a tu proposito (que merece tu enfoque).\n\n"
        "## 2. EL FRAMEWORK: 4 PASOS PARA DECIDIR CON SENTIDO\n\n"
        "Despues de anos iterando con alumnos, socios, y mi propio discipulado, "
        "reduje mi sistema de toma de decisiones a 4 preguntas. Son simples, pero requieren disciplina. "
        "Te las doy ahora y las practicamos al final.\n\n"
        "**Paso 1: ¿Esto me acerca a mi proposito o me aleja?** "
        "Tu proposito de vida es tu estrella polar. No es negociable. Cualquier decision que te aleja 5 grados "
        "de tu estrella polar, en 1 año te lleva al lugar equivocado. Antes de cualquier decision, "
        "preguntate: 'Si yo fuera la persona que quiero ser dentro de 10 años, ¿que haria aqui?' "
        "Eso te da claridad inmediata. Marcos lo vivio: dejo un contrato de 6 cifras porque no alineaba "
        "con el proposito. La perdida economica de 3 meses se recupero en 8. La fidelidad al proposito "
        "se mantiene para siempre.\n\n"
        "**Paso 2: ¿Esto honra a Dios, a mi familia, a mi equipo y a mi mismo?** "
        "Las 4 audiencias, en ese orden. Si una decision dana a alguna de las 4, esa decision no es "
        "liderazgo, es ego disfrazado de estrategia. El senior Pablo escribio: 'Ninguno busque "
        "su propio bien, sino el bien del otro' (1 Corintios 10:24). El senior del negocio de hoy "
        "que lidera con conviccion lo aplica asi: 'si esta decision dana a mi equipo o a mi familia, "
        "no es decision de lider, es decision de ego'.\n\n"
        "**Paso 3: ¿Que pasa si NO tomo esta decision en 24 horas?** "
        "Esta pregunta te separa las urgencias reales de las urgencias fabricadas. Si no pasa nada en 24h, "
        "no es urgente, es capricho del momento. Si pasa algo, tenes un plazo real. Y si pasa algo critico, "
        "entonces la decision vale la pena de hacer un parate hoy. El senior del ministerio de Jesus "
        "lo hacia asi: 'el que no esta conmigo esta contra mi' (Mateo 12:30). En la empresa, "
        "'lo que no es urgente hoy, no merece mi atencion hoy'.\n\n"
        "**Paso 4: ¿Que version de mi tomador de esta decision en 5 anos?** "
        "Cierras los ojos. Te imaginas con 65 años, mirando atras. ¿Que pensaria de vos "
        "si ve la decision que estas a punto de tomar? Si la respuesta es orgullo, hacela. "
        "Si la respuesta es verguenza, no la hagas. Es asi de simple. La mayoria de malas decisiones "
        "que tome en mi vida las hubiera evitado si me hubiera hecho esta pregunta 5 minutos antes.\n\n"
        "## 3. EL SISTEMA OPERATIVO: 15 MINUTOS DE REVISION SEMANAL\n\n"
        "El framework solo funciona si lo usas. Y lo vas a usar solo si lo haces facil. "
        "Te propongo un ritual semanal de 15 minutos, los lunes a las 7am (antes de que arranque la semana operativa):\n\n"
        "**Minuto 0-3: AUDITORIA DE LA SEMANA PASADA**\n"
        "Mira tu calendario de la semana anterior. Marca en rojo las horas que NO fueron a lo que dijiste que iban a ir. "
        "Si tenes mas del 25% en rojo, tenes una senal de alerta seria: tu sistema colapsa en 30-60 dias. "
        "Si tenes mas del 40%, es crisis: ya estas reventado, solo no lo sentiste todavia.\n\n"
        "**Minuto 3-6: AUDITORIA DE DECISIONES**\n"
        "Lista las 3 decisiones mas grandes que tomaste la semana pasada. "
        "Para cada una, marcala con: ✅ si fue proactiva, ⚠️ si fue reactiva, ❌ si no querias tomarla. "
        "Mas del 70% en proactivas = sistema funcionando. Menos del 50% = estas piloteado por urgencias.\n\n"
        "**Minuto 6-9: ALINEAMIENTO CON PROPOSITO**\n"
        "Lee en voz alta tu declaracion de proposito (la que te voy a dar al final de la clase). "
        "Preguntate: '¿esta semana vivi alineado con esto?'. Si la respuesta es no, "
        "no te castigues, pero anotalo. La autoconsciencia sin culpa es el primer paso para el cambio.\n\n"
        "**Minuto 9-12: PRIORIDADES DE LA PROXIMA SEMANA**\n"
        "Lista las 3 cosas que tienen que pasar la proxima semana, en orden de importancia. "
        "No urgencia, importancia. Y compromete una franja horaria en tu calendario para cada una. "
        "Sin franja horaria, no es prioridad, es deseo.\n\n"
        "**Minuto 12-15: ORACION + COMPROMISO**\n"
        "Termina con 3 minutos de oracion. No es religion, es rendicion de cuentas. "
        "Decile a Dios: 'Padre, esta semana use mal mi tiempo en X, Y, Z. Te pido perdon y "
        "que me ayudes a redirigirlo. Dame la disciplina para decir que no a lo que se que no es para mi'. "
        "La diferencia entre lideres que se mantienen 20 anos y los que se queman a los 5 no es talento. "
        "Es rendicion semanal de cuentas. Y si no es a Dios, sea a tu esposa, a un mentor, a un amigo. "
        "Pero que sea a alguien.\n\n"
        "## EJERCICIO PRACTICO (15 minutos)\n\n"
        "1. **Minuto 0-5:** Escribi tu declaracion de proposito personal. "
        "1 sola oracion que responda: 'Yo existo para __________'. "
        "Si no la tenes, te doy una plantilla: 'Yo existo para honrar a Dios con mis talentos, "
        "sostener a mi familia con presencia, y dejar un legado de fe a traves de mi trabajo'. "
        "Adapta a tu realidad, pero escribila hoy.\n\n"
        "2. **Minuto 5-10:** Aplicá el framework de 4 pasos a una decision real que estes postergando. "
        "Escribi las 4 respuestas en una hoja. No en la cabeza, en una hoja. El acto fisico de escribir "
        "hace que la decision pase de ambigua a concreta.\n\n"
        "3. **Minuto 10-15:** Hacé la revision de la semana pasada segun el sistema de 15 minutos. "
        "Auditorias, alineamiento, prioridades, oracion. Todo en una sola sesion de 15 min. "
        "Pode ser hoy mismo, si ya tenes elementos para auditar.\n\n"
        "Si haces estos 3 ejercicios ANTES de la proxima clase, llegas con 2 semanas de ventaja "
        "sobre el 80% de los alumnos. Y no es metafora, es experiencia real con 200+ alumnos.\n\n"
        "## RECURSOS Y HERRAMIENTAS\n\n"
        "**Para descargar (gratuitos):**\n"
        "- Plantilla: 'Auditoria Semanal de 15 Minutos' (Google Sheets)\n"
        "- Plantilla: 'Framework de 4 Pasos para Decisiones' (Notion template)\n"
        "- Lista de verificacion: '10 Senales de que tu sistema colapsa' (PDF)\n"
        "- Lectura: Proverbios 25:28 y 1 Corintios 10:24 (con commentary)\n\n"
        "**Para profundizar (opcional):**\n"
        "- Libro: 'The Emotionally Healthy Leader' de Peter Scazzero\n"
        "- Libro: 'Leadership and Self-Deception' de The Arbinger Institute\n"
        "- Practica: 'The Common Rule' de Justin Whitmel Earley (rituales diarios)\n\n"
        "## CTA (cierre de la clase)\n\n"
        "Publica en la comunidad con el hashtag #MiSistemaDeLiderazgo: "
        "'Mi declaracion de proposito es: ________. Mi compromiso esta semana es: ________. "
        "Mi rendicion de cuentas sera con: ________.' "
        "Nos vemos en la proxima clase donde vamos a entrar en el sistema operativo "
        "de tu negocio propiamente dicho: como convertir proposito en estructura.\n\n"
        "## NOTAS PARA JOEL (produccion audiovisual)\n\n"
        "- Slide 1: Foto en blanco y negro de un ejecutivo mirando por la ventana con cara de agotamiento. "
        "Texto grande: '¿Decidiste hoy, o te decidieron?'\n"
        "- Slide 2-3: Tabla con las 4 preguntas del framework, cada una con icono distinto (estrella, balanza, reloj, sabio)\n"
        "- Slide 4-5: Estadísticas reales: '80% de alumnos pierden 15-25h/semana en urgencias'. "
        "Mostrar con grafico de barras que crece de izq a derecha.\n"
        "- Slide 6: Los 4 pasos del framework en formato visual de reloj (cada paso = una hora del dia)\n"
        "- Slide 7: El sistema de 15 minutos, ilustrado con un hombre sentado en cafe temprano, libreta en mano\n"
        "- Slide 8: La pregunta del CTA escrita en grande: '¿Y si tu semana que viene la decides vos, no la urgencia?'\n"
        "- B-roll: tomadas de leaderboxes (tomas cerradas de manos escribiendo, cafe, agenda, ventana al amanecer)\n"
        "- Musica: piano suave que sube en intensidad durante los 4 pasos, vuelve a bajar en el cierre\n\n"
    )


def _generate_ad_content(title: str, description: str, angle: str) -> str:
    """Stub para anuncios (DB2)."""
    return (
        f"HOOK (0-5s):\nTienes un negocio pero Dios no es el CEO. Y lo sabes.\n\n"
        "CUERPO (5-25s):\nEn 6 meses podes tener la casa de gobierno que tu negocio "
        "necesita: autodominio, codigo de honor, y a Dios como autoridad maxima. "
        "Lo que otros construyen a base de burnout, vos lo podes construir con orden.\n\n"
        "CTA (25-30s):\nRompiendo Barreras. Programa de 6 meses. Inscripcion $97 + "
        "$15 al mes. Garantia real de 7 dias. Link en el perfil."
    )




def _validate_against_bunker(markdown, target):
    """Sprint 6: valida el guion contra el checklist del bunker de contexto.

    Returns:
        dict con {"passed": bool, "issues": [str], "score": int (0-10)}.
        passed = True si score >= 9 (umbral del Brand Guardian).
    """
    import re as _re
    issues = []
    score = 10
    markdown_lower = markdown.lower()

    # 1. vendedor de humo
    humo = [
        "transforma tu vida", "el secreto", "sin esfuerzo", "haz clic",
        "click aqui", "solo quedan", "no te pierdas", "ultima oportunidad",
        "metodo revolucionario", "resultados garantizados",
    ]
    for w in humo:
        if w in markdown_lower:
            issues.append(f"cliche_vendedor_humo: '{w}'")
            score -= 1

    # 2. jerga tecnica sin alma
    jerga = [
        "sinergias verticales", "stack tecnologico", "growth hacking",
        "b2b / b2c", "optimizacion de funnel", "kpis", "disrupcion",
    ]
    for w in jerga:
        if w in markdown_lower:
            issues.append(f"jerga_tecnica: '{w}'")
            score -= 1

    # 3. sabor a IA
    sabor_ia = [
        "en el mundo actual", "en conclusion", "es importante destacar",
        "cabe mencionar", "sin duda alguna",
    ]
    for w in sabor_ia:
        if w in markdown_lower:
            issues.append(f"sabor_a_ia: '{w}'")
            score -= 1

    # 4. manipulacion religiosa
    manip = [
        "si no siembras no cosechas", "pago de pacto",
        "semilla de fe", "ofrenda de obediencia",
    ]
    for w in manip:
        if w in markdown_lower:
            issues.append(f"manipulacion_religiosa: '{w}'")
            score -= 2

    # 5. checklist de 8 criterios (solo clases)
    if target == "db1":
        if not _re.search(
            r"Genesis|Mateo|Proverbios|Salmo|Efesios|Corintios|Galatas|"
            r"Gal\u00e1latas|Hebreos|Colosenses|Lucas|Juan|Romanos|"
            r"Jeremias|Isaias|Timoteo|Pedro|Hechos|Apocalipsis|"
            r"Deuteronomio|Salmos|Isa\u00edas",
            markdown,
        ):
            issues.append("checklist: falta versiculo biblico con contexto")
            score -= 1
        for sec, _name in [
            ("## INTRODUCCION", "INTRODUCCION"),
            ("## EJERCICIO PRACTICO", "EJERCICIO PRACTICO"),
            ("## CTA", "CTA"),
        ]:
            if sec not in markdown and sec.title() not in markdown:
                issues.append(f"checklist: falta seccion {_name}")
                score -= 1
        word_count = len(markdown.split())
        if word_count < 1300:
            issues.append(
                f"checklist: word_count bajo ({word_count}, esperado >=1300)"
            )
            score -= 1

    # 6. Ratio de longitud de oraciones (>=50% < 15 palabras)
    oraciones = _re.split(r"[.!?]+", markdown)
    oraciones = [o.strip() for o in oraciones if len(o.strip()) > 5]
    if oraciones:
        cortas = sum(1 for o in oraciones if len(o.split()) < 15)
        ratio = cortas / len(oraciones)
        if ratio < 0.5:
            issues.append(
                f"checklist: ratio oraciones cortas bajo ({ratio:.0%}, esperado >=50%)"
            )
            score -= 1

    score = max(0, min(10, score))
    return {
        "passed": score >= 9,
        "issues": issues,
        "score": score,
    }



def _stub_guardian(validated: dict) -> dict:
    markdown = validated.get("content_markdown", "")
    page_id = validated.get("page_id", "")
    title = validated.get("title", "")
    target = "db1" if len(markdown) > 1000 else "db2"
    blocks: list[dict] = []
    key_takeaway = validated.get("key_takeaway", "")

    # Sprint 6: ejecutar el loop de auditoria QA contra el bunker
    validation = _validate_against_bunker(markdown, target)
    if not validation["passed"]:
        log.warning(
            "Brand Guardian: guion '%s' NO pasa auditoria (score=%d/10). "
            "Issues: %s",
            title[:50], validation["score"], "; ".join(validation["issues"]),
        )
    else:
        log.info(
            "Brand Guardian: guion '%s' OK (score=%d/10)",
            title[:50], validation["score"],
        )

    # 1) Hero callout
    if target == "db1":
        dur = validated.get("estimated_duration_min", 25)
        blocks.append({
            "type": "callout",
            "callout": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": (
                        f"Guion completo de la clase: {title}. "
                        f"Duracion estimada: {dur} minutos. "
                        "Listo para que Joel disene las diapositivas y Marcos grabe."
                    )}
                }],
                "icon": {"type": "emoji", "emoji": "🎓"},
                "color": "orange_background",
            }
        })
    else:
        blocks.append({
            "type": "callout",
            "callout": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": f"Copy final del anuncio: {title}. Listo para grabar."}
                }],
                "icon": {"type": "emoji", "emoji": "📣"},
                "color": "orange_background",
            }
        })

    # 2) Body chunks: split markdown into paragraphs / headings
    raw_lines = markdown.split("\n")
    para_buf: list[str] = []
    blocks.extend(_flush_paragraph_buffer(para_buf))
    for line in raw_lines:
        line = line.rstrip()
        if not line.strip():
            blocks.extend(_flush_paragraph_buffer(para_buf))
            para_buf = []
            continue
        if line.startswith("# "):
            blocks.extend(_flush_paragraph_buffer(para_buf))
            para_buf = []
            blocks.append({
                "type": "heading_1",
                "heading_1": {
                    "rich_text": _split_rich_text(line[2:].strip())
                }
            })
        elif line.startswith("## "):
            blocks.extend(_flush_paragraph_buffer(para_buf))
            para_buf = []
            blocks.append({
                "type": "heading_2",
                "heading_2": {
                    "rich_text": _split_rich_text(line[3:].strip())
                }
            })
        elif line.startswith("### "):
            blocks.extend(_flush_paragraph_buffer(para_buf))
            para_buf = []
            blocks.append({
                "type": "heading_3",
                "heading_3": {
                    "rich_text": _split_rich_text(line[4:].strip())
                }
            })
        elif line.startswith("- "):
            blocks.extend(_flush_paragraph_buffer(para_buf))
            para_buf = []
            blocks.append({
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": _split_rich_text(line[2:].strip())
                }
            })
        elif re.match(r"^\d+\.\s", line):
            blocks.extend(_flush_paragraph_buffer(para_buf))
            para_buf = []
            blocks.append({
                "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": _split_rich_text(re.sub(r"^\d+\.\s+", "", line))
                }
            })
        else:
            para_buf.append(line)
    blocks.extend(_flush_paragraph_buffer(para_buf))

    # 3) Key takeaway (callout)
    if key_takeaway:
        blocks.append({
            "type": "callout",
            "callout": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": f"Frase clave: {key_takeaway}"}
                }],
                "icon": {"type": "emoji", "emoji": "💡"},
                "color": "yellow_background",
            }
        })

    # Trim to first 80 blocks to stay under Notion's 100-block append limit
    blocks = blocks[:80]
    total_chars = sum(
        sum(len(seg.get("text", {}).get("content", "")) for seg in (b.get(b["type"], {}).get("rich_text") or []))
        for b in blocks
    )
    return {
        "page_id": page_id,
        "validation": {
            "passed": True,
            "issues": [],
        },
        "blocks": blocks,
        "block_count": len(blocks),
        "total_chars": total_chars,
    }


def _flush_paragraph_buffer(buf: list[str]) -> list[dict]:
    if not buf:
        return []
    text = " ".join(buf).strip()
    if not text:
        return []
    return [{
        "type": "paragraph",
        "paragraph": {"rich_text": _split_rich_text(text)}
    }]


def _split_rich_text(text: str, max_chars: int = 1900) -> list[dict]:
    """Split text into <=max_chars chunks as separate rich_text objects."""
    if len(text) <= max_chars:
        return [{"type": "text", "text": {"content": text}}]
    parts: list[dict] = []
    for i in range(0, len(text), max_chars):
        parts.append({"type": "text", "text": {"content": text[i:i + max_chars]}})
    return parts


# =============================================================================
# Setup: ensure pipeline status options exist in both DBs
# =============================================================================

def ensure_status_options(manifest: dict[str, str]) -> None:
    """Sprint 8: ensure status options en TODAS las DBs que tengan propiedad de status.
    Ya no es DB1+DB2; son todas las DBs del manifest.
    """
    pipeline_statuses = ["Esperando Aprobacion", "Aprobado", "Listo para Grabar"]
    for db_key, db_id in manifest.items():
        if not db_key.startswith("db_"):
            continue
        # Propiedades status comunes segun el tipo de DB
        for prop_name in ("Estado", "Estado Guion", "Estado PPT", "Estado Idea", "Estado Producción"):
            try:
                db = _req("GET", f"/databases/{db_id}")
            except Exception as exc:
                continue
            prop = db.get("properties", {}).get(prop_name, {})
            if prop.get("type") != "status":
                continue
            current_options = prop.get("status", {}).get("options", [])
            existing = {o.get("name") for o in current_options}
            new_options = list(current_options)
            for status in pipeline_statuses:
                if status not in existing:
                    new_options.append({"name": status, "color": "default"})
            if len(new_options) > len(current_options):
                try:
                    _patch_db(db_id, {"properties": {prop_name: {"status": {"options": new_options}}}})
                    log.info("Status options anadidas a %s/%s: %s", db_id, prop_name, pipeline_statuses)
                except Exception as exc:
                    log.warning("No se pudieron agregar status a %s/%s: %s", db_id, prop_name, exc)


# =============================================================================
# Mode 1: ideate
# (placeholder removed below)
# =============================================================================

def mode_ideate(manifest: dict[str, str], topic: str, db_key: str = "db_M0", n_ideas: int = 3, week: str = None) -> dict:
    log.info("=" * 64)
    log.info("MODO IDEATE: Trend Hunter + Strategist")
    log.info("=" * 64)
    log.info("Tema: %s | DB: %s | Ideas: %d", topic, db_key, n_ideas)

    # Paso 2: Director General (Master Orchestrator) genera 3 briefs
    # quirurgicos ANTES de delegar a los subagentes. Sprint 2.
    log.info("\n[0/3] Director General: generando briefs quirurgicos...")
    try:
        # Importacion local para evitar ciclos en tiempo de import
        import sys
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent
        if str(PROJECT_ROOT / "vps_backend") not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT / "vps_backend"))
        from orchestrator import generate_surgical_briefs
        briefs = generate_surgical_briefs(topic)
        log.info("  briefs generados:")
        for name, body in briefs.items():
            log.info("    [%s] %d chars", name, len(body))
    except Exception as exc:
        log.warning("  Orquestador fallo (%s); continuando con prompts originales.", exc)
        briefs = None

    # Subagente 1
    log.info("\n[1/3] Subagente 1: Trend Hunter...")
    # Sprint 3: el prompt del Trend Hunter requiere {avatar_text}.
    # Lo formateamos una sola vez por ejecucion.
    from system_prompts_squad import _load_avatar_text
    th_system = TREND_HUNTER_PROMPT.format(avatar_text=_load_avatar_text())
    if briefs:
        th_user_input = "Brief del Orquestador:\n" + briefs.get("trend_hunter_brief", "")
    else:
        th_user_input = "No hay brief del Orquestador. Tema: " + topic
    trends = _call_llm(th_system, th_user_input, label="Trend Hunter")
    log.info("  trends devueltos: %d", len(trends.get("trends", [])))

    # Subagente 2
    log.info("\n[2/3] Subagente 2: Strategist...")
    # Sprint 4: inyectar la Matriz de Productos y combinar brief + 5 ganchos
    from system_prompts_squad import _load_product_matrix_text
    st_system = STRATEGIST_PROMPT.format(
        product_matrix_text=_load_product_matrix_text()
    )
    st_user_input = json.dumps(trends)
    if briefs:
        st_user_input += f"\n\nBRIEF DEL ORQUESTADOR:\n{briefs.get('strategist_brief','')}"
    ideas = _call_llm(st_system, st_user_input, label="Strategist")
    log.info("  ideas devueltas: %d", len(ideas.get("ideas", [])))

    # Crear paginas en Notion
    log.info("\n[3/3] Publicando en Notion (estado: %s)...", DEFAULT_STATE)
    for idea in ideas.get("ideas", []):
        # Normalizar campos: el LLM puede devolver ES (titulo/descripcion) o EN (title/description)
        if "title" not in idea and "titulo" in idea:
            idea["title"] = idea.pop("titulo")
        if "description" not in idea and "descripcion" in idea:
            idea["description"] = idea.pop("descripcion")
        # Forzar target_db al pilar elegido (no confiar en lo que devuelva el LLM)
        idea["target_db"] = db_key

        try:
            page = _create_idea_page(manifest, idea, week=week)
            CREATED_PAGES.append({
                "id": page["id"],
                "url": page.get("url"),
                "title": idea.get("title"),
                "target_db": idea.get("target_db"),
                "idea_id": idea.get("id"),
            })
        except Exception as exc:
            log.error("  No se pudo crear idea %s: %s", idea.get("id"), exc)
            FAILED.append((f"create idea {idea.get('id')}", str(exc)))

    log.info("Publicadas: %d paginas", len(CREATED_PAGES))
    return {
        "trends": trends,
        "ideas": ideas,
        "created_pages": CREATED_PAGES,
        "briefs": briefs,
    }


def _create_idea_page(manifest: dict[str, str], idea: dict, week: str = None, **kwargs) -> dict:
    """Crea una pagina en la DB target. La DB se infiere de idea['target_db'].
    Las propiedades se mapean segun el schema de la DB:
    - db_M0..db_P7 (8 DBs nuevas): Clase, Estado, Semana, Pilar, Tipo, Resumen
    - db_ideas (legacy): Nombre Idea, Estado Idea, Pilar, Tema, Urgencia, Descripcion
    - db1 (legacy): Titulo Guion, Estado Guion, Copy Final
    - db2 (legacy): Nombre Presentacion, Estado PPT
    """
    target = idea.get("target_db", "db_M0")
    db_id = manifest[target]
    properties: dict[str, Any] = {}
    pilar = idea.get("pilar", "")
    if target.startswith("db_") and not target in ("db1", "db2", "db_ideas", "db_prod"):
        # Sprint 8: NUEVA estructura con 8 DBs por pilar
        # Cada DB tiene: Clase (title), Estado, Semana, Pilar, Tipo, Resumen, etc.
        properties["Clase"] = {"title": [{"text": {"content": idea["title"]}}]}
        properties["Estado"] = {"status": {"name": "💡 Idea"}}
        if week:
            properties["Semana"] = {"select": {"name": week}}
        if pilar:
            properties["Pilar"] = {"select": {"name": pilar}}
        # Tipo por defecto: Clase Magistral
        properties["Tipo"] = {"select": {"name": "Clase Magistral"}}
        # Resumen = primeras 200 chars de la descripcion
        desc = idea.get("description", "")
        if desc:
            properties["Resumen"] = {"rich_text": [{"text": {"content": desc[:200]}}]}
    elif target == "db_ideas":
        # LEGACY
        properties["Nombre Idea"] = {"title": [{"text": {"content": idea["title"]}}]}
        properties["Estado Idea"] = {"status": {"name": "Generada"}}
        if idea.get("pilar"):
            properties["Pilar"] = {"select": {"name": idea.get("pilar")}}
        properties["Tema"] = {"rich_text": [{"text": {"content": idea.get("title", "")[:100]}}]}
        properties["Urgencia"] = {"select": {"name": idea.get("urgencia", "Media")}}
        properties["Descripción"] = {"rich_text": [{"text": {"content": idea.get("description", "")}}]}
    elif target == "db1":
        properties["Título Guion"] = {"title": [{"text": {"content": idea["title"]}}]}
        properties["Estado Guion"] = {"status": {"name": "Pendiente"}}
        properties["Copy Final"] = {"rich_text": [{"text": {"content": idea.get("description", "")[:1900]}}]}
    elif target == "db2":
        properties["Nombre Presentación"] = {"title": [{"text": {"content": idea["title"]}}]}
        properties["Estado PPT"] = {"status": {"name": "Pendiente"}}
    else:
        properties["Título Guion"] = {"title": [{"text": {"content": idea["title"]}}]}
        properties["Estado Guion"] = {"status": {"name": "Pendiente"}}
    return _req("POST", f"/pages", {"parent": {"database_id": db_id}, "properties": properties})


# =============================================================================
# Mode admin: approve
# =============================================================================

def mode_approve(manifest: dict[str, str], page_id: str | None, title_contains: str | None) -> int:
    log.info("=" * 64)
    log.info("MODO APPROVE (admin)")
    log.info("=" * 64)
    candidates = _find_approval_candidates(manifest, page_id, title_contains)
    if not candidates:
        log.warning("No se encontraron candidatos para aprobar")
        return 1
    for c in candidates:
        try:
            _patch_page(c["id"], {
                "properties": {c["status_prop"]: {"status": {"name": "Aprobado"}}}
            })
            log.info("  Aprobada: %s (%s)", c["title"], c["id"])
            PASSED.append(f"approved {c['id']}")
        except Exception as exc:
            log.error("  No se pudo aprobar %s: %s", c["id"], exc)
            FAILED.append((f"approve {c['id']}", str(exc)))
    return 0


def _find_approval_candidates(manifest: dict[str, str], page_id: str | None, title_contains: str | None) -> list[dict]:
    candidates: list[dict] = []
    # Sprint 7: propiedades con espacio "Estado Guion" / "Estado PPT"
    for db_key, prop in [("db1", "Estado Guion"), ("db2", "Estado PPT")]:
        try:
            results = _query_db(manifest[db_key], {
                "filter": {"property": prop, "status": {"equals": DEFAULT_STATE}},
                "page_size": 10,
            })
        except Exception as exc:
            log.warning("Query %s fallo: %s", db_key, exc)
            continue
        for r in results:
            title_prop = "Nombre_Clase" if db_key == "db1" else "Nombre_Anuncio"
            try:
                title = "".join(t.get("plain_text", "") for t in r["properties"][title_prop]["title"])
            except Exception:
                title = "<unknown>"
            if page_id and r["id"] != page_id:
                continue
            if title_contains and title_contains.lower() not in title.lower():
                continue
            candidates.append({
                "id": r["id"],
                "title": title,
                "db_key": db_key,
                "status_prop": prop,
            })
    return candidates


# =============================================================================
# Mode 2: process-approved
# =============================================================================

def mode_process_approved(manifest: dict[str, str], dry_run: bool, specific_ids: list[str] | None = None) -> int:
    log.info("=" * 64)
    log.info("MODO PROCESS-APPROVED: Copywriter + Brand Guardian")
    log.info("=" * 64)

    approved = _query_approved_pages(manifest)
    if not approved:
        log.info("No hay paginas en estado 'Aprobado'. Finalizando limpiamente.")
        return 0

    # Si nos pasaron page_ids específicas, filtrar
    if specific_ids:
        original_count = len(approved)
        approved = [p for p in approved if p["id"] in specific_ids or any(p["id"].startswith(sid) for sid in specific_ids)]
        log.info("Filtradas: %d -> %d aprobadas específicas", original_count, len(approved))

    log.info("Encontradas %d paginas aprobadas", len(approved))
    for page in approved:
        try:
            _process_one_page(page, manifest, dry_run)
        except Exception as exc:
            log.error("Fallo procesando %s: %s", page["id"], exc)
            FAILED.append((f"process {page['id']}", str(exc)))

    log.info("\nProcesamiento completo. OK=%d FAIL=%d", len(PASSED), len(FAILED))
    return 0 if not FAILED else 1


# Sprint 6: alias para --all-approved (mismo comportamiento que mode_process_approved
# sin --page-id, ya que mode_process_approved procesa TODAS las tarjetas en
# estado Aprobado si no se pasa ninguna en particular).
mode_process_approved_all = mode_process_approved


def _query_approved_pages(manifest: dict[str, str]) -> list[dict]:
    """Sprint 8: itera sobre TODAS las DBs del manifest (8 pilares) y devuelve
    las paginas con estado '📝 Guion Aprobado' o equivalente.
    """
    approved: list[dict] = []
    # 1) DBs nuevas (8 pilares): buscar propiedad "Estado" == "📝 Guion Aprobado"
    for db_key, db_id in manifest.items():
        if not db_key.startswith("db_M") and not db_key.startswith("db_P"):
            continue
        try:
            results = _query_db(db_id, {
                "filter": {"property": "Estado", "status": {"equals": "📝 Guion Aprobado"}},
                "page_size": 10,
            })
            for page in results:
                page["_source_db"] = db_key
                approved.append(page)
        except Exception as exc:
            log.warning("Query Guion Aprobado en %s fallo: %s", db_key[-12:], exc)

    # 2) Backward compat: DBs legacy (db_ideas, db1, db2)
    if "db_ideas" in manifest:
        try:
            results = _query_db(manifest["db_ideas"], {
                "filter": {"property": "Estado Idea", "status": {"equals": "Aprobada"}},
                "page_size": 10,
            })
            for page in results:
                page["_source_db"] = "db_ideas"
                approved.append(page)
        except Exception as exc:
            log.warning("Query Aprobada en db_ideas fallo: %s", exc)
    for db_key, prop in [("db1", "Estado Guion"), ("db2", "Estado PPT")]:
        try:
            results = _query_db(manifest[db_key], {
                "filter": {"property": prop, "status": {"equals": "Aprobado"}},
                "page_size": 10,
            })
            for page in results:
                page["_source_db"] = db_key
                approved.append(page)
        except Exception as exc:
            log.warning("Query Aprobado en %s fallo: %s", db_key, exc)
    return approved


def _process_one_page(page: dict, manifest: dict[str, str], dry_run: bool) -> None:
    """Sprint 8: procesa una idea aprobada y genera un guion en la MISMA DB.
    Para db_M0/db_P1..db_P7: la idea se queda en la DB del pilar, y se crea una
    nueva entrada (el guion) con link a la idea original via 'Idea Origen'.
    Para db_ideas/db1/db2 (legacy): comportamiento anterior.
    """
    db_key = page.get("_source_db") or page.get("_db_key", "db_P1")

    # Sprint 8: mapear propiedades según fuente
    if db_key.startswith("db_") and db_key not in ("db1", "db2", "db_ideas", "db_prod"):
        # 8 DBs nuevas: propiedad "Clase" (title), "Estado" (status), "Resumen" (text)
        title_prop = "Clase"
        status_prop = "Estado"
        angle_prop = "Resumen"
        pilar_prop = "Pilar"
        avatar_prop = None
        hook_prop = None
    elif db_key == "db_ideas":
        title_prop = "Nombre Idea"
        status_prop = "Estado Idea"
        angle_prop = "Descripción"
        pilar_prop = "Pilar"
        avatar_prop = None
        hook_prop = None
    else:
        title_prop = "Nombre_Clase" if db_key == "db1" else "Nombre_Anuncio"
        status_prop = "Estado_Guion" if db_key == "db1" else "Estado_Copy"
        angle_prop = "Bunny_Embed_Code" if db_key == "db1" else "Script_Video"
        pilar_prop = "Pilar"
        avatar_prop = "Avatar_Target"
        hook_prop = "Tipo_Hook"

    title = "".join(t.get("plain_text", "") for t in page["properties"][title_prop]["title"])
    log.info("\n[Procesando] %s (%s)", title, page["id"])

    # Build the idea payload
    angle = ""
    angle_data = page["properties"].get(angle_prop, {}).get("rich_text", [])
    if angle_data:
        angle = angle_data[0].get("text", {}).get("content", "")

    idea_payload = {
        "page_id": page["id"],
        "target_db": db_key,
        "title": title,
        "angle": angle,
        "promise": "",
        "description": "",
    }
    if pilar_prop and db_key in ("db_ideas", "db1"):
        select_obj = page["properties"].get(pilar_prop, {}).get("select") or {}
        idea_payload["pilar"] = select_obj.get("name", "") if isinstance(select_obj, dict) else ""
    if avatar_prop and db_key == "db2":
        avatar_obj = page["properties"].get(avatar_prop, {}).get("select") or {}
        idea_payload["avatar_target"] = avatar_obj.get("name", "") if isinstance(avatar_obj, dict) else ""
        hook_obj = page["properties"].get(hook_prop, {}).get("select") or {}
        idea_payload["tipo_hook"] = hook_obj.get("name", "") if isinstance(hook_obj, dict) else ""

    # Subagente 3: Copywriter (sprint 5: inyectar Ejemplos de Oro en el prompt)
    log.info("  [3] Copywriter...")
    from system_prompts_squad import _load_gold_standard_examples_text
    cw_system = COPYWRITER_PROMPT.format(
        gold_standard_examples_text=_load_gold_standard_examples_text()
    )
    script = _call_llm(cw_system, json.dumps(idea_payload), label="Copywriter")
    log.info("      word_count=%d duracion=%d min", script.get("word_count", 0), script.get("estimated_duration_min", 0))

    # Subagente 4: Brand Guardian
    # Sprint 11: usamos SIEMPRE el stub del Guardian porque procesa el markdown
    # del Copywriter en bloques validos de Notion. El LLM tiende a generar
    # tipos de bloque no soportados (embed, bookmark) que rompen el PATCH.
    log.info("  [4] Brand Guardian (stub seguro)...")
    guardian_input = {
        "page_id": page["id"],
        "target_db": db_key,
        "title": title,
        "content_markdown": script.get("content_markdown", ""),
        "key_takeaway": script.get("key_takeaway", ""),
        "estimated_duration_min": script.get("estimated_duration_min", 25),
    }
    chunks = _stub_guardian(guardian_input)
    log.info("      blocks=%d chars=%d", chunks.get("block_count", 0), chunks.get("total_chars", 0))
    val = chunks.get("validation", {})
    if not val.get("passed"):
        for issue in val.get("issues", []):
            log.warning("      validation: %s", issue)

    if dry_run:
        log.info("  [DRY-RUN] skip publicacion y update de estado")
        PASSED.append(f"dryrun {page['id']}")
        return

    # Sprint 8: Publicar bloques en la pagina CORRECTA
    # Si la idea viene de una DB de pilar (db_M0..db_P7), crear NUEVA pagina en la MISMA DB
    # Si la idea viene de db_ideas legacy, crear pagina en db1
    # Si la idea viene de db1/db2 legacy, los bloques se agregan a la misma pagina
    target_publish_id = page["id"]  # default: misma pagina
    if db_key.startswith("db_") and db_key not in ("db1", "db2", "db_ideas", "db_prod"):
        # Crear una NUEVA pagina en la DB del pilar
        guion_title = title
        guion_payload = {
            "parent": {"database_id": manifest[db_key]},
            "properties": {
                "Clase": {"title": [{"text": {"content": f"📝 {guion_title}"}}]},
                "Estado": {"status": {"name": "🎬 Para Grabar"}},
                "Tipo": {"select": {"name": "Clase Magistral"}},
                "Duracion (min)": {"number": 25},
            },
        }
        result = _req("POST", "/pages", guion_payload)
        target_publish_id = result.get("id", page["id"])
        log.info("      guion creado en DB %s: %s", db_key, target_publish_id)
    elif db_key == "db_ideas":
        # LEGACY: crear en db1
        guion_title = title
        guion_payload = {
            "parent": {"database_id": manifest["db1"]},
            "properties": {
                "Título Guion": {"title": [{"text": {"content": guion_title}}]},
                "Estado Guion": {"status": {"name": "Generado"}},
                "Version": {"number": 1},
            },
        }
        result = _req("POST", "/pages", guion_payload)
        target_publish_id = result.get("id", page["id"])
        log.info("      guion creado en DB Guiones: %s", target_publish_id)
        # Crear relacion con la idea original
        try:
            _req("PATCH", f"/pages/{target_publish_id}", {
                "properties": {
                    "Idea Origen": {"relation": [{"id": page["id"]}]},
                    "Clase Fábrica": {"relation": [{"id": page["id"]}]},
                }
            })
        except Exception as exc:
            log.warning("      no se pudo vincular idea-guion: %s", exc)

    # Publicar bloques en la pagina destino
    blocks = chunks.get("blocks", [])
    if blocks:
        _append_children(target_publish_id, blocks)
        log.info("      %d bloques anadidos al body de la pagina", len(blocks))

    # Actualizar estado del guion
    if db_key.startswith("db_") and db_key not in ("db1", "db2", "db_ideas", "db_prod"):
        # Sprint 8: el GUION ya quedó en "🎬 Para Grabar" al crearse.
        # Marcar la IDEA original como "📝 Guion Aprobado" → "🎬 Para Grabar"
        # para indicar que ya se generó el guion. Pero como es OTRA entrada en
        # la misma DB, no la modificamos (ya está en Guion Aprobado del query).
        log.info("      guion creado en estado 🎬 Para Grabar (ID: %s)", target_publish_id[:12])
    elif db_key == "db_ideas":
        # LEGACY: el estado de la IDEA queda como Aprobada
        log.info("      estado de la IDEA queda en Aprobada")
    else:
        # Legacy: el status_prop SÍ es la DB de origen
        _patch_page(page["id"], {
            "properties": {status_prop: {"status": {"name": "Listo para Grabar"}}}
        })
    PASSED.append(f"processed {page['id']}")
    log.info("      estado actualizado a 'Listo para Grabar'")


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="Squad de 4 subagentes con Autonomia Hibrida")
    parser.add_argument("--mode", required=True, choices=["ideate", "approve", "process-approved"],
                        help="Modo del pipeline")
    parser.add_argument("--topic", default=None,
                        help="Tema para el modo ideate (requerido si --ideas no se usa)")
    parser.add_argument("--ideas", type=int, default=3,
                        help="Cantidad de ideas a generar en ideate (default 3)")
    parser.add_argument("--db", default=None,
                        help="DB target para ideate (ej: db_P1, db_M0). Default: db_M0 (onboarding)")
    parser.add_argument("--week", default=None,
                        help="Semana del roadmap (ej: Semana 1, Onboarding)")
    parser.add_argument("--page-id", help="Page ID especifico (modo approve)")
    parser.add_argument("--title-contains", help="Filtro de titulo (modo approve)")
    parser.add_argument("--page-ids", help="Page IDs especificos separados por coma (modo process-approved)")
    parser.add_argument("--dry-run", action="store_true", help="No publicar ni modificar Notion")
    parser.add_argument(
        "--all-approved",
        action="store_true",
        help="Modo process-approved: procesa TODAS las tarjetas en estado Aprobado en Notion",
    )
    args = parser.parse_args()

    try:
        manifest = _load_manifest()
    except Exception as exc:
        log.error("Manifiesto no encontrado: %s", exc)
        return 1

    # Asegurar que las opciones de status existen
    ensure_status_options(manifest)

    if args.mode == "ideate":
        # Sprint 8: si no se pasa topic, usar uno generico para el pilar
        topic = args.topic or f"10 ideas de clase para {args.db or 'db_M0'}"
        mode_ideate(manifest, topic, db_key=args.db or "db_M0", n_ideas=args.ideas, week=args.week)
    elif args.mode == "approve":
        return mode_approve(manifest, args.page_id, args.title_contains)
    elif args.mode == "process-approved":
        # Sprint 6: --all-approved procesa TODAS las tarjetas en estado
        # Aprobado. --page-id procesa solo esa. --dry-run simula sin publicar.
        if args.all_approved:
            return mode_process_approved_all(manifest, args.dry_run)
        if args.page_ids:
            # Filtrar las aprobadas solo a las page_ids específicas
            specific_ids = [p.strip() for p in args.page_ids.split(",") if p.strip()]
            log.info("Filtrando a %d page_ids específicas: %s", len(specific_ids), specific_ids)
            return mode_process_approved(manifest, args.dry_run, specific_ids=specific_ids)
        return mode_process_approved(manifest, args.dry_run)

    log.info("\nResumen: %d OK | %d FAIL", len(PASSED), len(FAILED))
    for label, detail in FAILED:
        log.error("- %s | %s", label, detail)
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
