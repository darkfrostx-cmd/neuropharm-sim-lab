"""Configuration helpers for backend services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping, Optional, Tuple

import os


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


DEFAULT_GRAPH_CONFIG = GraphConfig.from_env()

