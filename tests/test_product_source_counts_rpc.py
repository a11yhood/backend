"""GET /api/products/sources must use the get_product_source_counts() RPC.

If the function is missing, the endpoint silently falls back to paging through
every product, so this checks that the products table is never read directly.
Needs migrations/20261101_add_get_product_source_counts.sql applied to the test project.
"""
from fastapi.testclient import TestClient

from main import app
from services.database import get_db


class _RecordingDb:
    """Delegates to the real test DB and records which tables/RPCs were used."""

    def __init__(self, db):
        self._db = db
        self.tables = []
        self.rpcs = []

    def table(self, name):
        self.tables.append(name)
        return self._db.table(name)

    def rpc(self, name, *args, **kwargs):
        self.rpcs.append(name)
        return self._db.rpc(name, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._db, name)


def test_sources_endpoint_uses_rpc_not_product_paging(clean_database):
    recorder = _RecordingDb(clean_database)
    app.dependency_overrides[get_db] = lambda: recorder
    try:
        response = TestClient(app).get("/api/products/sources")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert recorder.rpcs == ["get_product_source_counts"]
    assert "products" not in recorder.tables
