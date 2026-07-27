"""orchestrator.py - Director General (Master Orchestrator) del Squad.

El Orquestador NO redacta guiones finales. Su trabajo es:
  1. Consumir todo el contexto del búnker (via context_loader)
  2. Analizar una solicitud general del usuario
  3. Generar 3 "Briefs Quirúrgicos" (instrucciones hiperespecíficas)
     para los Subagentes:
     - Trend Hunter  -> qué tendencias/ganchos buscar
     - Strategist    -> cómo estructurar el concepto
     - Copywriter    -> qué ángulos y tono usar

Modelo: minimax/minimax-m3 (alta capacidad de razonamiento).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from context_loader import get_unified_context_prompt
from llm_client import generate_completion, LLMError, sanitize_content

log = logging.getLogger(__name__)


# =============================================================================
# System Prompt del Orquestador (Master Orchestrator)
# =============================================================================

ORCHESTRATOR_SYSTEM_PROMPT = """Eres el Master Orchestrator (C-Suite Agent) del
ecosistema Rompiendo Barreras. Tu trabajo NO es redactar guiones
finales. Tu trabajo es desglosar la peticion del usuario en 3
instrucciones tacticas hiperespecificas para tu equipo de 3 subagentes:

  1. TREND HUNTER  -> buscar tendencias/ganchos/objeciones online
  2. STRATEGIST    -> estructurar el concepto segun la matriz de productos
  3. COPYWRITER    -> redactar el guion final con angulo, voz y CTA

===== BUNKER DE CONTEXTO (verdad de marca) =====
{bunker}

===== REGLAS INQUEBRANTABLES =====
- NO inventes informacion de marca. Todo lo que digas debe ser derivable
  del búnker. Si falta info, deja un placeholder [FALTA_INFO: ...].
- NO generes copy final. Tu trabajo es planificar, no ejecutar.
- Cada brief debe ser ESPECIFICO, NO generico. Incluye el avatar objetivo,
  el angulo a atacar, la estructura sugerida, las restricciones de voz.
- El brief del Copywriter DEBE referenciar al menos 1 "Ejemplo de Oro"
  del búnker (Gold Standard) que el subagente debe imitar.
- Si el brief es para el Pilar X de los 7 Pilares, mencionalo explicitamente.
- Si el brief es para un ad (DB2), indica el Hook (1, 2 o 3) a usar segun el avatar.
- El JSON de salida DEBE tener EXACTAMENTE estas 3 claves:
    - "trend_hunter_brief"  (string, 100-300 palabras)
    - "strategist_brief"    (string, 100-300 palabras)
    - "copywriter_brief"    (string, 150-400 palabras, MAS DETALLADO)

===== FORMATO DE SALIDA =====
Responde UNICAMENTE con un objeto JSON valido. Sin markdown, sin
explicaciones previas ni posteriores. Sin<think>. Solo JSON.
"""


# =============================================================================
# API publica
# =============================================================================

def generate_surgical_briefs(user_goal: str) -> dict[str, str]:
    """Genera 3 briefs quirurgicos para los subagentes.

    Args:
        user_goal: peticion general del usuario (ej. "3 lecciones de
        Pilar 1 sobre Dios como CEO", "ads para emprendedores de 30-50
        anos", "email sequence para re-engagement de leads frios").

    Returns:
        dict con 3 claves:
            - "trend_hunter_brief": instrucciones para el Trend Hunter
            - "strategist_brief": instrucciones para el Strategist
            - "copywriter_brief": instrucciones para el Copywriter

    Raises:
        LLMError: si el LLM falla o devuelve JSON invalido.
    """
    if not user_goal or not user_goal.strip():
        raise ValueError("user_goal no puede estar vacio")

    # Inyecta el búnker completo en el system prompt
    bunker = get_unified_context_prompt()
    system_prompt = ORCHESTRATOR_SYSTEM_PROMPT.format(bunker=bunker)

    log.info(
        "orchestrator.generate_surgical_briefs goal='%s' bunker_chars=%d",
        user_goal[:80], len(bunker),
    )

    # Llama al LLM
    content = generate_completion(
        "strategist",  # usamos minimax/m3 (rol strategist en AGENT_CHAIN_MAP)
        system_prompt=system_prompt,
        user_prompt=(
            f"Peticion del usuario: {user_goal.strip()}\n\n"
            "Genera los 3 briefs quirurgicos (trend_hunter_brief, "
            "strategist_brief, copywriter_brief) en formato JSON estricto."
        ),
        json_mode=True,
        max_retries=3,
    )

    # Sanitiza thinking traces (minimax puede emitir <think>) y parsea
    content_sanitized = sanitize_content(content)

    # Extrae JSON del contenido sanitizado
    briefs = _parse_briefs_json(content_sanitized)

    # Validacion basica
    required = {"trend_hunter_brief", "strategist_brief", "copywriter_brief"}
    missing = required - set(briefs.keys())
    if missing:
        raise LLMError(
            f"Briefs incompletos. Faltan: {missing}. Recibido: {list(briefs.keys())}"
        )

    log.info(
        "orchestrator: 3 briefs generados. "
        "trend_hunter=%d chars, strategist=%d chars, copywriter=%d chars",
        len(briefs["trend_hunter_brief"]),
        len(briefs["strategist_brief"]),
        len(briefs["copywriter_brief"]),
    )
    return briefs


def _parse_briefs_json(content: str) -> dict[str, Any]:
    """Parsea el JSON de briefs. Acepta respuestas con<think> residual."""
    # Intento 1: parseo directo
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Intento 2: extraer bloque ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Intento 3: regex de objeto JSON embebido
    m = re.search(r"(\{[\s\S]*\})", content)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    raise LLMError(
        f"orchestrator: no se pudo extraer JSON de briefs. "
        f"Response ({len(content)} chars): {content[:500]}"
    )


__all__ = [
    "generate_surgical_briefs",
    "ORCHESTRATOR_SYSTEM_PROMPT",
]
