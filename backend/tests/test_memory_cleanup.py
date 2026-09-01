from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_rag_python_package_removed():
    legacy_files = sorted((ROOT / "app" / "rag").glob("*.py"))
    assert legacy_files == []


def test_legacy_rag_admin_route_removed():
    assert not (ROOT / "app" / "routers" / "admin_rag.py").exists()
    assert not (ROOT / "app" / "services" / "rag_stats.py").exists()
    main_text = (ROOT / "app" / "main.py").read_text()
    assert "admin_rag" not in main_text


def test_legacy_rag_models_and_config_removed():
    import app.models as models
    from app.config import settings

    assert not hasattr(models, "SourceType")
    assert not hasattr(models, "Embedding")
    assert not hasattr(models, "KnowledgeArticle")

    for name in dir(settings):
        assert not name.startswith("rag_")
    assert not hasattr(settings, "admin_api_token")


def test_memweaver_migration_moves_then_drops_legacy_tables():
    migration = (ROOT / "alembic" / "versions" / "20260613_01_memweaver_memory.py").read_text()

    assert "INSERT INTO memory_nodes" in migration
    assert "FROM embeddings" in migration
    assert "knowledge_base" in migration
    assert "op.drop_table(\"embeddings\")" in migration
    assert "op.drop_table(\"knowledge_articles\")" in migration


def test_legacy_rag_tests_removed():
    assert sorted(ROOT.glob("tests/test_rag*.py")) == []
