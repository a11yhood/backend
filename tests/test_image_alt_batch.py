from unittest.mock import MagicMock

import pytest

from services.image_references import resolve_image_alts

pytestmark = pytest.mark.unit


def test_resolve_image_alts_uses_one_query_and_maps_ids():
    db = MagicMock()
    query = db.table.return_value.select.return_value.in_.return_value
    query.execute.return_value.data = [
        {"id": "img-1", "default_alt": "A tactile map"},
        {"id": "img-2", "default_alt": None},
    ]

    result = resolve_image_alts(db, ["img-1", "img-2", "img-1", None])

    assert result == {"img-1": "A tactile map", "img-2": None}
    db.table.assert_called_once_with("images")
    ids = db.table.return_value.select.return_value.in_.call_args.args[1]
    assert sorted(ids) == ["img-1", "img-2"]


def test_resolve_image_alts_skips_query_when_no_ids():
    db = MagicMock()
    assert resolve_image_alts(db, [None, ""]) == {}
    db.table.assert_not_called()
