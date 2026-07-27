"""llm_client.py - Cliente unificado multi-proveedor para el Squad de agentes.

Soporta 3 proveedores:
    - OpenCode Go API (modelos opencode/*)        -> OpenAI-compatible chat completions
    - MiniMax API    (modelos minimax/*)        -> OpenAI-compatible chat completions
    - Google Cloud API (modelos google/*)       -> Gemini generateContent (con soporte para Claude via Vertex)

La funcion principal es generate_completion(agent_role, system, user), que
mapea el rol del subagente al (proveedor, modelo) configurado via env vars
con defaults razonables (ver DEFAULT_AGENT_MODELS).

Variables de entorno:
    OPENCODE_GO_API_KEY              (requerida para modelos opencode/*)
    MINIMAX_API_KEY                  (requerida para modelos minimax/*)
    GOOGLE_CLOUD_API_KEY             (requerida para modelos google/*)
    SQUAD_<ROLE>_MODEL               (override por agente, formato provider/model)
    <PROVIDER>_BASE_URL              (override de URL base por proveedor)

Roles reconocidos (default models):
    trend_hunter -> opencode/deepseek-v4-flash
    strategist   -> minimax/minimax-m3
    copywriter   -> google/claude-3.5-sonnet
    guardian     -> google/gemini-3.1-flash-lite
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

# Sanitiza trazas de razonamiento de modelos que emiten <think>...</think>
# (MiniMax-M3, MiniMax-M2.7, Doubao, DeepSeek-R1 distill, etc.) antes del JSON.
# Tambien remueve fences de markdown (```json ... ```) que envuelven el JSON.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_MARKDOWN_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n|\n```\s*$", re.MULTILINE)


def sanitize_content(content: str) -> str:
    """Limpia trazas de pensamiento y wrappers de markdown de un response LLM.

    Modelos como MiniMax-M3, MiniMax-M2.7, Doubao, DeepSeek-R1 distill emiten
    bloques<think>...</think> (a veces multilinea) antes del JSON. Tambien
    pueden envolver el JSON en ```json ... ```. Esta funcion los elimina para que
    json.loads() funcione.

    Es defensiva: si no encuentra los patrones, devuelve el content intacto.
    Tambien defensiva: si el input no es string (p.ej. un dict), lo serializa
    a JSON como fallback.
    """
    if not content:
        return content
    if not isinstance(content, str):
        # Fallback: si el LLM devolvio un dict (raro pero posible), serializarlo
        try:
            import json as _json
            return _json.dumps(content, ensure_ascii=False)
        except Exception:
            return str(content)
    # 1) Remover bloques<think>...</think>
    content = _THINK_BLOCK_RE.sub("", content)
    # 2) Remover fences de markdown ```json ... ``` o ``` ... ```
    content = _MARKDOWN_FENCE_RE.sub("", content)
    # 3) Trim de whitespace redundante
    return content.strip()

# =============================================================================
# Configuracion de proveedores
# =============================================================================

PROVIDER_CONFIGS: dict[str, dict[str, str]] = {
    "opencode": {
        "api_key_env": "OPENCODE_GO_API_KEY",
        "base_url_env": "OPENCODE_BASE_URL",
        "default_base_url": "https://opencode.ai/zen/v1",
        "style": "openai",
    },
    "minimax": {
        "api_key_env": "MINIMAX_API_KEY",
        "base_url_env": "MINIMAX_BASE_URL",
        # URL oficial corregida (sprint 6)
        "default_base_url": "https://api.minimaxi.chat/v1",
        "style": "openai",
    },
    "google": {
        "api_key_env": "GOOGLE_CLOUD_API_KEY",
        "base_url_env": "GOOGLE_CLOUD_BASE_URL",
        # Google Generative Language API REST nativa (sprint 7).
        # Acepta claves de Google Cloud Console (formato AQ.Ab8...) y claves
        # de AI Studio (formato AIzaSy...). No usa Bearer; la key va como
        # query param y como header x-goog-api-key.
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "style": "gemini",
    },
    "vertex": {
        "credentials_path_env": "GOOGLE_APPLICATION_CREDENTIALS",
        "project_env": "GOOGLE_CLOUD_PROJECT",
        "region_env": "GOOGLE_CLOUD_REGION",
        "default_region": "global",          # CONFIRMADO: models Vertex Express viven en global
        "style": "vertex",
    },
}

# Chain de fallback por agente (sprint 14).
# Cada agente tiene una lista de (provider, model) en orden de prioridad.
# - trend_hunter: MiniMax M2.7-highspeed (ultra-rapido para escaneo de patrones)
# - strategist: MiniMax M3 (razonamiento profundo, contexto largo)
# - copywriter: Gemini 3.5 Flash (working) -> Claude Sonnet 4.5 (gold standard)
#   -> MiniMax M3 (safety net)
# - guardian: MiniMax M2.7-highspeed (validacion rapida) -> Gemini Flash-Lite
#
# Override por env var: SQUAD_<ROLE>_MODEL=provider/model (single model)
# o SQUAD_<ROLE>_MODEL_CHAIN=p1/m1,p2/m2,p3/m3 (custom chain)
DEFAULT_AGENT_CHAINS: dict[str, list[tuple[str, str]]] = {
    # Plan A (validado 26-Jul-2026):
    #   - trend_hunter:    Gemini 2.5 flash-lite (1.13s, sin thinking)
    #   - strategist:      Gemini 3.5 flash     (4.99s, razonamiento)
    #   - copywriter:      Gemini 2.5 flash     (5.41s, calidad-precio)
    #   - guardian:        Gemini 2.5 flash-lite (1.13s, validacion rapida)
    #
    # Fallbacks: MiniMax con modelos verificados (MiniMax-Text-01 sin thinking).
    "trend_hunter": [
        ("vertex", "gemini-2.5-flash-lite"),     # PRIMARY: 1.13s
        ("minimax", "MiniMax-Text-01"),         # FALLBACK: 1.50s sin thinking
        ("minimax", "minimax-m2.7-highspeed"),  # FALLBACK: 1.98s con thinking
    ],
    "strategist": [
        ("vertex", "gemini-3.5-flash"),          # PRIMARY: 4.99s razonamiento
        ("minimax", "minimax-m3"),              # FALLBACK: 3.81s con thinking
    ],
    "copywriter": [
        ("vertex", "gemini-2.5-flash"),          # PRIMARY: 5.41s calidad-precio
        ("minimax", "minimax-m3"),              # FALLBACK: 3.81s con thinking
    ],
    "guardian": [
        ("vertex", "gemini-2.5-flash-lite"),     # PRIMARY: 1.13s
        ("minimax", "MiniMax-Text-01"),         # FALLBACK: 1.50s
    ],
}

# Roles que la funcion de stub (en run_hybrid_squad) reconoce
KNOWN_ROLES = set(DEFAULT_AGENT_CHAINS.keys())


# =============================================================================
# Helpers de configuracion
# =============================================================================

def _mask(key: str) -> str:
    if len(key) < 12:
        return "***"
    return f"{key[:6]}...{key[-4:]}"


def _get_provider_config(provider: str) -> dict[str, str]:
    if provider not in PROVIDER_CONFIGS:
        raise ValueError(f"Proveedor desconocido: {provider!r}. Soportados: {list(PROVIDER_CONFIGS)}")
    cfg = PROVIDER_CONFIGS[provider]

    # Vertex AI usa service account JSON, no API key.
    if cfg.get("style") == "vertex":
        creds_path = os.getenv(cfg["credentials_path_env"], "").strip().strip('"').strip("'").strip()
        if not creds_path:
            raise ValueError(
                f"Variable de entorno {cfg['credentials_path_env']} es obligatoria para vertex "
                "(path al JSON de service account)."
            )
        if not os.path.exists(creds_path):
            raise ValueError(
                f"Archivo de credenciales vertex no encontrado: {creds_path}"
            )
        # Auto-detectar project_id del JSON si GOOGLE_CLOUD_PROJECT no esta seteado
        project = os.getenv(cfg["project_env"], "").strip().strip('"').strip("'").strip()
        if not project:
            try:
                with open(creds_path, "r", encoding="utf-8") as f:
                    import json as _json
                    project = _json.load(f).get("project_id", "")
            except Exception as exc:
                raise ValueError(
                    f"No se pudo leer project_id del JSON ({cfg['project_env']} no seteado): {exc}"
                ) from exc
        if not project:
            raise ValueError(
                f"project_id no encontrado: setea {cfg['project_env']} o incluye project_id en el JSON."
            )
        region = os.getenv(cfg["region_env"], cfg["default_region"]).strip().strip('"').strip("'").strip()
        return {
            "provider": provider,
            "style": cfg["style"],
            "credentials_path": creds_path,
            "project_id": project,
            "region": region,
        }

    base_url = os.getenv(cfg["base_url_env"], cfg["default_base_url"]).rstrip("/")
    api_key = os.getenv(cfg["api_key_env"], "").strip().strip('"').strip("'").strip()
    return {
        "provider": provider,
        "api_key_env": cfg["api_key_env"],
        "api_key": api_key,
        "base_url": base_url,
        "style": cfg["style"],
    }


def _get_agent_chain(agent_role: str) -> list[tuple[str, str]]:
    """Devuelve la cadena de fallback (provider, model) para un agente.

    Orden de prioridad:
      1. SQUAD_<ROLE>_MODEL_CHAIN (env var con formato p1/m1,p2/m2,p3/m3)
      2. SQUAD_<ROLE>_MODEL (env var single-model, se convierte en chain de 1)
      3. DEFAULT_AGENT_CHAINS[role]
    """
    chain_env = os.getenv(f"SQUAD_{agent_role.upper()}_MODEL_CHAIN", "").strip()
    if chain_env:
        chain = []
        for entry in chain_env.split(","):
            entry = entry.strip()
            if "/" not in entry:
                raise ValueError(
                    f"SQUAD_{agent_role.upper()}_MODEL_CHAIN debe tener formato "
                    f"provider/model,p2/m2, recibido: {entry!r}"
                )
            p, m = entry.split("/", 1)
            chain.append((p, m))
        if chain:
            return chain

    single_env = os.getenv(f"SQUAD_{agent_role.upper()}_MODEL", "").strip()
    if single_env:
        if "/" not in single_env:
            raise ValueError(
                f"SQUAD_{agent_role.upper()}_MODEL debe tener formato provider/model, "
                f"recibido: {single_env!r}"
            )
        p, m = single_env.split("/", 1)
        return [(p, m)]

    if agent_role in DEFAULT_AGENT_CHAINS:
        return DEFAULT_AGENT_CHAINS[agent_role]

    raise ValueError(
        f"agent_role desconocido: {agent_role!r}. "
        f"Soportados: {sorted(DEFAULT_AGENT_CHAINS)}"
    )


def resolve_agent(agent_role: str) -> dict[str, str]:
    """Resuelve el primer (provider, model) de la cadena para un rol.

    Deprecated: usar _get_agent_chain() para la cadena completa.
    Mantenido por backward-compat.
    """
    chain = _get_agent_chain(agent_role)
    if not chain:
        raise ValueError(f"agent_role '{agent_role}' no tiene chain definido")
    provider, model = chain[0]
    cfg = _get_provider_config(provider)
    if cfg.get("style") != "vertex" and not cfg.get("api_key"):
        raise ValueError(
            f"API key ausente: {cfg['api_key_env']} "
            f"(necesaria para {agent_role} -> {provider}/{model})"
        )
    cfg["model"] = model
    return cfg


# =============================================================================
# Conectores por proveedor
# =============================================================================

def _call_openai_style(cfg: dict, system_prompt: str, user_prompt: str, json_mode: bool) -> str:
    """Llamada OpenAI-compatible (OpenCode Go y MiniMax).

    Para MiniMax, añade el header `MM-Group-Id` si la variable de entorno
    `MINIMAX_GROUP_ID` esta presente (requerido por algunos planes).

    El nombre del modelo se normaliza: si viene con prefijo 'provider/' se
    elimina (ej. 'opencode/deepseek-v4-flash' -> 'deepseek-v4-flash').
    """
    model_name = cfg["model"]
    if "/" in model_name:
        model_name = model_name.split("/", 1)[1]

    body: dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    headers: dict[str, str] = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    # Header opcional de MiniMax para suscripciones con Group ID
    if cfg.get("provider") == "minimax":
        group_id = os.getenv("MINIMAX_GROUP_ID", "").strip().strip('"').strip("'").strip()
        if group_id:
            headers["MM-Group-Id"] = group_id

    response = requests.post(
        f"{cfg['base_url']}/chat/completions",
        headers=headers,
        json=body,
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    if "choices" not in data or not data["choices"]:
        raise LLMError(f"Respuesta sin 'choices': {str(data)[:200]}")
    return data["choices"][0]["message"]["content"]


def _call_gemini(cfg: dict, system_prompt: str, user_prompt: str, json_mode: bool) -> str:
    """Llamada a la API REST nativa de Google Generative Language.

    Soporta claves de Google Cloud Console (formato AQ.Ab8...) y de
    AI Studio (formato AIzaSy...). La key se envia en:
      - Query param: ?key={GOOGLE_CLOUD_API_KEY}
      - Header: x-goog-api-key: {GOOGLE_CLOUD_API_KEY}

    Body formato Gemini nativo:
      {"contents": [{"parts": [{"text": "SYSTEM_PROMPT + USER_PROMPT"}]}]}

    Respuesta: candidates[0].content.parts[0].text
    """
    model_name = cfg["model"]
    if "/" in model_name:
        model_name = model_name.split("/", 1)[1]

    # Combinar system + user en un solo text segun spec del usuario
    combined_text = f"{system_prompt}\n\n{user_prompt}"

    body: dict[str, Any] = {
        "contents": [{"parts": [{"text": combined_text}]}],
    }
    if json_mode:
        body["generationConfig"] = {"responseMimeType": "application/json"}

    url = f"{cfg['base_url']}/models/{model_name}:generateContent"
    response = requests.post(
        url,
        params={"key": cfg["api_key"]},
        headers={
            "x-goog-api-key": cfg["api_key"],
            "Content-Type": "application/json",
        },
        json=body,
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise LLMError(f"Google API sin candidates: {str(data)[:300]}")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise LLMError(f"Google API sin parts: {str(data)[:300]}")
    text = parts[0].get("text", "")
    if not text:
        raise LLMError(f"Google API text vacio: {str(data)[:300]}")
    return text


def _call_vertex(cfg: dict, system_prompt: str, user_prompt: str, json_mode: bool) -> str:
    """Llamada a Vertex AI (Google Cloud) con autenticacion por service account.

    Requiere un JSON de service account (GOOGLE_APPLICATION_CREDENTIALS).
    El project_id y la region se leen del .env o se auto-detectan del JSON.

    Endpoint REST:
      POST https://{region}-aiplatform.googleapis.com/v1/projects/{project}/
           locations/{region}/publishers/google/models/{model}:generateContent

    Auth: Bearer con OAuth2 access token del service account.
    """
    # Importacion lazy: google-auth solo se necesita para vertex
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request as GoogleRequest

    model_name = cfg["model"]
    if "/" in model_name:
        model_name = model_name.split("/", 1)[1]

    # Obtener access token del service account
    creds = service_account.Credentials.from_service_account_file(
        cfg["credentials_path"],
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    creds.refresh(GoogleRequest())
    token = creds.token

    combined_text = f"{system_prompt}\n\n{user_prompt}"
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": combined_text}]}],
    }
    if json_mode:
        body["generationConfig"] = {"responseMimeType": "application/json"}

    region = cfg["region"]
    project = cfg["project_id"]
    # Para region=global, el host NO lleva "-global" (es la URL global canonica).
    if region == "global":
        host = "https://aiplatform.googleapis.com"
    else:
        host = f"https://{region}-aiplatform.googleapis.com"
    url = (
        f"{host}/v1/projects/{project}"
        f"/locations/{region}/publishers/google/models/{model_name}:generateContent"
    )
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise LLMError(f"Vertex AI sin candidates: {str(data)[:300]}")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise LLMError(f"Vertex AI sin parts: {str(data)[:300]}")
    text = parts[0].get("text", "")
    if not text:
        raise LLMError(f"Vertex AI text vacio: {str(data)[:300]}")
    return text


def _call_anthropic_via_vertex(cfg: dict, system_prompt: str, user_prompt: str, json_mode: bool) -> str:
    """Llamada a Claude via Vertex AI (endpoint :rawPredict, formato Anthropic).

    Body formato Anthropic nativo:
      {"anthropic_version": "vertex-2023-10-16",
       "messages": [{"role": "user", "content": "..."}],
       "max_tokens": ...,
       "system": "..." (opcional)}

    Respuesta: {"content": [{"text": "..."}], "usage": {...}}
    """
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request as GoogleRequest

    model_name = cfg["model"]
    if "/" in model_name:
        model_name = model_name.split("/", 1)[1]

    creds = service_account.Credentials.from_service_account_file(
        cfg["credentials_path"],
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    creds.refresh(GoogleRequest())

    project = cfg["project_id"]
    region = cfg.get("region", "global")
    if region == "global":
        host = "https://aiplatform.googleapis.com"
    else:
        host = f"https://{region}-aiplatform.googleapis.com"

    body: dict[str, Any] = {
        "anthropic_version": "vertex-2023-10-16",
        "messages": [{"role": "user", "content": user_prompt}],
        "max_tokens": 4096,
    }
    if system_prompt:
        body["system"] = system_prompt

    url = f"{host}/v1/projects/{project}/locations/{region}/publishers/anthropic/models/{model_name}:rawPredict"
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    content = data.get("content", [])
    if not content:
        raise LLMError(f"Vertex Anthropic sin content: {str(data)[:300]}")
    text = content[0].get("text", "")
    if not text:
        raise LLMError(f"Vertex Anthropic text vacio: {str(data)[:300]}")
    return text


def _dispatch(cfg: dict, system_prompt: str, user_prompt: str, json_mode: bool) -> str:
    """Despacha al caller correcto segun el estilo del proveedor."""
    style = cfg.get("style")
    if style == "vertex":
        # Anthropic via Vertex AI usa endpoint y formato distintos
        if "anthropic" in cfg.get("model", "").lower():
            return _call_anthropic_via_vertex(cfg, system_prompt, user_prompt, json_mode)
        return _call_vertex(cfg, system_prompt, user_prompt, json_mode)
    if style == "gemini":
        return _call_gemini(cfg, system_prompt, user_prompt, json_mode)
    return _call_openai_style(cfg, system_prompt, user_prompt, json_mode)


def _call_one(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    json_mode: bool,
    max_retries: int,
) -> str:
    """Llama a un (provider, model) especifico con retry interno + backoff."""
    cfg = _get_provider_config(provider)
    cfg["model"] = model

    last_exc: Exception | None = None
    failure_count = 0
    max_failures = 2

    for attempt in range(1, max_retries + 3):
        try:
            return _dispatch(cfg, system_prompt, user_prompt, json_mode)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            body = exc.response.text[:200] if exc.response is not None else str(exc)
            if 500 <= status < 600 and attempt <= max_retries:
                delay = 0.5 * (2 ** (attempt - 1))
                log.warning(
                    "llm_call attempt=%d status=%d retry_in=%.1fs body=%s",
                    attempt, status, delay, body,
                )
                time.sleep(delay)
                last_exc = exc
                failure_count += 1
                if failure_count >= max_failures:
                    raise LLMError(f"Circuit breaker abierto tras {failure_count} fallos")
                continue
            raise LLMError(
                f"{provider}/{model} -> HTTP {status}: {body}"
            ) from exc
        except requests.RequestException as exc:
            if attempt <= max_retries:
                delay = 0.5 * (2 ** (attempt - 1))
                log.warning(
                    "llm_call network_error attempt=%d retry_in=%.1fs err=%s",
                    attempt, delay, exc,
                )
                time.sleep(delay)
                last_exc = exc
                failure_count += 1
                if failure_count >= max_failures:
                    raise LLMError(f"Circuit breaker abierto tras {failure_count} fallos")
                continue
            raise LLMError(f"{provider}/{model}: {exc}") from exc
    raise LLMError(f"{provider}/{model}: failed after retries: {last_exc}")


# =============================================================================
# API publica
# =============================================================================

class LLMError(RuntimeError):
    """Error llamando a un proveedor LLM."""


def generate_completion(
    agent_role: str,
    system_prompt: str,
    user_prompt: str,
    json_mode: bool = True,
    max_retries: int = 2,
) -> str:
    """Llama al modelo del subagente, iterando sobre su chain de fallback.

    El chain se obtiene con _get_agent_chain(agent_role) y consiste en una
    lista de (provider, model) en orden de prioridad. Se prueba cada uno
    hasta que uno responda con exito. Si todos fallan, se eleva LLMError
    con el ultimo error capturado.

    Args:
        agent_role: uno de trend_hunter, strategist, copywriter, guardian.
        system_prompt: instrucciones del sistema.
        user_prompt: input especifico de la tarea.
        json_mode: True para pedir respuesta JSON.
        max_retries: reintentos por cada modelo del chain.

    Returns:
        String con la respuesta. Devuelve thinking traces y markdown fences
        saneados (sanitize_content). Pensado para strings JSON.
    """
    chain = _get_agent_chain(agent_role)
    log.info(
        "llm_client.generate_completion role=%s chain=%s",
        agent_role, [(p, m) for p, m in chain],
    )

    last_error: Exception | None = None
    for provider, model in chain:
        try:
            content = _call_one(provider, model, system_prompt, user_prompt, json_mode, max_retries)
            return sanitize_content(content)
        except LLMError as exc:
            last_error = exc
            log.warning(
                "  chain step failed role=%s provider=%s model=%s err=%s",
                agent_role, provider, model, str(exc)[:200],
            )
            continue

    raise last_error or LLMError(
        f"Todos los modelos del chain de '{agent_role}' fallaron. "
        f"Chain: {[(p, m) for p, m in chain]}"
    )


# =============================================================================
# Utilidades
# =============================================================================

def list_agent_roles() -> list[dict[str, str]]:
    """Lista los roles conocidos y su chain de fallback efectiva."""
    out: list[dict[str, str]] = []
    for role in DEFAULT_AGENT_CHAINS:
        try:
            chain = _get_agent_chain(role)
            first = chain[0] if chain else ("?", "?")
            out.append({
                "role": role,
                "provider": first[0],
                "model": first[1],
                "chain_length": len(chain),
                "chain": [{"provider": p, "model": m} for p, m in chain],
                "available": True,
            })
        except ValueError as exc:
            out.append({
                "role": role,
                "provider": "?",
                "model": "?",
                "available": False,
                "error": str(exc),
            })
    return out


def mask_key(key: str) -> str:
    return _mask(key)


__all__ = [
    "LLMError",
    "generate_completion",
    "list_agent_roles",
    "resolve_agent",
    "mask_key",
    "sanitize_content",
    "PROVIDER_CONFIGS",
    "DEFAULT_AGENT_CHAINS",
    "KNOWN_ROLES",
]
