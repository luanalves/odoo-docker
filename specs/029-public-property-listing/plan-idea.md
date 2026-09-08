# Public Property Listing API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new public, JWT-only (no Odoo session) REST endpoints in `thedevkitchen_cms` that let a headless SSR frontend list an agency's published properties by `company_slug` (sortable, status-filterable, ID-filterable, limit-capped) and fetch each listed property's main image, without ever exposing owner/agent PII or requiring a login.

**Architecture:** Two new controller routes reuse the existing `cms_public_controller.get_public_page` pattern (`auth="none"` + `@require_jwt` only, `.sudo()` justified by the absence of an Odoo user/session on this path). A small service layer (slug resolution, query-param validation, domain building, PII-free serialization) sits between the controller and the `real.estate.property` model so each concern is independently unit-testable. Tenant isolation and public-visibility are enforced entirely through an explicit, non-overridable domain filter (`company_id`, `active=True`, `publish_website=True`), not through `ir.rule` (there is no user context to evaluate record rules against on this path).

**Tech Stack:** Odoo 18.0 ORM, `python-magic` (MIME sniffing, already a project dependency), Werkzeug `Response` for raw byte streaming, plain `unittest.TestCase` for DB-free unit tests, Odoo `TransactionCase` for DB-backed tests, curl/bash for E2E API tests (per this project's ADR-003 test flow — `pytest`/`HttpCase` are deliberately not used here; see `scripts/validate_coverage.sh` header comment).

## Global Constraints

- Both new routes: `auth="none"` + `@require_jwt` only (imported from `odoo.addons.thedevkitchen_apigateway.middleware`) — no `@require_session`, no `@require_company`. Do not import `require_jwt` from `quicksol_estate/controllers/utils/auth.py` — that is a different, incompatible implementation (sets `request.jwt_payload`, not `request.jwt_token`) used only by `quicksol_estate`'s own controllers.
- Every query MUST filter `company_id = <resolved from company_slug>`, `active = True`, `publish_website = True` — unconditionally, with no override query param.
- `status` filter values are restricted to exactly `{available, rented, sold, reserved}` — the model's other 3 `property_status` values (`occupied`, `under_construction`, `maintenance`) must be rejected with `400` if explicitly requested, but are NOT filtered out when `status` is omitted (confirmed product decision — see spec Assumptions).
- `ids` filter is AND-combined with all other filters; non-matching IDs are silently dropped from `data`, never surfaced as a distinguishing error (anti-enumeration, ADR-008).
- `limit` default `20`, hard-clamped (not errored) to max `100`.
- No PII in any response: never reuse `serialize_property()` (leaks owner email/phone/mobile/whatsapp) — always use the new `serialize_public_property()`.
- Image bytes are streamed directly via `Response(content, ...)` — never redirect to `/web/content/` (Feature 017 invariant).
- New Python files: black/isort/flake8-clean, `# -*- coding: utf-8 -*-` header, matching this codebase's existing style.
- No changes to the authenticated `GET /api/v1/properties` endpoint or its serializer.

---

### Task 1: Extract shared company-slug resolution helper

**Files:**
- Create: `18.0/extra-addons/thedevkitchen_cms/services/cms_slug_service.py`
- Modify: `18.0/extra-addons/thedevkitchen_cms/controllers/cms_public_controller.py:26-34`
- Test: `18.0/extra-addons/thedevkitchen_cms/tests/integration/test_cms_slug_service.py`
- Modify: `18.0/extra-addons/thedevkitchen_cms/tests/integration/__init__.py`
- Modify: `18.0/extra-addons/thedevkitchen_cms/tests/__init__.py`

**Interfaces:**
- Produces: `resolve_company_by_slug(env, company_slug: str) -> int | None` — used by Task 5 and Task 6's controllers, and by the refactored `cms_public_controller.get_public_page`.

This is a targeted, behavior-preserving extraction: the exact slug→company lookup already inline in `get_public_page` (reading `thedevkitchen.cms.settings`) is pulled into a shared function so the new public-properties controller doesn't duplicate it, per the spec's Architecture Patterns note.

- [ ] **Step 1: Write the failing integration test**

```python
# -*- coding: utf-8 -*-
"""
Integration tests for cms_slug_service.resolve_company_by_slug.
"""
from odoo.tests.common import TransactionCase


class TestCmsSlugService(TransactionCase):

    def setUp(self):
        super().setUp()
        from odoo.addons.thedevkitchen_cms.services.cms_slug_service import (
            resolve_company_by_slug,
        )
        self.resolve_company_by_slug = resolve_company_by_slug

        self.company = self.env["res.company"].create(
            {"name": "Slug Service Test Co", "cnpj": "44.444.444/0001-53"}
        )
        self.env["thedevkitchen.cms.settings"].create(
            {"company_id": self.company.id, "company_slug": "it-slug-service-co"}
        )

    def test_resolves_known_slug(self):
        company_id = self.resolve_company_by_slug(self.env, "it-slug-service-co")
        self.assertEqual(company_id, self.company.id)

    def test_returns_none_for_unknown_slug(self):
        company_id = self.resolve_company_by_slug(self.env, "it-slug-does-not-exist")
        self.assertIsNone(company_id)
```

- [ ] **Step 2: Wire the test file into the test suite**

Edit `18.0/extra-addons/thedevkitchen_cms/tests/integration/__init__.py`, append:
```python
from . import test_cms_slug_service
```

Edit `18.0/extra-addons/thedevkitchen_cms/tests/__init__.py`, append:
```python
# Feature 029: shared company-slug resolution helper
from .integration import test_cms_slug_service
```

- [ ] **Step 3: Run test to verify it fails**

Run: `docker compose -f 18.0/docker-compose.yml exec odoo odoo -d realestate -u thedevkitchen_cms --test-enable --stop-after-init --log-level=test --http-port=8988 2>&1 | tail -40`
Expected: FAIL / ImportError — `cms_slug_service` module does not exist yet.

- [ ] **Step 4: Write minimal implementation**

```python
# -*- coding: utf-8 -*-


def resolve_company_by_slug(env, company_slug):
    """Resolve a res.company id from its CMS-settings company_slug.

    Returns the company_id (int) or None if no matching settings record
    exists. Uses sudo() — there is no Odoo user/session on the public
    routes that call this, so record rules cannot be evaluated anyway.
    """
    settings = (
        env["thedevkitchen.cms.settings"]
        .sudo()
        .search([("company_slug", "=", company_slug)], limit=1)
    )
    return settings.company_id.id if settings else None
```

- [ ] **Step 5: Run test to verify it passes**

Run: same command as Step 3.
Expected: PASS, `2 tests ... OK` in the log tail.

- [ ] **Step 6: Refactor `cms_public_controller.py` to use the shared helper**

Edit `18.0/extra-addons/thedevkitchen_cms/controllers/cms_public_controller.py`:

Replace the import block (lines 1-7):
```python
# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request, Response
from odoo.addons.thedevkitchen_apigateway.middleware import require_jwt
from ..services.cms_error_helpers import _cms_error
from ..services.cms_slug_service import resolve_company_by_slug
```

Replace lines 27-34 (the inline slug lookup) with:
```python
        # 1. Resolve company from slug
        company_id = resolve_company_by_slug(request.env, company_slug)
        if not company_id:
            return _cms_error(404, "not_found", f"Company '{company_slug}' not found")
```

- [ ] **Step 7: Run the full thedevkitchen_cms integration + unit suite to confirm no regression**

Run: `docker compose -f 18.0/docker-compose.yml exec odoo python3 /mnt/extra-addons/thedevkitchen_cms/tests/run_unit_tests.py`
Expected: PASS (unchanged — this refactor doesn't touch unit-tested code).

Run: `docker compose -f 18.0/docker-compose.yml exec odoo odoo -d realestate -u thedevkitchen_cms --test-enable --stop-after-init --log-level=test --http-port=8988 2>&1 | tail -60`
Expected: PASS, including the pre-existing CMS page tests (behavior-preserving refactor).

- [ ] **Step 8: Commit**

```bash
git add 18.0/extra-addons/thedevkitchen_cms/services/cms_slug_service.py \
        18.0/extra-addons/thedevkitchen_cms/controllers/cms_public_controller.py \
        18.0/extra-addons/thedevkitchen_cms/tests/integration/test_cms_slug_service.py \
        18.0/extra-addons/thedevkitchen_cms/tests/integration/__init__.py \
        18.0/extra-addons/thedevkitchen_cms/tests/__init__.py
git commit -m "feat(029): extract shared company-slug resolution helper"
```

---

### Task 2: Public property query-param validators and domain builder

**Files:**
- Create: `18.0/extra-addons/thedevkitchen_cms/services/cms_public_property_service.py`
- Test: `18.0/extra-addons/thedevkitchen_cms/tests/unit/test_cms_public_property_service.py`

**Interfaces:**
- Consumes: nothing (pure functions, no Odoo/DB dependency).
- Produces (used by Task 5 and Task 6 controllers):
  - `PUBLIC_PROPERTY_STATUSES: frozenset[str]` — `{"available", "rented", "sold", "reserved"}`
  - `parse_status_filter(raw: str | None) -> tuple[list[str] | None, bool]` — `(values, ok)`
  - `parse_ids_filter(raw: str | None) -> tuple[list[int] | None, bool]`
  - `parse_sort(raw: str | None) -> tuple[str | None, bool]` — returns an ORM `order` clause string
  - `parse_limit(raw: str | None) -> tuple[int | None, bool]`
  - `build_public_property_domain(company_id: int, status_values: list[str] | None = None, ids: list[int] | None = None) -> list`

This file lives under `tests/unit/` (plain `unittest.TestCase`, no DB) because it has zero Odoo/ORM dependency — it is auto-discovered by `tests/run_unit_tests.py`, no `__init__.py` wiring needed.

- [ ] **Step 1: Write the failing unit test**

```python
# -*- coding: utf-8 -*-
"""
Unit tests for cms_public_property_service — pure functions, no DB.
"""
import unittest

from odoo.addons.thedevkitchen_cms.services.cms_public_property_service import (
    PUBLIC_PROPERTY_STATUSES,
    build_public_property_domain,
    parse_ids_filter,
    parse_limit,
    parse_sort,
    parse_status_filter,
)


class TestParseStatusFilter(unittest.TestCase):
    def test_omitted_returns_no_filter(self):
        self.assertEqual((None, True), parse_status_filter(None))
        self.assertEqual((None, True), parse_status_filter(""))

    def test_single_valid_value(self):
        self.assertEqual((["available"], True), parse_status_filter("available"))

    def test_multiple_valid_values(self):
        values, ok = parse_status_filter("available,reserved")
        self.assertTrue(ok)
        self.assertEqual(["available", "reserved"], values)

    def test_rejects_out_of_scope_model_value(self):
        # 'maintenance' is a real property_status value but not public-facing
        self.assertEqual((None, False), parse_status_filter("maintenance"))

    def test_rejects_unknown_token(self):
        self.assertEqual((None, False), parse_status_filter("not-a-status"))

    def test_rejects_mixed_valid_and_invalid(self):
        self.assertEqual((None, False), parse_status_filter("available,maintenance"))


class TestParseIdsFilter(unittest.TestCase):
    def test_omitted_returns_no_filter(self):
        self.assertEqual((None, True), parse_ids_filter(None))

    def test_parses_comma_separated_ints(self):
        self.assertEqual(([12, 45, 90], True), parse_ids_filter("12,45,90"))

    def test_rejects_non_integer_token(self):
        self.assertEqual((None, False), parse_ids_filter("12,abc,90"))


class TestParseSort(unittest.TestCase):
    def test_default_is_newest(self):
        self.assertEqual(("create_date desc", True), parse_sort(None))

    def test_newest_explicit(self):
        self.assertEqual(("create_date desc", True), parse_sort("newest"))

    def test_oldest(self):
        self.assertEqual(("create_date asc", True), parse_sort("oldest"))

    def test_rejects_unknown_value(self):
        self.assertEqual((None, False), parse_sort("random"))


class TestParseLimit(unittest.TestCase):
    def test_default_is_20(self):
        self.assertEqual((20, True), parse_limit(None))
        self.assertEqual((20, True), parse_limit(""))

    def test_clamps_above_max_to_100(self):
        self.assertEqual((100, True), parse_limit("500"))

    def test_within_range_passes_through(self):
        self.assertEqual((50, True), parse_limit("50"))

    def test_rejects_non_integer(self):
        self.assertEqual((None, False), parse_limit("abc"))

    def test_rejects_zero_or_negative(self):
        self.assertEqual((None, False), parse_limit("0"))
        self.assertEqual((None, False), parse_limit("-5"))


class TestBuildPublicPropertyDomain(unittest.TestCase):
    def test_mandatory_filters_only(self):
        domain = build_public_property_domain(7)
        self.assertEqual(
            [
                ("company_id", "=", 7),
                ("active", "=", True),
                ("publish_website", "=", True),
            ],
            domain,
        )

    def test_adds_status_filter_when_provided(self):
        domain = build_public_property_domain(7, status_values=["available", "sold"])
        self.assertIn(("property_status", "in", ["available", "sold"]), domain)

    def test_adds_ids_filter_when_provided(self):
        domain = build_public_property_domain(7, ids=[1, 2, 3])
        self.assertIn(("id", "in", [1, 2, 3]), domain)

    def test_public_statuses_constant_has_exactly_four_values(self):
        self.assertEqual(
            {"available", "rented", "sold", "reserved"}, PUBLIC_PROPERTY_STATUSES
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f 18.0/docker-compose.yml exec odoo python3 /mnt/extra-addons/thedevkitchen_cms/tests/run_unit_tests.py`
Expected: FAIL / `ModuleNotFoundError: No module named 'odoo.addons.thedevkitchen_cms.services.cms_public_property_service'`

- [ ] **Step 3: Write minimal implementation**

```python
# -*- coding: utf-8 -*-

PUBLIC_PROPERTY_STATUSES = frozenset({"available", "rented", "sold", "reserved"})

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def parse_status_filter(raw_status):
    """Parse the optional `status` query param.

    Returns (status_values, ok). status_values is None when the param was
    omitted (no filter applied) or when validation failed. ok is False when
    any token is outside PUBLIC_PROPERTY_STATUSES.
    """
    if not raw_status:
        return None, True

    tokens = [token.strip() for token in raw_status.split(",") if token.strip()]
    if not tokens or any(token not in PUBLIC_PROPERTY_STATUSES for token in tokens):
        return None, False
    return tokens, True


def parse_ids_filter(raw_ids):
    """Parse the optional `ids` query param into a list of ints."""
    if not raw_ids:
        return None, True

    tokens = [token.strip() for token in raw_ids.split(",") if token.strip()]
    if not tokens:
        return None, True

    ids = []
    for token in tokens:
        try:
            ids.append(int(token))
        except ValueError:
            return None, False
    return ids, True


def parse_sort(raw_sort):
    """Parse the optional `sort` query param into an ORM order clause."""
    sort = raw_sort or "newest"
    if sort == "newest":
        return "create_date desc", True
    if sort == "oldest":
        return "create_date asc", True
    return None, False


def parse_limit(raw_limit):
    """Parse the optional `limit` query param: default 20, hard-clamped to 100."""
    if raw_limit is None or raw_limit == "":
        return DEFAULT_LIMIT, True
    try:
        limit = int(raw_limit)
    except ValueError:
        return None, False
    if limit <= 0:
        return None, False
    return min(limit, MAX_LIMIT), True


def build_public_property_domain(company_id, status_values=None, ids=None):
    """Build the search domain for the public property listing.

    Mandatory filters (company_id, active, publish_website) are always
    applied first and cannot be overridden by any query param.
    """
    domain = [
        ("company_id", "=", company_id),
        ("active", "=", True),
        ("publish_website", "=", True),
    ]
    if status_values:
        domain.append(("property_status", "in", status_values))
    if ids:
        domain.append(("id", "in", ids))
    return domain
```

- [ ] **Step 4: Run test to verify it passes**

Run: same command as Step 2.
Expected: PASS, `OK` with 20 tests run.

- [ ] **Step 5: Commit**

```bash
git add 18.0/extra-addons/thedevkitchen_cms/services/cms_public_property_service.py \
        18.0/extra-addons/thedevkitchen_cms/tests/unit/test_cms_public_property_service.py
git commit -m "feat(029): add public property query-param validators and domain builder"
```

---

### Task 3: Public property serializer (PII-free)

**Files:**
- Create: `18.0/extra-addons/thedevkitchen_cms/services/cms_public_property_serializer.py`
- Test: `18.0/extra-addons/thedevkitchen_cms/tests/integration/test_cms_public_property_serializer.py`
- Modify: `18.0/extra-addons/thedevkitchen_cms/tests/integration/__init__.py`
- Modify: `18.0/extra-addons/thedevkitchen_cms/tests/__init__.py`

**Interfaces:**
- Consumes: a `real.estate.property` recordset (single record) and a `company_slug: str`.
- Produces: `serialize_public_property(property_record, company_slug: str) -> dict` — used by Task 5's list controller.

This needs a real ORM record (to exercise `currency_id`/`state_id`/`property_type_id` relations and `create_date`), so it lives in `tests/integration/` (`TransactionCase`, real DB), not `tests/unit/`.

- [ ] **Step 1: Write the failing integration test**

```python
# -*- coding: utf-8 -*-
"""
Integration tests for cms_public_property_serializer.serialize_public_property.
"""
from odoo.tests.common import TransactionCase

FORBIDDEN_KEYS = {
    "owner", "owner_id", "agent", "agent_id", "internal_notes",
    "commission_ids", "total_commission", "document_ids", "documents",
    "street", "street_number", "complement", "zip_code",
    "latitude", "longitude", "company",
}


class TestSerializePublicProperty(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.thedevkitchen_cms.services.cms_public_property_serializer import (
            serialize_public_property,
        )
        cls.serialize_public_property = staticmethod(serialize_public_property)

        cls.company = cls.env["res.company"].create(
            {"name": "Serializer Test Co", "cnpj": "55.555.555/0001-77"}
        )
        cls.property_type = cls.env["real.estate.property.type"].create(
            {"name": "it_serializer_house"}
        )
        cls.location_type = cls.env["real.estate.location.type"].search(
            [("code", "=", "URB")], limit=1
        ) or cls.env["real.estate.location.type"].create(
            {"name": "Urban", "code": "URB", "sequence": 10}
        )
        country = cls.env.ref("base.br")
        cls.state = cls.env["res.country.state"].search(
            [("country_id", "=", country.id)], limit=1
        )
        owner = cls.env["real.estate.property.owner"].create(
            {"name": "Serializer Test Owner", "email": "owner@example.com"}
        )

        cls.property_with_image = cls.env["real.estate.property"].create(
            {
                "name": "it_serializer_prop_with_image",
                "company_id": cls.company.id,
                "property_type_id": cls.property_type.id,
                "location_type_id": cls.location_type.id,
                "state_id": cls.state.id,
                "owner_id": owner.id,
                "zip_code": "01310-100",
                "city": "Sao Paulo",
                "street": "Av. Paulista",
                "street_number": "1000",
                "area": 80.0,
                "price": 350000.0,
                "for_sale": True,
                "property_status": "available",
                "publish_website": True,
                "description_short": "A lovely test property",
                # 1x1 transparent PNG, base64-encoded
                "image": (
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
                    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
                ),
            }
        )
        cls.property_no_image = cls.env["real.estate.property"].create(
            {
                "name": "it_serializer_prop_no_image",
                "company_id": cls.company.id,
                "property_type_id": cls.property_type.id,
                "location_type_id": cls.location_type.id,
                "state_id": cls.state.id,
                "zip_code": "01310-100",
                "city": "Sao Paulo",
                "street": "Av. Paulista",
                "street_number": "1000",
                "area": 60.0,
                "price": 200000.0,
                "for_sale": True,
                "property_status": "sold",
                "publish_website": True,
            }
        )

    def test_image_url_populated_when_image_set(self):
        payload = self.serialize_public_property(self.property_with_image, "it-slug")
        self.assertEqual(
            f"/api/v1/public/properties/it-slug/{self.property_with_image.id}/image",
            payload["image_url"],
        )

    def test_image_url_null_when_no_image(self):
        payload = self.serialize_public_property(self.property_no_image, "it-slug")
        self.assertIsNone(payload["image_url"])

    def test_expected_keys_present(self):
        payload = self.serialize_public_property(self.property_with_image, "it-slug")
        expected_keys = {
            "id", "reference_code", "name", "property_status", "for_sale",
            "for_rent", "price", "rent_price", "currency", "area", "num_rooms",
            "num_bathrooms", "num_parking", "city", "neighborhood", "state",
            "property_type", "image_url", "description_short", "create_date",
        }
        self.assertEqual(expected_keys, set(payload.keys()))

    def test_no_pii_or_internal_fields_leaked(self):
        payload = self.serialize_public_property(self.property_with_image, "it-slug")
        leaked = FORBIDDEN_KEYS & set(payload.keys())
        self.assertFalse(leaked, f"Forbidden keys leaked into public payload: {leaked}")

    def test_property_type_and_state_are_nested_objects(self):
        payload = self.serialize_public_property(self.property_with_image, "it-slug")
        self.assertEqual(
            {"id": self.property_type.id, "name": "it_serializer_house"},
            payload["property_type"],
        )
        self.assertEqual(self.state.id, payload["state"]["id"])
```

- [ ] **Step 2: Wire the test file into the test suite**

Edit `18.0/extra-addons/thedevkitchen_cms/tests/integration/__init__.py`, append:
```python
from . import test_cms_public_property_serializer
```

Edit `18.0/extra-addons/thedevkitchen_cms/tests/__init__.py`, append:
```python
from .integration import test_cms_public_property_serializer
```

- [ ] **Step 3: Run test to verify it fails**

Run: `docker compose -f 18.0/docker-compose.yml exec odoo odoo -d realestate -u thedevkitchen_cms --test-enable --stop-after-init --log-level=test --http-port=8988 2>&1 | tail -40`
Expected: FAIL — `ModuleNotFoundError` for `cms_public_property_serializer`.

- [ ] **Step 4: Write minimal implementation**

```python
# -*- coding: utf-8 -*-


def serialize_public_property(property_record, company_slug):
    """Build the PII-free public payload for one property (spec FR3.1).

    Deliberately excludes: owner/agent info, internal_notes, commission
    data, documents, exact street address, lat/long, company details.
    """
    currency = property_record.currency_id
    state = property_record.state_id
    property_type = property_record.property_type_id

    return {
        "id": property_record.id,
        "reference_code": property_record.reference_code or None,
        "name": property_record.name or "",
        "property_status": property_record.property_status,
        "for_sale": bool(property_record.for_sale),
        "for_rent": bool(property_record.for_rent),
        "price": float(property_record.price) if property_record.price else 0.0,
        "rent_price": (
            float(property_record.rent_price) if property_record.rent_price else 0.0
        ),
        "currency": (
            {"id": currency.id, "name": currency.name, "symbol": currency.symbol}
            if currency
            else None
        ),
        "area": float(property_record.area) if property_record.area else 0.0,
        "num_rooms": property_record.num_rooms or 0,
        "num_bathrooms": property_record.num_bathrooms or 0,
        "num_parking": property_record.num_parking or 0,
        "city": property_record.city or "",
        "neighborhood": property_record.neighborhood or "",
        "state": (
            {"id": state.id, "name": state.name, "code": state.code}
            if state
            else None
        ),
        "property_type": (
            {"id": property_type.id, "name": property_type.name}
            if property_type
            else None
        ),
        "image_url": (
            f"/api/v1/public/properties/{company_slug}/{property_record.id}/image"
            if property_record.image
            else None
        ),
        "description_short": property_record.description_short or None,
        "create_date": (
            property_record.create_date.isoformat()
            if property_record.create_date
            else None
        ),
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: same command as Step 3.
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add 18.0/extra-addons/thedevkitchen_cms/services/cms_public_property_serializer.py \
        18.0/extra-addons/thedevkitchen_cms/tests/integration/test_cms_public_property_serializer.py \
        18.0/extra-addons/thedevkitchen_cms/tests/integration/__init__.py \
        18.0/extra-addons/thedevkitchen_cms/tests/__init__.py
git commit -m "feat(029): add PII-free public property serializer"
```

---

### Task 4: Domain builder correctness against a real DB (multi-tenancy + visibility gates)

**Files:**
- Test: `18.0/extra-addons/thedevkitchen_cms/tests/integration/test_cms_public_property_domain.py`
- Modify: `18.0/extra-addons/thedevkitchen_cms/tests/integration/__init__.py`
- Modify: `18.0/extra-addons/thedevkitchen_cms/tests/__init__.py`

**Interfaces:**
- Consumes: `build_public_property_domain` (Task 2), real `real.estate.property` records.
- Produces: nothing new — this task only proves the domain from Task 2 behaves correctly against real `search()` calls (no controller/HTTP involved), covering the acceptance criteria in spec User Stories 1-2 that need real data (publish_website gate, active gate, cross-company `ids` isolation), plus the NFR2 query-count (N+1) assertion.

No new production code in this task — pure test coverage of existing pieces wired together.

- [ ] **Step 1: Write the test (no separate "fails first" step — this task adds coverage of already-implemented code, so write it and run it directly)**

```python
# -*- coding: utf-8 -*-
"""
Integration tests proving build_public_property_domain(), combined with a
real search(), correctly enforces multi-tenancy isolation and the
publish_website/active public-visibility gates (spec User Stories 1-2).
"""
from odoo.tests.common import TransactionCase


class TestPublicPropertyDomainIsolation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.thedevkitchen_cms.services.cms_public_property_service import (
            build_public_property_domain,
        )
        cls.build_public_property_domain = staticmethod(build_public_property_domain)

        cls.company_a = cls.env["res.company"].create(
            {"name": "Domain Test Co A", "cnpj": "66.666.666/0001-01"}
        )
        cls.company_b = cls.env["res.company"].create(
            {"name": "Domain Test Co B", "cnpj": "98.765.432/0001-98"}
        )
        cls.property_type = cls.env["real.estate.property.type"].create(
            {"name": "it_domain_house"}
        )
        cls.location_type = cls.env["real.estate.location.type"].search(
            [("code", "=", "URB")], limit=1
        ) or cls.env["real.estate.location.type"].create(
            {"name": "Urban", "code": "URB", "sequence": 10}
        )
        country = cls.env.ref("base.br")
        cls.state = cls.env["res.country.state"].search(
            [("country_id", "=", country.id)], limit=1
        )

        def _make(company, **overrides):
            vals = {
                "name": "it_domain_prop",
                "company_id": company.id,
                "property_type_id": cls.property_type.id,
                "location_type_id": cls.location_type.id,
                "state_id": cls.state.id,
                "zip_code": "01310-100",
                "city": "Sao Paulo",
                "street": "Av. Paulista",
                "street_number": "1000",
                "area": 70.0,
                "price": 300000.0,
                "for_sale": True,
                "property_status": "available",
                "publish_website": True,
            }
            vals.update(overrides)
            return cls.env["real.estate.property"].create(vals)

        cls.prop_a_published = _make(cls.company_a)
        cls.prop_a_unpublished = _make(cls.company_a, publish_website=False)
        cls.prop_a_maintenance = _make(
            cls.company_a, property_status="maintenance"
        )
        cls.prop_a_archived = _make(cls.company_a)
        cls.prop_a_archived.write({"active": False})
        cls.prop_b_published = _make(cls.company_b)

        cls.Property = cls.env["real.estate.property"].sudo()

    def _search(self, company_id, status_values=None, ids=None):
        domain = self.build_public_property_domain(company_id, status_values, ids)
        return self.Property.search(domain)

    def test_only_returns_properties_for_requested_company(self):
        results = self._search(self.company_a.id)
        self.assertNotIn(self.prop_b_published.id, results.ids)

    def test_publish_website_false_never_returned(self):
        results = self._search(self.company_a.id)
        self.assertNotIn(self.prop_a_unpublished.id, results.ids)

    def test_archived_property_never_returned(self):
        results = self._search(self.company_a.id)
        self.assertNotIn(self.prop_a_archived.id, results.ids)

    def test_no_status_filter_includes_maintenance_if_published(self):
        # Confirmed product decision (spec Assumptions): omitting `status`
        # applies no implicit status restriction.
        results = self._search(self.company_a.id)
        self.assertIn(self.prop_a_maintenance.id, results.ids)

    def test_explicit_status_filter_excludes_non_matching(self):
        results = self._search(self.company_a.id, status_values=["sold"])
        self.assertNotIn(self.prop_a_published.id, results.ids)

    def test_cross_company_id_silently_excluded(self):
        results = self._search(
            self.company_a.id, ids=[self.prop_a_published.id, self.prop_b_published.id]
        )
        self.assertIn(self.prop_a_published.id, results.ids)
        self.assertNotIn(self.prop_b_published.id, results.ids)

    def test_serialization_does_not_n_plus_one(self):
        """Spec NFR2: serializing a result set must not issue a query per
        record per relation (property_type_id/state_id/currency_id) — a
        single search() + iteration should let Odoo's prefetch batch these.
        """
        from odoo.addons.thedevkitchen_cms.services.cms_public_property_serializer import (
            serialize_public_property,
        )

        results = self._search(self.company_a.id)
        self.assertGreaterEqual(len(results), 3, "Need multiple records to prove batching")

        self.env.invalidate_all()
        before = self.env.cr.sql_log_count
        for prop in results:
            serialize_public_property(prop, "it-slug")
        query_count = self.env.cr.sql_log_count - before

        # A handful of prefetch queries (property_type/state/currency), not
        # one set of queries per record — bounded constant, not O(n).
        self.assertLess(
            query_count,
            10,
            f"Expected bounded query count for {len(results)} records, got {query_count} "
            "— check for a per-record N+1 on a related field",
        )
```

- [ ] **Step 2: Wire the test file into the test suite**

Edit `18.0/extra-addons/thedevkitchen_cms/tests/integration/__init__.py`, append:
```python
from . import test_cms_public_property_domain
```

Edit `18.0/extra-addons/thedevkitchen_cms/tests/__init__.py`, append:
```python
from .integration import test_cms_public_property_domain
```

- [ ] **Step 3: Run test to verify it passes**

Run: `docker compose -f 18.0/docker-compose.yml exec odoo odoo -d realestate -u thedevkitchen_cms --test-enable --stop-after-init --log-level=test --http-port=8988 2>&1 | tail -40`
Expected: PASS (all 7 test methods green — this exercises Task 2/3's already-correct implementation, so no code change is expected here, only test failures would indicate a bug in an earlier task).

- [ ] **Step 4: Commit**

```bash
git add 18.0/extra-addons/thedevkitchen_cms/tests/integration/test_cms_public_property_domain.py \
        18.0/extra-addons/thedevkitchen_cms/tests/integration/__init__.py \
        18.0/extra-addons/thedevkitchen_cms/tests/__init__.py
git commit -m "test(029): cover multi-tenancy and visibility-gate isolation for public property domain"
```

---

### Task 5: List endpoint controller

**Files:**
- Create: `18.0/extra-addons/thedevkitchen_cms/controllers/cms_public_property_controller.py`
- Modify: `18.0/extra-addons/thedevkitchen_cms/controllers/__init__.py`

**Interfaces:**
- Consumes: `resolve_company_by_slug` (Task 1), `PUBLIC_PROPERTY_STATUSES`/`parse_status_filter`/`parse_ids_filter`/`parse_sort`/`parse_limit`/`build_public_property_domain` (Task 2), `serialize_public_property` (Task 3), `_cms_error` (existing, `cms_error_helpers.py`).
- Produces: route `GET /api/v1/public/properties/<string:company_slug>`, verified end-to-end by Task 8's curl script.

- [ ] **Step 1: Create the controller file with the list route**

```python
# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request, Response
from odoo.addons.thedevkitchen_apigateway.middleware import require_jwt

from ..services.cms_error_helpers import _cms_error
from ..services.cms_public_property_serializer import serialize_public_property
from ..services.cms_public_property_service import (
    PUBLIC_PROPERTY_STATUSES,
    build_public_property_domain,
    parse_ids_filter,
    parse_limit,
    parse_sort,
    parse_status_filter,
)
from ..services.cms_slug_service import resolve_company_by_slug

_logger = logging.getLogger(__name__)


class CmsPublicPropertyController(http.Controller):

    # JWT-authenticated endpoint — requires Bearer token from the frontend
    # application. auth='none' + @require_jwt enforces token validation at
    # the middleware level. Not unauthenticated: intended for
    # server-to-server or SSR clients with a service token, same pattern
    # as CmsPublicController.get_public_page.
    @http.route(
        "/api/v1/public/properties/<string:company_slug>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    def list_public_properties(self, company_slug, **kwargs):
        company_id = resolve_company_by_slug(request.env, company_slug)
        if not company_id:
            return _cms_error(404, "not_found", f"Company '{company_slug}' not found")

        raw_status = kwargs.get("status")
        status_values, status_ok = parse_status_filter(raw_status)
        if not status_ok:
            return _cms_error(
                400,
                "validation_error",
                "Invalid status value(s)",
                allowed=sorted(PUBLIC_PROPERTY_STATUSES),
            )

        raw_ids = kwargs.get("ids")
        ids, ids_ok = parse_ids_filter(raw_ids)
        if not ids_ok:
            return _cms_error(
                400,
                "validation_error",
                "ids must be a comma-separated list of integers",
            )

        raw_sort = kwargs.get("sort")
        order, sort_ok = parse_sort(raw_sort)
        if not sort_ok:
            return _cms_error(
                400, "validation_error", "sort must be 'newest' or 'oldest'"
            )

        raw_limit = kwargs.get("limit")
        limit, limit_ok = parse_limit(raw_limit)
        if not limit_ok:
            return _cms_error(
                400, "validation_error", "limit must be a positive integer"
            )

        domain = build_public_property_domain(company_id, status_values, ids)
        properties = (
            request.env["real.estate.property"]
            .sudo()
            .search(domain, limit=limit, order=order)
        )

        data = [
            serialize_public_property(prop, company_slug) for prop in properties
        ]

        self_link = (
            f"/api/v1/public/properties/{company_slug}"
            f"?sort={raw_sort or 'newest'}&limit={limit}"
        )
        if raw_status:
            self_link += f"&status={raw_status}"
        if raw_ids:
            self_link += f"&ids={raw_ids}"

        payload = {
            "company_slug": company_slug,
            "count": len(data),
            "limit": limit,
            "filters": {
                "status": status_values,
                "ids": ids,
                "sort": raw_sort or "newest",
            },
            "data": data,
            "_links": {"self": self_link},
        }
        return Response(json.dumps(payload), status=200, content_type="application/json")
```

- [ ] **Step 2: Register the controller**

Edit `18.0/extra-addons/thedevkitchen_cms/controllers/__init__.py`, append:
```python
from . import cms_public_property_controller
```

- [ ] **Step 3: Verify the module loads without import errors**

Run: `docker compose -f 18.0/docker-compose.yml exec odoo odoo -d realestate -u thedevkitchen_cms --stop-after-init 2>&1 | tail -30`
Expected: module upgrade completes with no traceback (confirms no syntax/import error in the new controller).

- [ ] **Step 4: Manual smoke test against a running dev stack**

Ensure the stack is up: `cd 18.0 && docker compose up -d`

```bash
source 18.0/.env
TOKEN=$(curl -s -X POST http://localhost:8069/api/v1/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=${OAUTH_CLIENT_ID}&client_secret=${OAUTH_CLIENT_SECRET}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

curl -s "http://localhost:8069/api/v1/public/properties/some-unknown-slug" \
  -H "Authorization: Bearer ${TOKEN}" | python3 -m json.tool
```
Expected: `{"error": "not_found", "detail": "Company 'some-unknown-slug' not found"}` with HTTP 404 (verify status via `-w "%{http_code}"` if desired). Full happy-path verification (with real seeded data) happens in Task 8's automated E2E script — this step only proves the route is reachable and returns a sane shape.

- [ ] **Step 5: Commit**

```bash
git add 18.0/extra-addons/thedevkitchen_cms/controllers/cms_public_property_controller.py \
        18.0/extra-addons/thedevkitchen_cms/controllers/__init__.py
git commit -m "feat(029): add public property listing endpoint"
```

---

### Task 6: Public property image endpoint

**Files:**
- Modify: `18.0/extra-addons/thedevkitchen_cms/controllers/cms_public_property_controller.py`

**Interfaces:**
- Consumes: `resolve_company_by_slug` (Task 1), `build_public_property_domain` (Task 2).
- Produces: route `GET /api/v1/public/properties/<string:company_slug>/<int:property_id>/image`, verified end-to-end by Task 8's curl script.

- [ ] **Step 1: Add imports for binary streaming**

Edit `18.0/extra-addons/thedevkitchen_cms/controllers/cms_public_property_controller.py`, add to the import block:
```python
import base64
import magic
```

- [ ] **Step 2: Add the image route to the same controller class**

Append this method to `CmsPublicPropertyController`, after `list_public_properties`:

```python
    # Same auth model as list_public_properties — see comment above that
    # route. No Content-Disposition header: inline rendering for <img>
    # tags, unlike the authenticated attachment-download endpoint which
    # forces `attachment;` disposition (property_attachments_controller.py).
    @http.route(
        "/api/v1/public/properties/<string:company_slug>/<int:property_id>/image",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    def get_public_property_image(self, company_slug, property_id, **kwargs):
        company_id = resolve_company_by_slug(request.env, company_slug)
        if not company_id:
            return _cms_error(404, "not_found", "Image not found")

        domain = build_public_property_domain(company_id) + [("id", "=", property_id)]
        prop = request.env["real.estate.property"].sudo().search(domain, limit=1)
        if not prop or not prop.image:
            return _cms_error(404, "not_found", "Image not found")

        content = base64.b64decode(prop.image)
        mimetype = magic.from_buffer(content[:2048], mime=True)

        return Response(
            content,
            status=200,
            headers={
                "Content-Type": mimetype,
                "Content-Security-Policy": "default-src 'none'",
                "X-Content-Type-Options": "nosniff",
            },
        )
```

- [ ] **Step 3: Verify the module loads without import errors**

Run: `docker compose -f 18.0/docker-compose.yml exec odoo odoo -d realestate -u thedevkitchen_cms --stop-after-init 2>&1 | tail -30`
Expected: module upgrade completes with no traceback.

- [ ] **Step 4: Manual smoke test — 404 for a non-existent property**

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  "http://localhost:8069/api/v1/public/properties/some-unknown-slug/999999/image" \
  -H "Authorization: Bearer ${TOKEN}"
```
Expected: `404`. Full happy-path byte-streaming verification happens in Task 8.

- [ ] **Step 5: Commit**

```bash
git add 18.0/extra-addons/thedevkitchen_cms/controllers/cms_public_property_controller.py
git commit -m "feat(029): add public property main-image endpoint"
```

---

### Task 7: Composite DB index for the public listing hot path

**Files:**
- Modify: `18.0/extra-addons/quicksol_estate/models/property.py`
- Test: `18.0/extra-addons/quicksol_estate/tests/integration/test_property_public_listing_index.py`
- Modify: `18.0/extra-addons/quicksol_estate/tests/integration/__init__.py`
- Modify: `18.0/extra-addons/quicksol_estate/tests/__init__.py`

Follows the exact existing precedent in `18.0/extra-addons/quicksol_estate/models/lead.py:17-46` (an `init()` override running `CREATE INDEX IF NOT EXISTS`). Per spec NFR2, the mandatory filter set on every public-listing request is `company_id = X AND active = True AND publish_website = True`, sorted by `create_date` — this composite index covers that exact hot path.

- [ ] **Step 1: Write the failing integration test**

```python
# -*- coding: utf-8 -*-
"""
Verifies the composite index backing the public property listing hot path
(Feature 029: company_id + publish_website + active + create_date) exists.
"""
from odoo.tests.common import TransactionCase


class TestPropertyPublicListingIndex(TransactionCase):

    def test_composite_index_exists(self):
        self.env.cr.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'real_estate_property'
            AND indexname = 'real_estate_property_public_listing_idx'
            """
        )
        row = self.env.cr.fetchone()
        self.assertIsNotNone(
            row, "Expected index 'real_estate_property_public_listing_idx' to exist"
        )
```

- [ ] **Step 2: Wire the test file into the test suite**

Edit `18.0/extra-addons/quicksol_estate/tests/integration/__init__.py`, append:
```python
# Feature 029: composite index for the public property listing hot path
from . import test_property_public_listing_index
```

Edit `18.0/extra-addons/quicksol_estate/tests/__init__.py`, append:
```python
from .integration import test_property_public_listing_index
```

- [ ] **Step 3: Run test to verify it fails**

Run: `docker compose -f 18.0/docker-compose.yml exec odoo odoo -d realestate -u quicksol_estate --test-enable --stop-after-init --log-level=test --http-port=8988 2>&1 | tail -40`
Expected: FAIL — index does not exist yet.

- [ ] **Step 4: Add the `init()` override**

Edit `18.0/extra-addons/quicksol_estate/models/property.py`. Insert immediately after the field declarations block and before `# ========== COMPUTED FIELDS ==========` (i.e. right after the `active_proposal_id` field block ending around line 443, before the `@api.depends` at line 445 — insert as a new method on the `Property` class, e.g. directly after the existing `write()` method at lines 476-489):

```python
    def init(self):
        """Create database indexes for common search queries"""
        super(Property, self).init()

        # Composite index for the public property listing hot path
        # (Feature 029): every public request filters by
        # company_id + publish_website + active and sorts by create_date.
        self._cr.execute(
            """
            CREATE INDEX IF NOT EXISTS real_estate_property_public_listing_idx
            ON real_estate_property (company_id, publish_website, active, create_date)
        """
        )
```

- [ ] **Step 5: Apply the index by upgrading the module**

Run: `docker compose -f 18.0/docker-compose.yml exec odoo odoo -d realestate -u quicksol_estate --stop-after-init 2>&1 | tail -30`
Expected: upgrade completes with no traceback (the `init()` hook runs as part of module upgrade, creating the index).

- [ ] **Step 6: Run test to verify it passes**

Run: same command as Step 3.
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add 18.0/extra-addons/quicksol_estate/models/property.py \
        18.0/extra-addons/quicksol_estate/tests/integration/test_property_public_listing_index.py \
        18.0/extra-addons/quicksol_estate/tests/integration/__init__.py \
        18.0/extra-addons/quicksol_estate/tests/__init__.py
git commit -m "perf(029): add composite index for public property listing hot path"
```

---

### Task 8: E2E API test, Swagger/Postman docs, full verification

**Files:**
- Create: `integration_tests/test_us029_public_property_listing.sh`

**Interfaces:**
- Consumes: both new routes (Tasks 5-6), the existing `PUT /api/v1/cms/settings` and `POST /api/v1/properties` endpoints (to bootstrap fixtures), `integration_tests/lib/get_oauth2_token.sh`.
- Produces: nothing consumed elsewhere — this is the terminal E2E verification, auto-discovered by `integration_tests/run_all_tests.sh` (glob `test_us*.sh`) once named correctly.

- [ ] **Step 1: Write the E2E script**

```bash
#!/usr/bin/env bash
# integration_tests/test_us029_public_property_listing.sh
# Feature 029: Public Property Listing API — list + image endpoints

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../18.0/.env"
if [ -f "$ENV_FILE" ]; then
    set -a; source "$ENV_FILE"; set +a
else
    echo "ERROR: .env file not found at $ENV_FILE"
    exit 1
fi

source "${SCRIPT_DIR}/lib/get_oauth2_token.sh"

BASE_URL="${BASE_URL:-${ODOO_BASE_URL:-http://localhost:8069}}"
API_BASE="$BASE_URL/api/v1"
API_USER_EMAIL="${OWNER_EMAIL:-${SEED_OWNER_EMAIL:-}}"
API_USER_PASS="${OWNER_PASS:-${SEED_OWNER_PASSWORD:-}}"
: "${API_USER_EMAIL:?OWNER_EMAIL or SEED_OWNER_EMAIL is required in 18.0/.env}"
: "${API_USER_PASS:?OWNER_PASS or SEED_OWNER_PASSWORD is required in 18.0/.env}"

PASS=0; FAIL=0
_pass() { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
_fail() { echo "  [FAIL] $1 — $2"; FAIL=$((FAIL + 1)); }

echo "========================================"
echo "Feature 029: Public Property Listing Tests"
echo "========================================"

BEARER_TOKEN=$(get_oauth2_token) || { echo "Failed to get OAuth2 token"; exit 1; }

LOGIN_RESPONSE=$(curl -s -X POST "$API_BASE/users/login" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $BEARER_TOKEN" \
    -d "{\"email\":\"$API_USER_EMAIL\",\"password\":\"$API_USER_PASS\"}")
SID=$(echo "$LOGIN_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))")
COMPANY_ID=$(echo "$LOGIN_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print((d.get('user') or {}).get('company_id') or d.get('company_id') or '')")
[ -z "$SID" ] && { echo "Owner login failed"; exit 1; }

H=(-H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $SID" -H "Content-Type: application/json")
pub_req() {
    # Public endpoints: only the Bearer token is needed, no session header.
    curl -s "${@}" -H "Authorization: Bearer $BEARER_TOKEN"
}

# ── Setup: master data + company_slug ─────────────────────────────────────
PROPERTY_TYPE_ID=$(curl -s "$BASE_URL/api/v1/property-types" "${H[@]}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')")
LOCATION_TYPE_ID=$(curl -s "$BASE_URL/api/v1/location-types" "${H[@]}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')")
STATE_ID=$(curl -s "$BASE_URL/api/v1/states?country_id=31" "${H[@]}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')")
[ -n "$PROPERTY_TYPE_ID" ] && [ -n "$LOCATION_TYPE_ID" ] && [ -n "$STATE_ID" ] || { echo "Required master data not found"; exit 1; }

TS=$(date +%s)
COMPANY_SLUG="test-props-$TS"
curl -s -X PUT "$API_BASE/cms/settings" "${H[@]}" \
    -d "{\"company_slug\": \"$COMPANY_SLUG\"}" -o /dev/null

_create_property() {
    local name="$1" status="$2" advertise="$3"
    curl -s -X POST "$API_BASE/properties" "${H[@]}" -d "$(cat <<JSON
{
  "name": "$name",
  "property_type_id": $PROPERTY_TYPE_ID,
  "location_type_id": $LOCATION_TYPE_ID,
  "state_id": $STATE_ID,
  "area": 80,
  "zip_code": "01310-100",
  "city": "Sao Paulo",
  "street": "Av. Paulista",
  "street_number": "1000",
  "company_ids": [$COMPANY_ID],
  "price": 300000,
  "for_sale": true,
  "property_status": "$status",
  "advertise": $advertise
}
JSON
)" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo ""
}

PROP_AVAILABLE=$(_create_property "US029 Available Published $TS" "available" "true")
PROP_SOLD=$(_create_property "US029 Sold Published $TS" "sold" "true")
PROP_UNPUBLISHED=$(_create_property "US029 Unpublished $TS" "available" "false")

[ -n "$PROP_AVAILABLE" ] && [ -n "$PROP_SOLD" ] && [ -n "$PROP_UNPUBLISHED" ] || { echo "Property fixture setup failed"; exit 1; }
echo "Setup complete: slug=$COMPANY_SLUG available=$PROP_AVAILABLE sold=$PROP_SOLD unpublished=$PROP_UNPUBLISHED"

# ---- S1: Happy path list ----
echo ""; echo "S1: GET public property list — happy path"
RESP=$(pub_req -X GET "$API_BASE/public/properties/$COMPANY_SLUG" -o /tmp/us029_list.json -w "%{http_code}")
if [ "$RESP" = "200" ]; then
    _pass "List returns 200"
    COUNT=$(python3 -c "import json; print(json.load(open('/tmp/us029_list.json'))['count'])")
    [ "$COUNT" -ge 2 ] && _pass "List includes published properties (count=$COUNT)" || _fail "Count" "Expected >=2, got $COUNT"
else
    _fail "List happy path" "Expected 200, got $RESP"
fi

# ---- S2: Unpublished property never returned ----
echo ""; echo "S2: Unpublished property excluded"
IDS=$(python3 -c "import json; print([p['id'] for p in json.load(open('/tmp/us029_list.json'))['data']])")
if echo "$IDS" | grep -q "$PROP_UNPUBLISHED"; then
    _fail "Unpublished exclusion" "Unpublished property $PROP_UNPUBLISHED leaked into results"
else
    _pass "Unpublished property not in results"
fi

# ---- S3: status filter ----
echo ""; echo "S3: status=sold filter"
RESP=$(pub_req -X GET "$API_BASE/public/properties/$COMPANY_SLUG?status=sold" -o /tmp/us029_sold.json -w "%{http_code}")
[ "$RESP" = "200" ] && _pass "status=sold returns 200" || _fail "status=sold" "Expected 200, got $RESP"
SOLD_IDS=$(python3 -c "import json; print([p['id'] for p in json.load(open('/tmp/us029_sold.json'))['data']])")
echo "$SOLD_IDS" | grep -q "$PROP_SOLD" && _pass "Sold property present in status=sold results" || _fail "status filter" "Expected $PROP_SOLD in $SOLD_IDS"

# ---- S4: invalid status → 400 ----
echo ""; echo "S4: status=maintenance → 400 (out-of-scope model value)"
RESP=$(pub_req -X GET "$API_BASE/public/properties/$COMPANY_SLUG?status=maintenance" -o /tmp/us029_bad_status.json -w "%{http_code}")
[ "$RESP" = "400" ] && _pass "Invalid status returns 400" || _fail "Invalid status" "Expected 400, got $RESP"

# ---- S5: ids filter, cross-company excluded silently ----
echo ""; echo "S5: ids filter"
RESP=$(pub_req -X GET "$API_BASE/public/properties/$COMPANY_SLUG?ids=$PROP_AVAILABLE,999999999" -o /tmp/us029_ids.json -w "%{http_code}")
[ "$RESP" = "200" ] && _pass "ids filter returns 200" || _fail "ids filter" "Expected 200, got $RESP"
IDS_COUNT=$(python3 -c "import json; print(json.load(open('/tmp/us029_ids.json'))['count'])")
[ "$IDS_COUNT" = "1" ] && _pass "Only the matching id is returned (nonexistent id silently dropped)" || _fail "ids filter count" "Expected 1, got $IDS_COUNT"

# ---- S6: unknown company_slug → 404 ----
echo ""; echo "S6: unknown company_slug → 404"
RESP=$(pub_req -X GET "$API_BASE/public/properties/nonexistent-slug-$TS" -o /dev/null -w "%{http_code}")
[ "$RESP" = "404" ] && _pass "Unknown slug returns 404" || _fail "Unknown slug" "Expected 404, got $RESP"

# ---- S7: missing bearer token → 401 ----
echo ""; echo "S7: missing token → 401"
RESP=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$API_BASE/public/properties/$COMPANY_SLUG")
[ "$RESP" = "401" ] && _pass "Missing token returns 401" || _fail "Missing token" "Expected 401, got $RESP"

# ---- S8: image endpoint — no image set → 404 ----
echo ""; echo "S8: image endpoint — property has no image → 404"
RESP=$(pub_req -X GET "$API_BASE/public/properties/$COMPANY_SLUG/$PROP_AVAILABLE/image" -o /dev/null -w "%{http_code}")
[ "$RESP" = "404" ] && _pass "No-image property returns 404 on image route" || _fail "Image 404" "Expected 404, got $RESP"

# ---- S9: image endpoint — non-public property → 404 (anti-enumeration) ----
echo ""; echo "S9: image endpoint — unpublished property → 404"
RESP=$(pub_req -X GET "$API_BASE/public/properties/$COMPANY_SLUG/$PROP_UNPUBLISHED/image" -o /dev/null -w "%{http_code}")
[ "$RESP" = "404" ] && _pass "Unpublished property image returns 404" || _fail "Image visibility gate" "Expected 404, got $RESP"

echo ""; echo "========================================"
echo "Results: PASS=$PASS FAIL=$FAIL"
echo "========================================"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
```

- [ ] **Step 2: Make it executable and run it against the live dev stack**

```bash
chmod +x integration_tests/test_us029_public_property_listing.sh
cd 18.0 && docker compose up -d && cd ..
bash integration_tests/test_us029_public_property_listing.sh
```
Expected: `Results: PASS=... FAIL=0`. If any scenario fails, fix the corresponding controller/service code from Tasks 5-6 and re-run — do not edit the test to match broken behavior.

- [ ] **Step 3: Generate Swagger/OpenAPI documentation**

Invoke the `swagger-updater` skill for both new routes (`GET /api/v1/public/properties/<company_slug>` and `GET /api/v1/public/properties/<company_slug>/<property_id>/image`), per ADR-005. Do not hand-edit static OpenAPI files.

- [ ] **Step 4: Generate Postman collection entries**

Invoke the `postman-collection-manager` skill to add both new endpoints, per ADR-016.

- [ ] **Step 5: Run the full verification suite**

Run: `bash scripts/validate_coverage.sh`
Expected: `thedevkitchen_cms` and `quicksol_estate` both show unit + integration PASS; the new `test_us029_public_property_listing.sh` shows PASS under "Phase 2: E2E API Tests".

- [ ] **Step 6: Run linters**

```bash
docker compose -f 18.0/docker-compose.yml exec odoo black --check /mnt/extra-addons/thedevkitchen_cms /mnt/extra-addons/quicksol_estate
docker compose -f 18.0/docker-compose.yml exec odoo isort --check-only /mnt/extra-addons/thedevkitchen_cms /mnt/extra-addons/quicksol_estate
docker compose -f 18.0/docker-compose.yml exec odoo flake8 /mnt/extra-addons/thedevkitchen_cms/controllers/cms_public_property_controller.py /mnt/extra-addons/thedevkitchen_cms/services/cms_slug_service.py /mnt/extra-addons/thedevkitchen_cms/services/cms_public_property_service.py /mnt/extra-addons/thedevkitchen_cms/services/cms_public_property_serializer.py
docker compose -f 18.0/docker-compose.yml exec odoo pylint --fail-under=8.0 /mnt/extra-addons/thedevkitchen_cms/controllers/cms_public_property_controller.py /mnt/extra-addons/thedevkitchen_cms/services/cms_slug_service.py /mnt/extra-addons/thedevkitchen_cms/services/cms_public_property_service.py /mnt/extra-addons/thedevkitchen_cms/services/cms_public_property_serializer.py
```
Expected: no errors, pylint score >= 8.0 (per NFR3). Fix formatting with `black`/`isort` (no `--check`) if needed and re-run.

- [ ] **Step 7: Commit**

```bash
git add integration_tests/test_us029_public_property_listing.sh
git commit -m "test(029): add E2E API tests for public property listing endpoints"
```

---

## Post-Implementation (not part of this plan's tasks)

Per this project's convention (constitution updates happen LAST, after implementation is validated — see spec "Constitution Feedback" section):
1. Journey flowcharts: create `specs/029-public-property-listing/flowcharts.md`, one Mermaid diagram per user story.
2. Constitution update: bump `.specify/memory/constitution.md` (MINOR) to document the "Public JWT-Only Listing Endpoint" and "Public Visibility Gate via Data Field" patterns, once this plan's tests are all green.
