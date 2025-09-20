"""Configuration helpers for backend services."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Mapping, MutableMapping, Optional


@dataclass(slots=True)
class GraphConfig:
    """Configuration for the knowledge graph persistence layer.

    Parameters
    ----------
    backend:
        Name of the backend to use. Supported values are ``"memory"``,
        ``"neo4j"``, and ``"arangodb"``.
    uri:
        Connection URI for the database. For AuraDB this should follow the
        ``neo4j+s://`` scheme. For ArangoDB use the HTTP endpoint.
    username / password:
        Credentials used when establishing a database connection. They are
        optional so the configuration can also describe anonymous/free-tier
        setups.
    database:
        Optional database name or graph namespace.
    options:
        Extra keyword arguments understood by the concrete backend driver.
    """

    backend: str = "memory"
    uri: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    options: MutableMapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        prefix: str = "GRAPH_",
    ) -> "GraphConfig":
        """Create a configuration object from environment variables."""

        env = env or os.environ
        backend = env.get(f"{prefix}BACKEND", "memory").lower()
        uri = env.get(f"{prefix}URI")
        username = env.get(f"{prefix}USERNAME")
        password = env.get(f"{prefix}PASSWORD")
        database = env.get(f"{prefix}DATABASE")
        options: dict[str, Any] = {}
        for key, value in env.items():
            if key.startswith(prefix + "OPT_"):
                option_key = key[len(prefix + "OPT_") :].lower()
                options[option_key] = value
        return cls(
            backend=backend,
            uri=uri,
            username=username,
            password=password,
            database=database,
            options=options,
        )


DEFAULT_GRAPH_CONFIG = GraphConfig.from_env()
