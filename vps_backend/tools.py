"""tools.py - Tools para Function Calling de los LLMs del Squad.

Sprint 17: Los agentes pueden LEER archivos del búnker y páginas de Notion
en vez de recibir el contexto completo inyectado en el system prompt.

Tools disponibles:
  1. read_bunker_file(filename)  -> Lee archivo especifico del búnker
  2. list_bunker_files()          -> Lista archivos disponibles
  3. read_notion_page(page_id)    -> Lee pagina de Notion por ID

Uso:
  from tools import BUNKER_TOOLS, execute_tool

  result = execute_tool("read_bunker_file", {"filename": "06_onboarding_structure.md"})
"""

from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("tools")

# =============================================================================
# Constantes de paths
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUNKER_PATH = PROJECT_ROOT / "context_vault"

NOTION_API_KEY = os.getenv("NOTION_API_KEY", "").strip().strip('"').strip("'")
NOTION_API_VERSION = "2022-06-28"

# Whitelist de archivos del búnker que se pueden leer (seguridad)
BUNKER_FILE_WHITELIST = {
    "01_brand_manifesto.md",
    "02_tone_and_voice.md",
    "03_target_avatar.md",
    "04_product_matrix.md",
    "05_gold_standard_examples.md",
    "06_onboarding_structure.md",
    "07_guion_bienvenida_referencia.md",
}


# =============================================================================
# Implementación de las tools
# =============================================================================


def read_bunker_file(filename: str) -> dict[str, Any]:
    """Lee un archivo del búnker. Solo permite archivos en la whitelist.

    Returns:
        dict con keys: filename, content, chars, error (si falla)
    """
    if filename not in BUNKER_FILE_WHITELIST:
        return {
            "filename": filename,
            "error": f"Archivo '{filename}' no esta en la whitelist. Disponibles: {sorted(BUNKER_FILE_WHITELIST)}",
        }

    path = BUNKER_PATH / filename
    if not path.exists():
        return {"filename": filename, "error": f"Archivo no existe en {path}"}

    try:
        content = path.read_text(encoding="utf-8")
        return {
            "filename": filename,
            "content": content,
            "chars": len(content),
        }
    except Exception as exc:
        log.exception("Error leyendo bunker file")
        return {"filename": filename, "error": str(exc)}


def list_bunker_files() -> dict[str, Any]:
    """Lista los archivos del búnker disponibles (solo los de la whitelist).

    Returns:
        dict con keys: files (lista de dicts con name, chars)
    """
    files = []
    for name in sorted(BUNKER_FILE_WHITELIST):
        path = BUNKER_PATH / name
        if path.exists():
            files.append({"name": name, "chars": len(path.read_text(encoding="utf-8"))})
        else:
            files.append({"name": name, "chars": 0, "available": False})
    return {"files": files, "count": len(files)}


def read_notion_page(page_id: str) -> dict[str, Any]:
    """Lee una página de Notion por ID. Devuelve el titulo y los primeros
    2000 chars del contenido en texto plano.

    Args:
        page_id: ID de la pagina de Notion (formato UUID, con o sin guiones)

    Returns:
        dict con keys: page_id, title, content, error
    """
    if not NOTION_API_KEY:
        return {"error": "NOTION_API_KEY no configurada", "page_id": page_id}

    # Normalizar ID (agregar guiones si faltan)
    clean_id = page_id.replace("-", "")
    if len(clean_id) == 32:
        clean_id = f"{clean_id[:8]}-{clean_id[8:12]}-{clean_id[12:16]}-{clean_id[16:20]}-{clean_id[20:]}"

    try:
        # Get page metadata
        req = urllib.request.Request(
            f"https://api.notion.com/v1/pages/{clean_id}",
            method="GET",
        )
        req.add_header("Authorization", f"Bearer {NOTION_API_KEY}")
        req.add_header("Notion-Version", NOTION_API_VERSION)

        with urllib.request.urlopen(req, timeout=15) as resp:
            page = json.loads(resp.read())

        # Extract title
        title = ""
        for prop_val in page.get("properties", {}).values():
            if prop_val.get("type") == "title":
                for t in prop_val.get("title", []):
                    title += t.get("plain_text", "")
                break

        # Get blocks (children)
        req2 = urllib.request.Request(
            f"https://api.notion.com/v1/blocks/{clean_id}/children",
            method="GET",
        )
        req2.add_header("Authorization", f"Bearer {NOTION_API_KEY}")
        req2.add_header("Notion-Version", NOTION_API_VERSION)

        content_parts = []
        with urllib.request.urlopen(req2, timeout=15) as resp2:
            blocks = json.loads(resp2.read())
            for block in blocks.get("results", [])[:50]:
                btype = block.get("type", "")
                if btype == "paragraph":
                    for t in block["paragraph"].get("rich_text", []):
                        content_parts.append(t.get("plain_text", ""))
                elif btype == "heading_1":
                    for t in block["heading_1"].get("rich_text", []):
                        content_parts.append(f"\n# {t.get('plain_text', '')}")
                elif btype == "heading_2":
                    for t in block["heading_2"].get("rich_text", []):
                        content_parts.append(f"\n## {t.get('plain_text', '')}")
                elif btype == "heading_3":
                    for t in block["heading_3"].get("rich_text", []):
                        content_parts.append(f"\n### {t.get('plain_text', '')}")
                elif btype == "bulleted_list_item":
                    for t in block["bulleted_list_item"].get("rich_text", []):
                        content_parts.append(f"• {t.get('plain_text', '')}")
                elif btype == "callout":
                    for t in block["callout"].get("rich_text", []):
                        content_parts.append(f">> {t.get('plain_text', '')}")

        content = "\n".join(content_parts)
        # Truncar a 5000 chars para no saturar el contexto del LLM
        truncated = len(content) > 5000
        if truncated:
            content = content[:5000] + "\n\n[... truncated, total 5000 chars]"

        return {
            "page_id": page_id,
            "title": title,
            "content": content,
            "chars": len(content),
            "truncated": truncated,
        }
    except Exception as exc:
        log.exception("Error leyendo Notion page")
        return {"page_id": page_id, "error": str(exc)}


# =============================================================================
# Dispatcher
# =============================================================================


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Ejecuta una tool por nombre con los argumentos dados.

    Args:
        tool_name: nombre de la tool ("read_bunker_file", etc)
        arguments: dict de argumentos

    Returns:
        dict con el resultado de la tool (o dict con 'error' si falla)
    """
    if tool_name == "read_bunker_file":
        return read_bunker_file(arguments.get("filename", ""))
    elif tool_name == "list_bunker_files":
        return list_bunker_files()
    elif tool_name == "read_notion_page":
        return read_notion_page(arguments.get("page_id", ""))
    else:
        return {"error": f"Tool '{tool_name}' no existe"}


# =============================================================================
# Tool definitions (formato OpenAI/Vertex compatible)
# =============================================================================


BUNKER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_bunker_file",
            "description": (
                "Lee un archivo específico del búnker de contexto de Rompiendo Barreras. "
                "Usa esta tool SIEMPRE antes de generar contenido para conocer la estructura "
                "exacta, duración, objetivos y enfoque de la clase. "
                "Archivos disponibles: "
                "01_brand_manifesto.md (manifiesto de marca), "
                "02_tone_and_voice.md (voz pentagonal de Marcos), "
                "03_target_avatar.md (avatares 1 y 2), "
                "04_product_matrix.md (matriz de productos), "
                "05_gold_standard_examples.md (ejemplos de oro), "
                "06_onboarding_structure.md (estructura de las 8 clases de Onboarding), "
                "07_guion_bienvenida_referencia.md (guion de referencia del Video 1)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Nombre del archivo a leer (ej: '06_onboarding_structure.md')",
                        "enum": sorted(BUNKER_FILE_WHITELIST),
                    }
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_bunker_files",
            "description": (
                "Lista todos los archivos disponibles en el búnker de contexto. "
                "Usar primero esta tool para saber qué hay disponible."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_notion_page",
            "description": (
                "Lee una página de Notion por su ID. Devuelve el título y los primeros "
                "5000 chars del contenido. Útil para leer feedback de Marcos, "
                "verificar una idea existente, o leer el contenido de un guion previo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "ID de la página de Notion (formato UUID)",
                    }
                },
                "required": ["page_id"],
            },
        },
    },
]


# =============================================================================
# Convierte tools a formato Vertex Gemini
# =============================================================================


def tools_to_gemini_format(tools: list[dict]) -> list[dict]:
    """Convierte tools de formato OpenAI a formato Gemini (Vertex AI).

    OpenAI format:
        {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

    Gemini format:
        {"function_declarations": [{"name": ..., "description": ..., "parameters": ...}]}
    """
    declarations = []
    for tool in tools:
        if tool.get("type") == "function":
            func = tool["function"]
            declarations.append({
                "name": func["name"],
                "description": func["description"],
                "parameters": func["parameters"],
            })
    return [{"function_declarations": declarations}]


# =============================================================================
# Loop de agente (multi-turno tool calling)
# =============================================================================


def run_agent_loop(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    tools: list[dict] = None,
    max_iterations: int = 5,
    api_key: str = None,
    base_url: str = None,
    project: str = None,
    location: str = None,
) -> str:
    """Loop de agente: ejecuta el LLM con tool calling hasta que devuelva
    respuesta final (sin tool_calls) o se acaben las iteraciones.

    Returns:
        string con la respuesta final del LLM
    """
    import json
    import urllib.request
    import time

    if tools is None:
        tools = BUNKER_TOOLS

    if not api_key:
        api_key = os.getenv("MINIMAX_API_KEY", "").strip().strip('"').strip("'")
    if not api_key:
        return f"Error: API key no configurada para provider {provider}"

    messages = [{"role": "user", "content": user_prompt}]

    for iteration in range(max_iterations):
        log.info("agent_loop iter %d/%d (provider=%s model=%s)",
                 iteration + 1, max_iterations, provider, model)

        if provider == "vertex":
            response, tool_calls = _call_vertex_with_tools(
                system_prompt, messages, tools, project, location
            )
        elif provider == "minimax":
            response, tool_calls = _call_minimax_with_tools(
                system_prompt, messages, tools, api_key, base_url
            )
        else:
            return f"Error: provider '{provider}' no soportado"

        # Si no hay tool_calls, terminó
        if not tool_calls:
            return response

        # Si hay tool_calls, los ejecutamos y reenviamos
        log.info("agent_loop: LLM pidió %d tool calls", len(tool_calls))
        messages.append({
            "role": "assistant",
            "content": response or "",
            "tool_calls": tool_calls,
        })

        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            try:
                tool_args = json.loads(tc["function"]["arguments"])
            except Exception:
                tool_args = {}

            log.info("agent_loop: ejecutando tool %s con args %s", tool_name, tool_args)
            result = execute_tool(tool_name, tool_args)
            result_str = json.dumps(result, ensure_ascii=False)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_str,
            })

    return f"Error: max_iterations ({max_iterations}) alcanzado sin respuesta final"


def _call_vertex_with_tools(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    project: str = None,
    location: str = None,
) -> tuple[str, list[dict]]:
    """Llama a Vertex Gemini con tools. Retorna (content, tool_calls)."""
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request as GoogleRequest

    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip().strip('"').strip("'")
    project = project or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    location = location or os.getenv("GOOGLE_CLOUD_REGION", "global").strip()

    creds = service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    creds.refresh(GoogleRequest())

    # Vertex usa formato Gemini, no OpenAI
    gemini_tools = tools_to_gemini_format(tools)

    # Convertir mensajes OpenAI a Vertex format
    vertex_contents = []
    system_instruction = {"parts": [{"text": system_prompt}]}
    for msg in messages:
        role = msg["role"]
        if role == "user":
            vertex_contents.append({
                "role": "user",
                "parts": [{"text": msg.get("content", "")}],
            })
        elif role == "assistant":
            # Incluir function_call si hay
            parts = []
            if msg.get("content"):
                parts.append({"text": msg["content"]})
            for tc in msg.get("tool_calls", []):
                args = tc["function"]["arguments"]
                if isinstance(args, str):
                    args_str = args
                else:
                    args_str = json.dumps(args)
                parts.append({
                    "functionCall": {
                        "name": tc["function"]["name"],
                        "args": json.loads(args_str) if isinstance(args, str) else args,
                    }
                })
            vertex_contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            # Convertir respuesta de tool
            function_name = msg.get("name", "unknown")
            try:
                content = json.loads(msg["content"])
            except Exception:
                content = {"result": msg["content"]}
            vertex_contents.append({
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "name": function_name,
                        "response": content,
                    }
                }],
            })

    payload = {
        "contents": vertex_contents,
        "tools": gemini_tools,
        "systemInstruction": system_instruction,
    }

    url = (
        f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/{location}"
        f"/publishers/google/models/gemini-2.5-flash:generateContent"
    )
    req = urllib.request.Request(url, method="POST", data=json.dumps(payload).encode())
    req.add_header("Authorization", f"Bearer {creds.token}")
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())

    # Extraer contenido y function calls
    candidate = data.get("candidates", [{}])[0]
    parts = candidate.get("content", {}).get("parts", [])

    text_parts = []
    function_calls = []
    for i, part in enumerate(parts):
        if "text" in part:
            text_parts.append(part["text"])
        elif "functionCall" in part:
            fc = part["functionCall"]
            function_calls.append({
                "id": f"fc_{i}",
                "type": "function",
                "function": {
                    "name": fc["name"],
                    "arguments": json.dumps(fc.get("args", {})),
                },
            })

    return "".join(text_parts), function_calls


def _call_minimax_with_tools(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    api_key: str,
    base_url: str = None,
) -> tuple[str, list[dict]]:
    """Llama a MiniMax con tools via OpenAI-compatible API."""
    import json
    import urllib.request

    base_url = base_url or "https://api.minimaxi.chat/v1"
    url = f"{base_url}/chat/completions"

    payload = {
        "model": "minimax-m3",
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "tools": tools,
        "tool_choice": "auto",
    }

    req = urllib.request.Request(url, method="POST", data=json.dumps(payload).encode())
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())

    msg = data.get("choices", [{}])[0].get("message", {})
    content = msg.get("content", "") or ""
    tool_calls = msg.get("tool_calls") or []
    return content, tool_calls


def _get_api_key_env(provider: str) -> str:
    if provider == "minimax":
        return "MINIMAX_API_KEY"
    return ""
