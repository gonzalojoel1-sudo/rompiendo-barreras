# 🏛️ Plan Maestro de Arquitectura: Squad con Contexto Total (Rompiendo Barreras)

## 📌 Objetivo del Documento
Transformar el sistema de agentes actual en un equipo de "mega trabajadores" hiperespecializados. El objetivo es eliminar el "sabor a IA" inyectando el contexto masivo del proyecto mediante un Búnker de Conocimiento y un Orquestador que dirija las operaciones.

---

## 🏗️ 1. Arquitectura de 3 Capas (Conocimiento y Ejecución)

                  ┌──────────────────────────────────────────────────┐
                  │          🏛️ CAPA 1: BÚNKER DE CONTEXTO           │
                  │   (Archivos Markdown con la Verdad Absoluta)     │
                  └─────────────────────────┬────────────────────────┘
                                            │
                                            ▼
                  ┌──────────────────────────────────────────────────┐
                  │        👑 CAPA 2: EL DIRECTOR GENERAL            │
                  │        (Master Orchestrator / C-Suite Agent)     │
                  └─────────────────────────┬────────────────────────┘
                                            │
                        (Crea Briefs Quirúrgicos + Inyecta Contexto)
                                            │
       ┌────────────────────────────────────┼────────────────────────────────────┐
       ▼                                    ▼                                    ▼
┌──────────────┐                     ┌──────────────┐                     ┌──────────────┐
│  🔍 AGENTE 1 │                     │  💡 AGENTE 2 │                     │  ✍️ AGENTE 3 │
│ Niche Scout  │                     │ Strategist   │                     │ Copy Master  │
└──────┬───────┘                     └──────┬───────┘                     └──────┬───────┘
       │                                    │                                    │
       └────────────────────────────────────┼────────────────────────────────────┘
                                            │
                                            ▼
                  ┌──────────────────────────────────────────────────┐
                  │         🛡️ CAPA 3: EDITOR EN JEFE (QA)           │
                  │   (Evalúa vs. Búnker: ¿Suena a Marcos? 9/10+)    │
                  └──────────────────────────────────────────────────┘

---

## 📚 2. El Búnker de Contexto (`/context_vault`)

El núcleo del sistema. El Orquestador leerá estos 5 archivos automáticamente antes de delegar cualquier tarea para garantizar fidelidad absoluta a la marca:

1. **`01_brand_manifesto.md`:** Filosofía de Marcos Barbosa, visión del negocio, principios no negociables, postura ante el liderazgo y la fe ("Dios como CEO").
2. **`02_tone_and_voice.md`:** Manual de comunicación exacto. Palabras prohibidas (cero clichés de "vendedor humo"), vocabulario clave, ritmo de frases y analogías recurrentes.
3. **`03_target_avatar.md`:** Perfil detallado del alumno ideal (empresario cristiano saturado). Dolores nocturnos, objeciones reales, nivel socioeconómico, miedos y metas.
4. **`04_product_matrix.md`:** Desglose del programa. Contenidos de los Pilares 1 al 4, módulos, promesas específicas y entregables de la hoja de ruta de 24 semanas.
5. **`05_gold_standard_examples.md`:** 3 o 4 guiones reales de Marcos que sirven como modelo de referencia estricto (*few-shot prompting*) para ritmo, ganchos y CTAs.

---

## 🔄 3. Master Roadmap: Flujo de Trabajo E2E (6 Pasos)

┌─────────────────────────────────────────────────────────────────────────┐
│ [✅ COMPLETADO] [PASO 1] Búnker de Contexto (/context_vault)               │
│    └─► Inyección de los 5 archivos Markdown con la Verdad de Marca      │
├─────────────────────────────────────────────────────────────────────────┤
│ [✅ COMPLETADO] [PASO 2] Director General (Master Orchestrator)            │
│    └─► Lectura global, emisión de Briefs Quirúrgicos y Loop de QA       │
├─────────────────────────────────────────────────────────────────────────┤
│ [✅ COMPLETADO] [PASO 3] Investigación Filtrada (Trend Hunter)               │
│    └─► Cazador de ganchos alineados 100% al Avatar del Búnker           │
├─────────────────────────────────────────────────────────────────────────┤
│ [✅ COMPLETADO] [PASO 4] Ideación Estructurada (Content Strategist)          │
│    └─► Matriz de Pilares (DB1/DB2) procesada con MiniMax-M3             │
├─────────────────────────────────────────────────────────────────────────┤
│ [✅ COMPLETADO] [PASO 5] Redacción de Élite + Claude 3.5 Sonnet (Copywriter)  │
│    └─► Guiones basados en "Ejemplos de Oro" + Conmutación a Claude      │
├─────────────────────────────────────────────────────────────────────────┤
│ [✅ COMPLETADO] [PASO 6] Auditoría QA, Disparo por Webhook y Escalado       │
│    └─► Control de calidad 9/10+ -> Notion -> Ejecución 100% Desatendida │
└─────────────────────────────────────────────────────────────────────────┘

### Detalle Operativo por Paso:

* **Paso 1 — Carga de Insumos:** Creación física del directorio `/context_vault` y poblamiento de los 5 archivos base mediante la extracción de la información original del proyecto.
* **Paso 2 — Briefing (Orquestador):** El C-Suite Agent carga el contexto. No redacta guiones; emite instrucciones hiperespecíficas para los subagentes (qué dolor atacar, qué ejemplo imitar).
* **Paso 3 — Investigación (Trend Hunter):** Ejecutado con `MiniMax-M2.7-highspeed` ($0 extra). Cruza tendencias externas estrictamente contra `03_target_avatar.md` para asegurar relevancia.
* **Paso 4 — Ideación (Content Strategist):** Ejecutado con `MiniMax-M3`. Cruza los insights del paso anterior con `04_product_matrix.md` para producir las tarjetas en Notion (`Esperando Aprobación`).
* **Paso 5 — Redacción de Élite (Copywriter Master):** Redacta guiones largos (~1,400 palabras) clonando el estilo de `05_gold_standard_examples.md`. Utiliza Gemini 3.5 temporalmente, programado para conmutar automáticamente a Claude 3.5 Sonnet tras la aprobación de cuota (60 RPM).
* **Paso 6 — Auditoría QA y Automatización (Webhook):** 
  - *Loop QA:* El Orquestador evalúa el guion generado contra el manual de tono. Si es < 9/10, fuerza reescritura.
  - *Webhook:* Activación del endpoint `/api/v1/orca/webhook/trigger` para disparar el flujo automáticamente al aprobar una tarjeta en Notion.