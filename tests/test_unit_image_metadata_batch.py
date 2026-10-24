"""Unit tests for resolve_image_metadata_batch (one query per chunk, not per image)."""

from unittest.mock import MagicMock

from services.image_references import resolve_image_metadata_batch


def _db_returning(rows_by_call):
    db = MagicMock()
    chain = db.table.return_value.select.return_value.in_.return_value
    chain.execute.side_effect = [MagicMock(data=rows) for rows in rows_by_call]
    return db


def test_batch_resolves_many_ids_with_single_query():
    db = _db_returning([[{"id": "a", "default_alt": "Alt A"}, {"id": "b", "default_alt": None}]])

    result = resolve_image_metadata_batch(db, ["a", "b", "a", None, "missing"])

    assert db.table.call_count == 1
    assert result["a"] == {"image_url": "/api/images/a", "image_alt": "Alt A"}
    assert result["b"] == {"image_url": "/api/images/b", "image_alt": None}
    assert result["missing"] == {"image_url": None, "image_alt": None}
    assert None not in result


def test_batch_chunks_large_id_lists():
    ids = [f"id-{i}" for i in range(5)]
    db = _db_returning([[], [], []])

    resolve_image_metadata_batch(db, ids, chunk_size=2)

    assert db.table.call_count == 3


def test_batch_with_no_ids_skips_database():
    db = MagicMock()

    assert resolve_image_metadata_batch(db, [None, ""]) == {}
    db.table.assert_not_called()


def test_batch_tolerates_lookup_failure():
    db = MagicMock()
    db.table.return_value.select.return_value.in_.return_value.execute.side_effect = RuntimeError("boom")

    result = resolve_image_metadata_batch(db, ["a"])

    assert result == {"a": {"image_url": None, "image_alt": None}}


def test_batch_logs_a_warning_when_lookup_fails(caplog):
    db = MagicMock()
    db.table.return_value.select.return_value.in_.return_value.execute.side_effect = RuntimeError("boom")

    with caplog.at_level("WARNING", logger="services.image_references"):
        resolve_image_metadata_batch(db, ["a", "b"])

    assert any("Batch image metadata lookup failed for 2 image id(s)" in r.message for r in caplog.records)



def test_product_alt_comes_from_batch_map_without_extra_queries():
    from routers.products import _attach_product_image_url

    db = MagicMock()
    with_alt = {"id": "p1", "image_id": "img-1"}
    unknown = {"id": "p2", "image_id": "img-missing"}
    keeps_own = {"id": "p3", "image_id": "img-1", "image_alt": "Own alt"}
    batch = {"img-1": {"image_url": "/api/images/img-1", "image_alt": "A tactile map"}}

    for product in (with_alt, unknown, keeps_own):
        _attach_product_image_url(product, db, batch)

    assert with_alt["image_alt"] == "A tactile map"
    assert unknown["image_alt"] is None
    assert keeps_own["image_alt"] == "Own alt"
    db.table.assert_not_called()
