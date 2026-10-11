"""Source URL domain validation on product create/update (#293).

Non-privileged users may only use supported domains; admins and moderators may use any
domain. The `source` field is always re-derived from the URL so it cannot go stale.
"""

import uuid

import pytest

pytestmark = pytest.mark.integration

UNSUPPORTED_URL = "https://unsupported-domain-test.invalid/some/page"
UNSUPPORTED_DOMAIN = "unsupported-domain-test.invalid"


def _unique(url_prefix: str) -> str:
    return f"{url_prefix}{uuid.uuid4().hex[:12]}"


def _source_name_for_domain(clean_database, domain: str) -> str:
    rows = clean_database.table("supported_sources").select("name").eq("domain", domain).execute().data
    assert rows, f"test database has no supported source for {domain}"
    return rows[0]["name"]


def _create_product(client, headers, source_url: str, name: str = "Source URL validation product"):
    return client.post(
        "/api/products",
        headers=headers,
        json={
            "name": name,
            "description": "integration test product",
            "source_url": source_url,
        },
    )


def test_user_create_with_unsupported_domain_is_rejected(client, test_user, auth_headers):
    response = _create_product(client, auth_headers(test_user), UNSUPPORTED_URL)

    assert response.status_code == 400
    assert "not supported" in response.json()["detail"]


@pytest.mark.parametrize("method", ["patch", "put"])
def test_user_update_to_unsupported_domain_is_rejected(client, test_user, auth_headers, method):
    created = _create_product(
        client, auth_headers(test_user), _unique("https://github.com/a11yhood/source-validation-")
    )
    assert created.status_code == 201
    product = created.json()

    response = getattr(client, method)(
        f"/api/products/{product['id']}",
        headers=auth_headers(test_user),
        json={"source_url": UNSUPPORTED_URL},
    )

    assert response.status_code == 400
    assert "not supported" in response.json()["detail"]
    unchanged = client.get(f"/api/products/{product['id']}").json()
    assert unchanged["source_url"] == product["source_url"]
    assert unchanged["source"] == product["source"]


def test_user_update_to_supported_domain_rederives_source(
    client, clean_database, test_user, auth_headers
):
    created = _create_product(
        client, auth_headers(test_user), _unique("https://github.com/a11yhood/source-rederive-")
    )
    assert created.status_code == 201
    product = created.json()
    new_url = _unique("https://www.ravelry.com/patterns/library/source-rederive-")

    response = client.patch(
        f"/api/products/{product['id']}",
        headers=auth_headers(test_user),
        json={"source_url": new_url},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_url"] == new_url
    assert body["source"] == _source_name_for_domain(clean_database, "ravelry.com")
    assert body["source"] != product["source"]


def test_explicit_source_does_not_override_url_derived_source_on_update(
    client, clean_database, test_user, auth_headers
):
    created = _create_product(
        client, auth_headers(test_user), _unique("https://github.com/a11yhood/source-explicit-")
    )
    assert created.status_code == 201
    new_url = _unique("https://www.ravelry.com/patterns/library/source-explicit-")

    response = client.patch(
        f"/api/products/{created.json()['id']}",
        headers=auth_headers(test_user),
        json={"source_url": new_url, "source": "Github"},
    )

    assert response.status_code == 200
    assert response.json()["source"] == _source_name_for_domain(clean_database, "ravelry.com")


def test_unchanged_unsupported_url_does_not_block_other_edits(
    client, clean_database, test_user, auth_headers
):
    """A product whose stored URL predates the supported list must stay editable."""
    product_id = str(uuid.uuid4())
    clean_database.table("products").insert(
        {
            "id": product_id,
            "name": "Legacy unsupported domain product",
            "slug": f"legacy-unsupported-{product_id[:8]}",
            "description": "legacy",
            "source": UNSUPPORTED_DOMAIN,
            "source_url": UNSUPPORTED_URL,
            "created_by": test_user["id"],
        }
    ).execute()

    response = client.patch(
        f"/api/products/{product_id}",
        headers=auth_headers(test_user),
        json={"name": "Renamed legacy product", "source_url": UNSUPPORTED_URL},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed legacy product"
    assert response.json()["source"] == UNSUPPORTED_DOMAIN


def test_admin_can_create_with_unsupported_domain(client, test_admin, auth_headers):
    response = _create_product(client, auth_headers(test_admin), _unique(UNSUPPORTED_URL + "?x="))

    assert response.status_code == 201
    assert response.json()["source"] == UNSUPPORTED_DOMAIN


def test_moderator_can_update_to_unsupported_domain(
    client, test_user, test_moderator, auth_headers
):
    created = _create_product(
        client, auth_headers(test_user), _unique("https://github.com/a11yhood/source-mod-")
    )
    assert created.status_code == 201
    new_url = _unique(UNSUPPORTED_URL + "?x=")

    response = client.put(
        f"/api/products/{created.json()['id']}",
        headers=auth_headers(test_moderator),
        json={"source_url": new_url},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_url"] == new_url
    assert body["source"] == UNSUPPORTED_DOMAIN


def test_admin_update_to_supported_domain_still_uses_canonical_source(
    client, clean_database, test_user, test_admin, auth_headers
):
    created = _create_product(
        client, auth_headers(test_user), _unique("https://github.com/a11yhood/source-admin-")
    )
    assert created.status_code == 201
    new_url = _unique("https://www.ravelry.com/patterns/library/source-admin-")

    response = client.patch(
        f"/api/products/{created.json()['id']}",
        headers=auth_headers(test_admin),
        json={"source_url": new_url},
    )

    assert response.status_code == 200
    assert response.json()["source"] == _source_name_for_domain(clean_database, "ravelry.com")
