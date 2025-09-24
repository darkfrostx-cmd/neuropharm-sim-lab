"""Configuration helpers for backend services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping, Optional, Tuple

import os
from urllib.parse import parse_qs, urlparse


@dataclass(slots=True)
class GraphBackendSettings:
    """Connection details for a single graph backend target."""

    backend: str = "memory"
    uri: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    options: MutableMapping[str, Any] = field(default_factory=dict)

    def normalized_backend(self) -> str:
        return (self.backend or "memory").lower()


@dataclass(slots=True)
class GraphConfig:
    """Configuration for the knowledge-graph persistence layer.

    ``GraphConfig`` now supports a *primary* backend and optional mirror
    targets.  All writes are replicated to the mirrors while reads are served
    from the primary.  This allows deployments to combine, for example, a
    Neo4j Aura instance with an ArangoDB document store for provenance-heavy
    queries without changing application code.
    """

    primary: GraphBackendSettings = field(default_factory=GraphBackendSettings)
    mirrors: Tuple[GraphBackendSettings, ...] = field(default_factory=tuple)

    @property
    def backend(self) -> str:
        """Compatibility shim for existing callers expecting ``backend``."""

        return self.primary.normalized_backend()

    @property
    def is_memory_only(self) -> bool:
        """Return ``True`` when all configured targets are in-memory stores."""

        return all(target.normalized_backend() == "memory" for target in self.iter_targets())

    def iter_targets(self) -> Tuple[GraphBackendSettings, ...]:
        """Return the primary target followed by any mirrors."""

        return (self.primary, *self.mirrors)

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        prefix: str = "GRAPH_",
    ) -> "GraphConfig":
        """Create a configuration object from environment variables.

        The parser understands both the legacy single-backend variables
        (``GRAPH_BACKEND``, ``GRAPH_URI`` …) and a richer mirroring syntax:

        ``GRAPH_MIRROR_<NAME>_BACKEND``
            Backend name for an additional replica. ``<NAME>`` can be any
            uppercase token (e.g. ``AURA``).

        ``GRAPH_MIRROR_<NAME>_URI`` etc.
            Connection parameters for the corresponding replica.  Optional
            ``GRAPH_MIRROR_<NAME>_OPT_*`` keys are folded into the
            ``options`` mapping.
        """

        env = env or os.environ

        def _parse_target(prefix_key: str) -> GraphBackendSettings:
            backend = env.get(f"{prefix_key}BACKEND", "memory").lower()
            uri = env.get(f"{prefix_key}URI")
            username = env.get(f"{prefix_key}USERNAME")
            password = env.get(f"{prefix_key}PASSWORD")
            database = env.get(f"{prefix_key}DATABASE")
            options: dict[str, Any] = {}
            for key, value in env.items():
                if key.startswith(f"{prefix_key}OPT_"):
                    option_key = key[len(f"{prefix_key}OPT_") :].lower()
                    options[option_key] = value
            return GraphBackendSettings(
                backend=backend,
                uri=uri,
                username=username,
                password=password,
                database=database,
                options=options,
            )

        primary = _parse_target(prefix)

        mirror_prefix = f"{prefix}MIRROR_"
        grouped: dict[str, dict[str, Any]] = {}
        for key, value in env.items():
            if not key.startswith(mirror_prefix):
                continue
            remainder = key[len(mirror_prefix) :]
            token, _, setting = remainder.partition("_")
            if not setting:
                continue
            token_key = token.upper()
            grouped.setdefault(token_key, {})[setting.upper()] = value

        mirrors: list[GraphBackendSettings] = []
        for token in sorted(grouped):
            settings = grouped[token]
            backend_name = str(settings.get("BACKEND", "memory")).lower()
            options = {k[4:].lower(): v for k, v in settings.items() if k.startswith("OPT_")}
            mirror = GraphBackendSettings(
                backend=backend_name,
                uri=settings.get("URI"),
                username=settings.get("USERNAME"),
                password=settings.get("PASSWORD"),
                database=settings.get("DATABASE"),
                options=options,
            )
            mirrors.append(mirror)

        return cls(primary=primary, mirrors=tuple(mirrors))


@dataclass(slots=True)
class VectorStoreConfig:
    """Connection information for the optional pgvector store."""

    url: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    schema: str = "neuropharm"
    table: str = "embedding_cache"
    options: MutableMapping[str, str] = field(default_factory=dict)
    pool_min: int = 1
    pool_max: int = 4
    sqlite_path: Optional[str] = ".cache/embeddings.sqlite"

    def is_configured(self) -> bool:
        """Return ``True`` when a connection URL or host has been supplied."""

        return bool((self.url or "").strip() or (self.host or "").strip())

    @property
    def dsn(self) -> Optional[str]:
        """Return the raw connection string when available."""

        return self.url

    def __post_init__(self) -> None:
        if self.pool_min > self.pool_max:
            self.pool_min, self.pool_max = self.pool_max, self.pool_min

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        prefix: str = "VECTOR_DB_",
    ) -> "VectorStoreConfig":
        """Parse vector-store credentials from environment variables."""

        env = env or os.environ
        url_keys = [
            f"{prefix}URL",
            f"{prefix}CONNECTION_STRING",
            "SUPABASE_DB_URL",
            "NEON_DB_URL",
            "DATABASE_URL",
        ]
        raw_url = next((env.get(key) for key in url_keys if env.get(key)), None)

        schema = env.get(f"{prefix}SCHEMA", "neuropharm")
        table = env.get(f"{prefix}TABLE", "embedding_cache")

        def _parse_pool(value: str, default: int) -> int:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return default
            return parsed if parsed > 0 else default

        pool_min = _parse_pool(env.get(f"{prefix}POOL_MIN", "1"), 1)
        pool_max = _parse_pool(env.get(f"{prefix}POOL_MAX", "4"), 4)

        host: Optional[str] = None
        port: Optional[int] = None
        database: Optional[str] = None
        username: Optional[str] = None
        password: Optional[str] = None
        options: dict[str, str] = {}

        if raw_url:
            parsed = urlparse(raw_url)
            host = parsed.hostname or None
            port = parsed.port
            database = parsed.path.lstrip("/") or None
            username = parsed.username or None
            password = parsed.password or None
            query_options = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
            options.update(query_options)

        opt_prefix = f"{prefix}OPT_"
        for key, value in env.items():
            if key.startswith(opt_prefix):
                option_key = key[len(opt_prefix) :].lower()
                options[option_key] = value

        sqlite_path = env.get(f"{prefix}SQLITE_PATH")

        return cls(
            url=raw_url,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            schema=schema,
            table=table,
            options=options,
            pool_min=pool_min,
            pool_max=pool_max,
            sqlite_path=sqlite_path or ".cache/embeddings.sqlite",
        )


DEFAULT_GRAPH_CONFIG = GraphConfig.from_env()
DEFAULT_VECTOR_STORE_CONFIG = VectorStoreConfig.from_env()

