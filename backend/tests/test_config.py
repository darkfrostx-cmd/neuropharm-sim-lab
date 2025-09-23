from backend.config import GraphConfig, VectorStoreConfig


def test_graph_config_supports_mirrors() -> None:
    env = {
        "GRAPH_BACKEND": "neo4j",
        "GRAPH_URI": "neo4j+s://primary",
        "GRAPH_USERNAME": "neo",
        "GRAPH_PASSWORD": "pass",
        "GRAPH_MIRROR_A_BACKEND": "arangodb",
        "GRAPH_MIRROR_A_URI": "https://arangodb.example",
        "GRAPH_MIRROR_A_DATABASE": "brainos",
        "GRAPH_MIRROR_A_OPT_TLS": "true",
    }

    config = GraphConfig.from_env(env)

    assert config.backend == "neo4j"
    assert not config.is_memory_only
    assert config.primary.uri == "neo4j+s://primary"
    assert config.primary.username == "neo"
    assert len(config.mirrors) == 1
    mirror = config.mirrors[0]
    assert mirror.backend == "arangodb"
    assert mirror.uri == "https://arangodb.example"
    assert mirror.database == "brainos"
    assert mirror.options.get("tls") == "true"


def test_vector_config_parses_connection_url() -> None:
    env = {
        "VECTOR_DB_URL": "postgresql://user:pass@example.com:5432/neuro?sslmode=require&application_name=worker",
        "VECTOR_DB_SCHEMA": "custom",
        "VECTOR_DB_TABLE": "embedding_cache",
        "VECTOR_DB_POOL_MIN": "2",
        "VECTOR_DB_POOL_MAX": "8",
    }

    config = VectorStoreConfig.from_env(env)

    assert config.is_configured()
    assert config.host == "example.com"
    assert config.port == 5432
    assert config.database == "neuro"
    assert config.username == "user"
    assert config.password == "pass"
    assert config.schema == "custom"
    assert config.table == "embedding_cache"
    assert config.options["sslmode"] == "require"
    assert config.options["application_name"] == "worker"
    assert config.pool_min == 2
    assert config.pool_max == 8


def test_vector_config_falls_back_to_supabase_keys() -> None:
    env = {
        "SUPABASE_DB_URL": "postgresql://sb_user:sb_pass@supabase.db:6543/postgres",
        "VECTOR_DB_TABLE": "custom_vectors",
        "VECTOR_DB_POOL_MIN": "7",
        "VECTOR_DB_POOL_MAX": "3",
    }

    config = VectorStoreConfig.from_env(env)

    assert config.is_configured()
    assert config.host == "supabase.db"
    assert config.port == 6543
    assert config.database == "postgres"
    assert config.table == "custom_vectors"
    # pool_min greater than pool_max swaps the values during normalisation
    assert config.pool_min == 3
    assert config.pool_max == 7


def test_vector_config_opt_overrides() -> None:
    env = {
        "VECTOR_DB_URL": "postgresql://user:pass@host/db",
        "VECTOR_DB_OPT_SSLMODE": "verify-full",
        "VECTOR_DB_OPT_TARGET_SESSION_ATTRS": "read-write",
    }

    config = VectorStoreConfig.from_env(env)

    assert config.options["sslmode"] == "verify-full"
    assert config.options["target_session_attrs"] == "read-write"
