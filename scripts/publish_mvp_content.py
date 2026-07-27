"""publish_mvp_content.py - Publica la leccion del M0 y 2 anuncios en Notion.

Usa notion_bridge directamente (sin servidor HTTP) para minimizar superficie
de fallo en la publicacion. El orquestador registra los eventos en el
scratchpad via API en un paso posterior.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vps_backend"))

from rb_notion_bridge import CachedSchemaService, NotionClient  # noqa: E402
from rb_notion_bridge.config import NotionBridgeConfig  # noqa: E402

NOTION_TOKEN = os.getenv(
    "NOTION_API_KEY",
    "ntn_REDACTED_LEAK_2026-07-28",
)
MANIFEST_PATH = ROOT / "manifests" / "notion_databases_manifest.json"


def find_db_id(label_hint: str) -> str:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    for entry in manifest:
        if label_hint in entry.get("label", ""):
            return entry["id"]
    raise RuntimeError(f"DB {label_hint!r} no encontrada en el manifiesto")


# Contenido generado por el Subagente Scriptwriter (Fase 2)
LESSON = {
    "nombre_clase": "Módulo 0: Bienvenido a la Misión — Activa tu Primera Victoria",
    "pilar": "Módulo 0: Onboarding",
    "semana_roadmap": 0,
    "estado_guion": "Guion Generado",
    "estado_ppt": "Pendiente",
    "estado_grabacion": "Pendiente",
    "estado_publicacion": "Pendiente",
    "bunny_embed_code": "",
    "pdf_entregable_url": "",
    "contenido_guion_markdown": (
        "# INTRODUCCIÓN — BIENVENIDO A LA MISIÓN\n\n"
        "¡Hola! Te doy la bienvenida oficial a **Rompiendo Barreras**. Mi nombre es Marcos Barbosa y quiero "
        "decirte algo con total claridad desde el segundo uno: no estás aquí por casualidad ni compraste un "
        "simple curso grabado de internet.\n\n"
        "Has ingresado a una misión y a un movimiento de líderes y empresarios cristianos. Si estás viendo esta "
        "clase, es porque Dios ha colocado en tu corazón el llamado a dejar atrás la escasez mental, el desorden y "
        "la improvisación para convertirte en un **José de Arimatea moderno**: una persona con sabiduría, "
        "disciplina, integridad y recursos puestos al servicio del Reino.\n\n"
        "José de Arimatea fue un discípulo que utilizó su posición y sus bienes para honrar a Jesús cuando llegó el "
        "momento decisivo (Mateo 27:57-60). Ese es nuestro modelo: no perseguimos recursos como un fin; "
        "desarrollamos carácter, capacidad y mayordomía para servir mejor a Dios, cuidar nuestra casa y financiar "
        "la expansión del Evangelio.\n\n"
        "Deja fuera de esta plataforma todo sentimiento de incapacidad y toda culpa por tus errores financieros o "
        "empresariales pasados. **Tu historia no te define; los principios que decidas practicar desde hoy, sí.** "
        "Bienvenido a tu nueva casa de formación.\n\n"
        "## 1. Nuestra misión\n"
        "**Transformar vidas y ganar almas para Cristo mediante la excelencia profesional y la administración sabia.**\n\n"
        "## 2. Nuestra visión\n"
        "Empresarios formados en principios bíblicos transformando industrias, restaurando la economía de sus "
        "familias, saliendo de deudas y financiando obras que anuncien el Evangelio.\n\n"
        "## 3. Tu propósito\n"
        "Dones dados por Dios + problemas reales que puedes resolver + servicio a los demás = propósito operativo.\n\n"
        "## 4. Nuestra metodología (DIY / DWY / DFY)\n"
        "DIY: hazlo tú mismo. DWY: hecho contigo. DFY: hecho para ti. **Regla del 1% diario**.\n\n"
        "## 5. Las 4 Áreas de Control\n"
        "Espiritual | Personal y salud | Profesional | Familiar.\n\n"
        "## 6. Código de Honor\n"
        "Cero quejas estériles. Máxima colaboración. Confidencialidad e integridad radical.\n\n"
        "## 7. Activación inmediata: tu #PrimeraVictoria\n"
        "Aprendizaje × Aplicación = Transformación. Identifica un gasto innecesario, elimínalo hoy, publica con "
        "el hashtag **#PrimeraVictoria**.\n\n"
        "---\n\n"
        "**MISIÓN #PRIMERAVICTORIA (24h):**\n"
        "1. Abre tu estado de cuenta o billetera.\n"
        "2. Identifica un gasto innecesario u 'hormiga'.\n"
        "3. Cáncelalo hoy mismo.\n"
        "4. Publica en la comunidad: #PrimeraVictoria — eliminé ___, liberaré __/mes.\n\n"
        "**Recursos adjuntos:** Hoja de diagnóstico de las 4 Áreas | Rastreador Regla del 1% | Checklist "
        "#PrimeraVictoria 24h | Código de Honor | Matriz DIY/DWY/DFY."
    ),
}

# Contenido generado por el Subagente Copywriter (Fase 2)
ADS = [
    {
        "nombre_anuncio": "AD_AV1_HOOK1_PAZ_FAMILIA_V1",
        "avatar_target": "Avatar 1: Pyme / Empresario",
        "tipo_hook": "Hook 1: Emocional (Paz y Familia)",
        "script_video": (
            "HOOK (0-5s):\nLlevas 14 horas en tu oficina. Y tu hija ya no pregunta cuándo llegas. Solo te "
            "abraza cuando duermes.\n\n"
            "CUERPO (5-25s):\nYo te entiendo. Fui empresario. Fundé, crecí, casi me destruyo trabajándole 14 horas "
            "por día. Hasta que entendí una cosa: tu negocio no es tu vida. Tu familia sí.\n\n"
            "Hoy acompaño a empresarios a salir del síndrome del hámster. Con sistemas reales, finanzas ordenadas "
            "y un código de honor que no negocia tu hogar.\n\n"
            "En 6 meses te entrego lo que a mí me tomó una década aprender: una empresa que funcione sin tu "
            "presencia, finanzas que respiran y paz para dormir de verdad.\n\n"
            "Lo que otros construyen a base de burnout, tú lo puedes construir con orden. Más de 200 empresarios ya "
            "están adentro.\n\n"
            "CTA (25-30s):\nRompiendo Barreras. Programa de 6 meses. Desde $97 de inscripción + $15 al mes. "
            "Garantía real de 7 días. Cupos limitados. Link en el perfil. Empieza hoy."
        ),
        "estado_copy": "Borrador IA",
        "estado_video": "Pendiente",
        "estado_campana": "Inactivo",
        "inversion_diaria_usd": 10.0,
    },
    {
        "nombre_anuncio": "AD_AV2_HOOK3_JOSE_ARIMATEA_V1",
        "avatar_target": "Avatar 2: Joven Emprendedor",
        "tipo_hook": "Hook 3: Identidad (José de Arimatea)",
        "script_video": (
            "HOOK (0-5s):\nJosé de Arimatea era un joven empresario que financió el Evangelio en silencio. En "
            "los tiempos más oscuros, Dios levantó uno. ¿Y si hoy está buscando al próximo?\n\n"
            "CUERPO (5-25s):\nTienes 22, 25, 30 años. Sientes el llamado. Pero no sabes por dónde arrancar. No "
            "tienes capital, no tienes conexiones, y el miedo al fracaso te paraliza cada noche.\n\n"
            "A mí también me pasó. Vengo de las Fuerzas Especiales de Élite. Fundé empresas. Cometí errores que "
            "casi me cuestan todo. Hoy ayudo a jóvenes como tú a convertir su fe en un negocio con propósito real.\n\n"
            "En 6 meses te doy un plan medible paso a paso: cómo validar tu idea, conseguir tus primeros clientes, "
            "ordenar tus finanzas y entrar a una red de mentores que ya están caminando el camino. Más de 200 "
            "jóvenes ya empezaron esta ruta.\n\n"
            "CTA (25-30s):\nRompiendo Barreras. Programa de 6 meses. Inscripción $97 + desde $15 mensuales. "
            "Garantía de 7 días. Tu momento es ahora. Link en el perfil. Inscríbete hoy."
        ),
        "estado_copy": "Borrador IA",
        "estado_video": "Pendiente",
        "estado_campana": "Inactivo",
        "inversion_diaria_usd": 10.0,
    },
]


def main() -> int:
    config = NotionBridgeConfig.from_env()
    if config.api_key != NOTION_TOKEN:
        config = NotionBridgeConfig(api_key=NOTION_TOKEN, api_version="2022-06-28",
                                    timeout=30.0, max_retries=3,
                                    backoff_base=0.5, backoff_max=8.0)
    client = NotionClient(config)
    cached = CachedSchemaService(client)

    db1_id = find_db_id("Fábrica")
    db2_id = find_db_id("Anuncios")
    print(f"DB1 Fabrica:        {db1_id}")
    print(f"DB2 Anuncios:       {db2_id}")
    print()

    created = []

    # --- Crear leccion en DB1 ---
    print("[1/3] Creando leccion en DB1 Fabrica de Clases...")
    svc1 = cached.get_service(db1_id)
    page1 = svc1.create_notion_page(db1_id, {
        "Nombre_Clase": LESSON["nombre_clase"],
        "Pilar": LESSON["pilar"],
        "Semana_Roadmap": LESSON["semana_roadmap"],
        "Estado_Guion": LESSON["estado_guion"],
        "Estado_PPT": LESSON["estado_ppt"],
        "Estado_Grabacion": LESSON["estado_grabacion"],
        "Estado_Publicacion": LESSON["estado_publicacion"],
        "Bunny_Embed_Code": LESSON["contenido_guion_markdown"],
        "PDF_Entregable_URL": LESSON["pdf_entregable_url"] or None,
    })
    page1_id = page1.get("id")
    print(f"  OK | page_id={page1_id}")
    print(f"      url={page1.get('url')}")
    created.append({
        "type": "LESSON_SCRIPT_UPDATED",
        "db": "DB1",
        "page_id": page1_id,
        "url": page1.get("url"),
        "title": LESSON["nombre_clase"],
        "marker": "M0_BIENVENIDA_LESSON",
    })

    # --- Crear 2 anuncios en DB2 ---
    for idx, ad in enumerate(ADS, start=2):
        print(f"\n[{idx}/3] Creando anuncio en DB2: {ad['nombre_anuncio']}...")
        svc2 = cached.get_service(db2_id)
        page = svc2.create_notion_page(db2_id, {
            "Nombre_Anuncio": ad["nombre_anuncio"],
            "Avatar_Target": ad["avatar_target"],
            "Tipo_Hook": ad["tipo_hook"],
            "Script_Video": ad["script_video"],
            "Estado_Copy": ad["estado_copy"],
            "Estado_Video": ad["estado_video"],
            "Estado_Campana": ad["estado_campana"],
            "Inversion_Diaria_USD": ad["inversion_diaria_usd"],
        })
        page_id = page.get("id")
        print(f"  OK | page_id={page_id}")
        print(f"      url={page.get('url')}")
        created.append({
            "type": "AD_LAUNCHED",
            "db": "DB2",
            "page_id": page_id,
            "url": page.get("url"),
            "title": ad["nombre_anuncio"],
            "marker": ad["nombre_anuncio"],
        })

    # Guardar manifesto con los IDs para uso posterior (verificacion + scratchpad)
    out_path = ROOT / "manifests" / "mvp_publish_manifest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(created, f, indent=2, ensure_ascii=False)
    print(f"\nManifiesto de publicacion guardado en: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
