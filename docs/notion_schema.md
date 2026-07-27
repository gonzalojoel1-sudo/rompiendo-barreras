# notion_schema.md - Especificación de Bases de Datos e Integración API REST para Notion

Este documento define la estructura técnica, nombres de propiedades, tipos de datos, relaciones y payloads JSON oficiales para las 4 Bases de Datos centrales en **Notion**, integradas con los agentes autónomos en **Orca** vía API REST (`https://api.notion.com/v1/...`).

---

## 1. Arquitectura del Workspace en Notion

```text
                                [ ROMPIENDO BARRERAS WORKSPACE ]
                                                |
     +-------------------+----------------------+-------------------+-------------------+
     |                   |                                         |                   |
[DB 1: Fábrica      [DB 2: Matriz             [DB 3: Tareas y       [DB 4: Control de
  de Clases]          de Anuncios]             Roadmap]              Alumnos e Hitos]
  (Agente 1)          (Agente 2)               (Agente 3)            (Agente 4)
```

---

## 2. DATABASE 1: Fábrica de Clases (Producción de Contenido)

### 2.1. Propiedades y Esquema de Columnas

| Nombre de Propiedad (Key) | Tipo de Dato Notion | Opciones / Formato | Descripción |
| :--- | :--- | :--- | :--- |
| **Nombre_Clase** | `title` | Texto | Nombre oficial de la lección |
| **Pilar** | `select` | `Módulo 0: Onboarding`, `Pilar 1: Casa de Gobierno`, `Pilar 2: Mentalidad de Reino`, `Pilar 3: Hábitos del Éxito`, `Pilar 4: Mayordomía Responsable`, `Pilar 5: Trabajo y Propósito`, `Pilar 6: Modelado de Negocios`, `Pilar 7: Expansión del Reino` | Clasificación por pilar del programa |
| **Semana_Roadmap** | `number` | `0` a `24` | Número de semana correspondiente |
| **Estado_Guion** | `status` | `Sin Iniciar`, `Generar Guion IA`, `Guion Generado`, `Aprobado Marcos` | Estado del texto pedagógico |
| **Estado_PPT** | `status` | `Pendiente`, `En Diseño (Joel)`, `PPT Lista` | Estado de maquetación de diapositivas |
| **Estado_Grabacion** | `status` | `Pendiente`, `Grabado Marcos` | Estado de captura de video |
| **Estado_Publicacion** | `status` | `Pendiente`, `Subido Bunny Stream`, `Publicado Plataforma` | Estado final en la web de alumnos |
| **Bunny_Embed_Code** | `rich_text` | HTML `<iframe>...</iframe>` | Código de incrustación de Bunny Stream |
| **PDF_Entregable_URL** | `url` | URL HTTPS | Enlace al recurso PDF/Excel adjunto |

### 2.2. Payload JSON API Notion (`POST /v1/pages`) - Crear Nueva Clase

```json
{
  "parent": { "database_id": "DATABASE_FABRICA_CLASES_ID" },
  "properties": {
    "Nombre_Clase": {
      "title": [{ "text": { "content": "Pilar 1 - Clase 2: Código de Honor Personal" } }]
    },
    "Pilar": {
      "select": { "name": "Pilar 1: Casa de Gobierno" }
    },
    "Semana_Roadmap": {
      "number": 2
    },
    "Estado_Guion": {
      "status": { "name": "Generar Guion IA" }
    }
  }
}
```

---

## 3. DATABASE 2: Matriz de Anuncios (Meta Ads & Copywriting)

### 3.1. Propiedades y Esquema de Columnas

| Nombre de Propiedad (Key) | Tipo de Dato Notion | Opciones / Formato | Descripción |
| :--- | :--- | :--- | :--- |
| **Nombre_Anuncio** | `title` | Texto | Identificador único del creativo |
| **Avatar_Target** | `select` | `Avatar 1: Pyme / Empresario`, `Avatar 2: Joven Emprendedor` | Segmentación del anuncio |
| **Tipo_Hook** | `select` | `Hook 1: Emocional (Paz y Familia)`, `Hook 2: Lógico (Sistemas)`, `Hook 3: Identidad (José de Arimatea)` | Ángulo persuasivo utilizado |
| **Script_Video** | `rich_text` | Texto largo | Guion redactado por Agente 2 |
| **Estado_Copy** | `status` | `Borrador IA`, `Listo para Grabar` | Estado del texto de venta |
| **Estado_Video** | `status` | `Pendiente`, `Grabado Marcos`, `Editado Joel` | Estado de producción audiovisual |
| **Estado_Campana** | `status` | `Inactivo`, `Activo Meta Ads`, `Pausado / Fatigado` | Estado en Meta Ads Manager |
| **Inversion_Diaria_USD** | `number` | Ej: `10.00` | Presupuesto diario asignado |

### 2.2. Payload JSON API Notion (`POST /v1/pages`) - Insertar Anuncio Generado por Agente 2

```json
{
  "parent": { "database_id": "DATABASE_MATRIZ_ANUNCIOS_ID" },
  "properties": {
    "Nombre_Anuncio": {
      "title": [{ "text": { "content": "AD_AV1_HOOK3_JoseDeArimatea_V1" } }]
    },
    "Avatar_Target": {
      "select": { "name": "Avatar 1: Pyme / Empresario" }
    },
    "Tipo_Hook": {
      "select": { "name": "Hook 3: Identidad (José de Arimatea)" }
    },
    "Estado_Copy": {
      "status": { "name": "Listo para Grabar" }
    },
    "Script_Video": {
      "rich_text": [{ "text": { "content": "(HOOK - 0 a 5s): El mundo te dijo que para ser espiritual tenías que ser pobre...
(CUERPO): En la Biblia vemos a José de Arimatea..." } }]
    }
  }
}
```

---

## 4. DATABASE 3: Tareas y Roadmap de Lanzamiento (PM & Operaciones)

### 4.1. Propiedades y Esquema de Columnas

| Nombre de Propiedad (Key) | Tipo de Dato Notion | Opciones / Formato | Descripción |
| :--- | :--- | :--- | :--- |
| **Mision_Tarea** | `title` | Texto | Tarea operativa o misión semanal |
| **Responsable** | `select` | `Marcos`, `Joel`, `Agente IA` | Persona u agente a cargo |
| **Fase_Proyecto** | `select` | `MVP Setup (Día -4 a 0)`, `Lanzamiento Inminente`, `Operación Semanal` | Etapa operativa |
| **Fecha_Limite** | `date` | `YYYY-MM-DD` | Deadline estricto |
| **Estado** | `status` | `Pendiente`, `En Proceso`, `Completado` | Estado de avance |
| **Prioridad** | `select` | `🔴 Alta / Bloqueante`, `🟡 Media`, `🟢 Baja` | Nivel de urgencia |

### 4.2. Query JSON API Notion (`POST /v1/databases/{id}/query`) - Auditar Tareas Pendientes (Agente 3)

```json
{
  "filter": {
    "and": [
      {
        "property": "Estado",
        "status": { "does_not_equal": "Completado" }
      },
      {
        "property": "Prioridad",
        "select": { "equals": "🔴 Alta / Bloqueante" }
      }
    ]
  },
  "sorts": [
    {
      "property": "Fecha_Limite",
      "direction": "ascending"
    }
  ]
}
```

---

## 5. DATABASE 4: Control de Alumnos e Hitos (Students & Milestones)

### 5.1. Propiedades y Esquema de Columnas

| Nombre de Propiedad (Key) | Tipo de Dato Notion | Opciones / Formato | Descripción |
| :--- | :--- | :--- | :--- |
| **Nombre_Alumno** | `title` | Texto | Nombre y apellido del cliente |
| **Email** | `email` | `usuario@ejemplo.com` | Correo electrónico de acceso |
| **Plan_Suscripcion** | `select` | `Emprendedor ($15/mes)`, `Estratégico ($35/mes)`, `Elite ($95/mes)`, `Emprendedor Anual ($150/año)`, `Estratégico Anual ($350/año)`, `Elite Anual ($950/año)`, `Beca Solidaria` | Plan activo contratado |
| **Metodo_Pago** | `select` | `Transferencia Bancaria`, `Tarjeta / Link MP`, `PayPal / Stripe` | Forma de cobro procesada |
| **Pilar_Actual_Desbloqueado**| `number` | `1` a `7` | Control de Drip Content |
| **Kit_Fisico_Requerido** | `checkbox` | `true` / `false` | Indica si incluye Kit (Planes Anuales) |
| **Kit_Fisico_Despachado** | `checkbox` | `true` / `false` | Control de logística de envío |
| **Estado_Hito_Semanal** | `status` | `Al Día`, `Pendiente Entregable`, `Revision Mentor` | Auditoría de avance en el programa |

---

## 6. Configuración de Headers HTTP para la Integración Orca <-> Notion

Para que los agentes de Orca ejecuten llamadas API exitosas a Notion, deben enviar siempre los siguientes encabezados HTTP:

```http
Authorization: Bearer ntn_secret_YOUR_NOTION_INTEGRATION_TOKEN
Notion-Version: 2022-06-28
Content-Type: application/json
```
