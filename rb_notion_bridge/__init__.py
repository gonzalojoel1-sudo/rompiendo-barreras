"""rb_notion_bridge - Bridge bidireccional entre Orca y la API de Notion.

Sprint 1. Provee:
    NotionBridgeConfig    -> Configuracion (env-based).
    NotionClient          -> Wrapper del SDK con retry/backoff.
    NotionTransformer     -> Mapeo Orca dict <-> Notion property objects.
    NotionBridgeService   -> API de alto nivel que consumen los agentes de Orca.

Uso tipico desde un agente de Orca:

    from rb_notion_bridge import NotionBridgeService, NotionBridgeConfig
    from rb_notion_bridge.client import NotionClient
    from rb_notion_bridge.transformer import NotionTransformer

    cfg = NotionBridgeConfig.from_env()
    client = NotionClient(cfg)
    database = client.raw_client.databases.retrieve(database_id=DB_ID)
    transformer = NotionTransformer.from_database(database)
    service = NotionBridgeService(client, transformer)

    items = service.fetch_database_items(DB_ID, filter={...}, sorts=[...])
    page  = service.create_notion_page(DB_ID, {"Titulo": "...", "Estado": "Pendiente"})
    service.update_notion_page(page["id"], {"Estado": "En Proceso"})
"""

from .client import NotionClient
from .config import NotionBridgeConfig
from .exceptions import (
    NotionAuthError,
    NotionBridgeError,
    NotionNotFoundError,
    NotionRateLimitError,
    NotionServerError,
    NotionValidationError,
)
from .transformer import NotionTransformer
from .service import NotionBridgeService
from .cache import SchemaCache, CacheStats
from .cached_service import CachedSchemaService

__all__ = [
    "NotionClient",
    "NotionBridgeConfig",
    "NotionBridgeService",
    "NotionTransformer",
    "SchemaCache",
    "CacheStats",
    "CachedSchemaService",
    "NotionBridgeError",
    "NotionAuthError",
    "NotionNotFoundError",
    "NotionValidationError",
    "NotionRateLimitError",
    "NotionServerError",
]
