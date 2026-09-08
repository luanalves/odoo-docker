# Feature Specification: Public Property Listing API

**Feature Branch**: `029-public-property-listing`
**Created**: 2026-09-08
**Status**: Draft
**ADR References**: ADR-001, ADR-003, ADR-004, ADR-005, ADR-007, ADR-008, ADR-009, ADR-011, ADR-015, ADR-016, ADR-018, ADR-019, ADR-022

## Executive Summary

A new **unauthenticated-from-the-end-user-perspective, service-JWT-gated** REST endpoint that returns a curated, PII-free list of an agency's published properties, resolved by `company_slug` — the same slug-resolution pattern already used by `GET /api/v1/public/cms/:company_slug/pages/:page_slug`. Consumers (the headless Next.js/React SSR frontend, or any server holding a valid application JWT) can sort by creation date, filter by a restricted set of public-facing statuses, filter by an explicit list of property IDs, and cap the number of items returned — enabling public marketing/SEO property-listing pages without ever requiring an Odoo user session or exposing owner/agent PII.

---

## Out of Scope / Non-Goals

**Fora de Escopo**:
- **Offset/cursor pagination** — only a `limit` cap is supported in this version (matches the literal ask: "Limite de quantidade de itens retornados"). If deep pagination becomes a product need, it is a follow-up feature.
- **Full property detail view** (public single-property GET) — this spec covers only the list endpoint plus the minimal supporting main-image endpoint needed to make the list usable. A public "property detail page" endpoint (with full description, gallery, amenities, etc.) is a separate future feature.
- **Photo gallery** — only the single "Main Property Image" (`property.image` field) is exposed via a new public image sub-resource. `photo_ids` (full gallery) is out of scope.
- **Search by free text / geolocation / price range / bedroom count** — the user's request enumerated exactly 4 capabilities (sort, status filter, ID-list filter, limit); no additional filters are added speculatively.
- **Per-endpoint rate limiting** (Redis `rate_limit:{endpoint}:{ip}` pattern) — explicitly deferred. The existing public CMS pages endpoint (`get_public_page`) has no endpoint-level rate limiting either; abuse control for this class of endpoint is left to the external Kong API Gateway in production, consistent with that precedent. **Do not implement a Redis rate-limit task for this feature.**
- **Restricting listing to only the 4 requested statuses by default** — when the `status` query param is omitted, no status filter is applied (all `publish_website=True` + `active=True` properties are returned regardless of `property_status`). Only an explicit, non-default `status` param is validated against the 4-value allow-list. See Assumptions.

**Comportamentos Proibidos** (o desenvolvimento NUNCA deve introduzir):
- [ ] Não enfraquecer o isolamento multi-tenant (ADR-008) — every query MUST be scoped to the single `company_id` resolved from `company_slug`; the `ids` filter param MUST be AND-combined with the company/publish/active filters, never OR-combined or used to bypass company scoping.
- [ ] Não expor dados de outra empresa — a property ID belonging to a different company (or not eligible for public visibility) passed via `ids` MUST be silently excluded from results, never surfaced with an error revealing its existence (ADR-008 principle 5, generic responses).
- [ ] Não remover soft delete em favor de exclusão física (ADR-015) — `active=True` is a mandatory, non-overridable filter on this public endpoint (no `is_active` override param, unlike the authenticated `/api/v1/properties`).
- [ ] Não expor PII de proprietário/agente (owner email/phone/mobile/whatsapp, agent email, internal_notes, commission data, exact street address, documents, lat/long) in the public payload — the existing `serialize_property()` helper used by the authenticated endpoint MUST NOT be reused as-is; a new, deliberately minimal public serializer is required.
- [ ] Não usar `.sudo()` para contornar isolamento em contexto autenticado — the `.sudo()` usage in this feature is scoped exclusively to the public/no-session code path (mirroring `cms_public_controller.get_public_page`), where there is no `res.users` context to apply record rules against in the first place; it MUST NOT be introduced into any authenticated controller as a shortcut.
- [ ] Não servir binários via redirect para `/web/content/` — the new main-image endpoint MUST stream bytes directly (`Response(content, ...)`), reusing the Feature 017 "download URL invariant" pattern already established in `property_attachments_controller.py`.
- [ ] Não quebrar o endpoint autenticado existente `GET /api/v1/properties` ou seu contrato — this is a net-new, additive route; no changes to the authenticated property controller/serializer.

**Armadilhas Conhecidas a Evitar**:
- The existing "public" CMS page endpoint is **not** actually unauthenticated — it is `auth="none"` at the route level but still enforces `@require_jwt`. Do not confuse this with the fully-unauthenticated `GET /api/v1/leads`, `/api/v1/sales`, `/api/v1/tags` endpoints (flagged in `CLAUDE.md` §12 item 6 as an *undecided, likely-accidental* gap). This feature deliberately follows the CMS-page pattern (JWT-gated), not the leads/sales/tags pattern (zero decorators) — this was a resolved, explicit decision, not an oversight.
- `real.estate.property.image` is a `Binary(attachment=True)` field, not a dedicated `url = fields.Char()` like `thedevkitchen.cms.media.url`. There is no existing public image-serving route for properties — the existing `download_attachment` endpoint requires the full triple decorator (`@require_jwt` + `@require_session` + `@require_company`) and is therefore unusable by a JWT-only public consumer. A new, minimal public image route is required for `image_url` in the response to be usable at all (see FR4).

---

## User Scenarios & Testing

### User Story 1: SSR frontend renders an agency's public property listing (Priority: P1) 🎯 MVP

**As a** headless SSR frontend (holding a valid application JWT, no Odoo session)
**I want to** fetch a company's published, active properties by `company_slug`
**So that** I can render a public marketing/SEO property-listing page without exposing internal data or requiring a login

**Acceptance Criteria**:
- [ ] Given a valid `company_slug` with published properties, when `GET /api/v1/public/properties/<company_slug>` is called with a valid JWT, then a 200 response with the curated property list is returned.
- [ ] Given no `status`/`ids`/`sort`/`limit` params, when the endpoint is called, then it returns up to 20 `active=True` + `publish_website=True` properties for that company, newest first.
- [ ] Given a property with `publish_website=False`, when the list is fetched, then that property is NEVER returned, regardless of any other filter.
- [ ] Given a soft-deleted property (`active=False`), when the list is fetched, then that property is NEVER returned.
- [ ] Given an invalid/unknown `company_slug`, when the endpoint is called, then a 404 `not_found` error is returned (identical shape whether the slug never existed or the company has no CMS settings record — no enumeration signal).
- [ ] Given a request with no JWT or an invalid/expired JWT, when the endpoint is called, then a 401 is returned (per `@require_jwt`).
- [ ] Given entrada inválida (malformed `ids`, invalid `status` token, invalid `sort` value), when [ação], then a 400 validation error is returned listing the allowed values (ADR-018).
- [ ] Given empresa diferente, when a property ID belonging to another company is included in `ids`, then it is silently excluded from `data` (ADR-008 isolation) — response is still 200, just without that item.

**Test Coverage** (per ADR-003):

| Type | Test Name | Description | Status |
|------|-----------|-------------|--------|
| Unit | `test_company_slug_resolution_found()` | Slug resolves to correct `company_id` | ⚠️ Required |
| Unit | `test_company_slug_resolution_not_found()` | Unknown slug → 404 | ⚠️ Required |
| Unit | `test_publish_website_gate_always_applied()` | `publish_website=False` never returned even with matching status/id filters | ⚠️ Required |
| Unit | `test_active_gate_always_applied()` | Soft-deleted properties never returned | ⚠️ Required |
| Unit | `test_status_filter_valid_values()` | `available/rented/sold/reserved` accepted | ⚠️ Required |
| Unit | `test_status_filter_rejects_out_of_scope_values()` | `occupied/under_construction/maintenance` (and any unknown token) → 400 | ⚠️ Required |
| Unit | `test_ids_filter_cross_company_excluded()` | ID from another company silently dropped, not errored | ⚠️ Required |
| Unit | `test_sort_newest_oldest()` | `sort=newest` (default) vs `sort=oldest` produce inverse `create_date` ordering | ⚠️ Required |
| Unit | `test_limit_default_and_clamp()` | Default 20; values >100 clamped to 100 (not errored), matching `/api/v1/properties` | ⚠️ Required |
| Unit | `test_public_serializer_excludes_pii()` | Serializer output has no owner/agent/internal_notes/commission/address-number/lat-long keys | ⚠️ Required |
| E2E (API) | `test_public_list_no_auth_401()` | Missing/invalid JWT → 401 | ⚠️ Required |
| E2E (API) | `test_public_list_happy_path()` | Full request→response contract, valid JWT | ⚠️ Required |
| E2E (API) | `test_multitenancy_isolation()` | Two companies' properties never cross-leak via slug or `ids` | ⚠️ Required |
| E2E (UI) | N/A | This is an API-only feature (headless consumers); no Odoo UI views/menus are introduced | N/A |

### User Story 2: Public listing filtered by status and explicit ID set (Priority: P1) 🎯 MVP

**As a** headless SSR frontend
**I want to** filter the public property list by one or more of the 4 public-facing statuses, and/or restrict to a specific set of property IDs (e.g., "featured" IDs curated by the agency)
**So that** I can render targeted sections of a public site (e.g., "Available Now", "Recently Sold", a hand-picked featured carousel)

**Acceptance Criteria**:
- [ ] Given `status=available,reserved`, when the endpoint is called, then only properties with those two statuses (and still `publish_website=True`, `active=True`) are returned.
- [ ] Given `status=sold`, when the endpoint is called, then only sold, published properties are returned (useful for a "recently sold" showcase section).
- [ ] Given `status=maintenance` (a value outside the public allow-list), when the endpoint is called, then a 400 error is returned listing the 4 valid values.
- [ ] Given `ids=12,45,90`, when the endpoint is called, then only those IDs (that also satisfy company/publish/active/status filters) are returned, in the requested sort order — not necessarily in the order the IDs were listed.
- [ ] Given `ids` combined with `status`, when both are provided, then both filters are AND-combined.

**Test Coverage**: covered by the Unit/E2E rows already listed under User Story 1 (`test_status_filter_*`, `test_ids_filter_cross_company_excluded`); additional:

| Type | Test Name | Description | Status |
|------|-----------|-------------|--------|
| Unit | `test_status_and_ids_combined_and_semantics()` | Both filters applied together narrow results correctly | ⚠️ Required |
| Unit | `test_ids_malformed_returns_400()` | Non-integer token in `ids` → 400 | ⚠️ Required |

### User Story 3: Public main-image delivery for listing cards (Priority: P2)

**As a** headless SSR frontend
**I want to** fetch a listed property's main image via a public, JWT-gated URL
**So that** listing cards render a photo without needing an authenticated session

**Acceptance Criteria**:
- [ ] Given a property returned by User Story 1/2 with a non-null `image_url`, when that URL is fetched with the same JWT, then the raw image bytes are streamed with the correct `Content-Type` (magic-bytes detected, per Feature 017 pattern).
- [ ] Given a property with no `image` set, when the list is fetched, then `image_url` is `null` (no dead link).
- [ ] Given a property that is NOT publicly visible (e.g., `publish_website=False`, soft-deleted, or belongs to another company), when its image URL is requested directly (bypassing the list), then a 404 is returned — the image endpoint enforces the same visibility gate as the list, so it cannot be used to enumerate non-public properties.
- [ ] Given no JWT, when the image URL is requested, then a 401 is returned.

**Test Coverage** (per ADR-003):

| Type | Test Name | Description | Status |
|------|-----------|-------------|--------|
| Unit | `test_image_url_null_when_no_image()` | Serializer emits `null`, not a broken URL, when `property.image` is empty | ⚠️ Required |
| E2E (API) | `test_public_image_streams_bytes()` | 200, correct `Content-Type`, no `/web/content/` redirect | ⚠️ Required |
| E2E (API) | `test_public_image_visibility_gate()` | Non-public property (unpublished/archived/other-company) → 404 via direct image request | ⚠️ Required |
| E2E (API) | `test_public_image_no_auth_401()` | Missing JWT → 401 | ⚠️ Required |

---

## Requirements

### Functional Requirements

**FR1: Company Resolution**
- FR1.1: Resolve `company_id` by searching `thedevkitchen.cms.settings` (`sudo()`, no user context available in a public/no-session request) for `company_slug = <path param>`, exactly mirroring `cms_public_controller.get_public_page`.
- FR1.2: If no matching `thedevkitchen.cms.settings` record exists, return `404 not_found` — same generic message regardless of whether the slug was never registered or the company simply has no CMS settings row (ADR-008 principle 5, anti-enumeration).

**FR2: Listing & Filtering**
- FR2.1: Always filter `active = True` (ADR-015). No override parameter — unlike `/api/v1/properties`'s `is_active` param, this public endpoint never exposes archived properties.
- FR2.2: Always filter `publish_website = True`, unconditionally, regardless of any other filter combination (per confirmed decision — the field already exists on `real.estate.property` but is currently unused by any endpoint; this is its first real consumer).
- FR2.3: Optional `status` query param — comma-separated list restricted to `{available, rented, sold, reserved}` (the 4 values the user requested). Any token outside this set (including the model's other 3 valid `property_status` values: `occupied`, `under_construction`, `maintenance`) causes the **entire request** to fail with `400 validation_error`, listing the 4 allowed values. When omitted, no status filter is applied.
- FR2.4: Optional `ids` query param — comma-separated integers. Combined via AND with the company/publish/active/status domain. IDs that don't match (wrong company, unpublished, archived, wrong status) are silently omitted from `data`, never surfaced as an error (ADR-008 principle 5). Non-integer tokens → `400 validation_error`.
- FR2.5: Optional `sort` query param — `newest` (default) or `oldest`, mapping to `order="create_date desc"` / `order="create_date asc"` respectively. Any other value → `400 validation_error`.
- FR2.6: Optional `limit` query param — default `20`, hard-clamped (not errored) to a max of `100`, identical semantics to the authenticated `GET /api/v1/properties` (`min(int(limit), 100)`). Non-integer value → `400 validation_error`.
- FR2.7: No offset/cursor pagination in this version (see Out of Scope).

**FR3: Public Payload Projection**
- FR3.1: Response `data[]` items contain exactly: `id`, `reference_code`, `name`, `property_status`, `for_sale`, `for_rent`, `price`, `rent_price`, `currency` (`{id, name, symbol}` from `currency_id`), `area`, `num_rooms`, `num_bathrooms`, `num_parking`, `city`, `neighborhood`, `state` (`{id, name, code}` or `null`), `property_type` (`{id, name}` or `null`), `image_url` (nullable), `description_short`, `create_date` (ISO 8601). No other fields.
- FR3.2: `image_url` is `null` when `property.image` is empty; otherwise it is `/api/v1/public/properties/<company_slug>/<property_id>/image` (relative path, consumer prepends host).
- FR3.3: `price`/`rent_price` are returned as raw floats (no localized formatting, unlike `serialize_property`'s `price_formatted` — public consumers format currency client-side).

**FR4: Public Main Image Delivery**
- FR4.1: `GET /api/v1/public/properties/<company_slug>/<int:property_id>/image` — `auth="none"` + `@require_jwt` only (same auth model as the list endpoint). Resolves `company_slug` identically to FR1; then looks up `property_id` filtered by `company_id = resolved`, `active = True`, `publish_website = True` — the exact same visibility gate as the list endpoint, so this route cannot be used to probe for non-public properties.
- FR4.2: If the property is not found under that filtered domain (wrong company, unpublished, archived, or nonexistent ID), return `404 not_found` — generic, no distinction between "doesn't exist" and "not publicly visible."
- FR4.3: If found but `property.image` is empty, return `404 not_found` (`no_image`).
- FR4.4: Stream raw bytes directly (`Response(content, status=200, headers={...})`) with MIME type detected via magic bytes (`python-magic`, reusing the Feature 017 pattern already in `property_attachments_controller.py`). MUST NOT redirect to `/web/content/` (Feature 017 invariant, reaffirmed here for a second module).

### Data Model (per ADR-004, knowledge_base/09-database-best-practices.md)

This feature introduces **no new persisted entities and no schema migrations**. It is a read-only projection over two existing models:

**Entity: `real.estate.property`** (existing, `quicksol_estate` module — read-only usage here)

| Field used | Type | Already exists? | Role in this feature |
|-------|------|-------------|--------------------|
| `id` | Integer | Yes | Public `id`, image sub-resource path, `ids` filter target |
| `reference_code` | Char, indexed | Yes | Public field |
| `name` | Char, required | Yes | Public field |
| `property_status` | Selection (7 values) | Yes | Public field + `status` filter (restricted to 4 of the 7 values) |
| `active` | Boolean (ADR-015 soft delete) | Yes | Mandatory, non-overridable filter |
| `publish_website` | Boolean, default False | Yes (currently unused by any endpoint) | Mandatory, non-overridable filter — first real consumer of this field |
| `company_id` | Many2one `res.company`, required | Yes | Mandatory tenant-isolation filter, resolved from `company_slug` |
| `create_date` | Datetime, auto | Yes | `sort` param target |
| `image` | Binary(attachment=True) | Yes | Source for the new public image sub-resource (FR4) |
| `for_sale`, `for_rent`, `price`, `rent_price`, `currency_id`, `area`, `num_rooms`, `num_bathrooms`, `num_parking`, `city`, `neighborhood`, `state_id`, `property_type_id`, `description_short` | various | Yes | Public projection fields |

**Entity: `thedevkitchen.cms.settings`** (existing, `thedevkitchen_cms` module — read-only usage here)

| Field used | Type | Role |
|-------|------|------|
| `company_slug` | Char, unique | Path param resolution to `company_id` (reused from Feature 021 CMS domain, not duplicated) |
| `company_id` | Many2one, required | Resolved tenant scope |

**No new SQL constraints, no new Python constraints, no new `ir.rule` record rules** — see NFR1 for why record rules do not apply here (no `res.users` context on this auth path).

**Recommended new index** (performance, not a functional/schema requirement of this spec — see NFR2): a composite B-tree index on `real_estate_property(company_id, publish_website, active, create_date)` to support the mandatory filter + sort combination efficiently at scale. To be added during implementation planning, not part of this spec's data-model contract.

### API Endpoints (per ADR-007, ADR-009, ADR-011)

**Endpoint: GET /api/v1/public/properties/<string:company_slug>**

| Attribute | Value |
|-----------|-------|
| **Method** | GET |
| **Path** | `/api/v1/public/properties/<string:company_slug>` |
| **Module** | `thedevkitchen_cms` (owns `company_slug` resolution + the existing public-route precedent; `quicksol_estate` cannot see CMS models since the dependency direction is `thedevkitchen_cms → quicksol_estate`, not the reverse) |
| **Authentication** | `# public endpoint` marker + `auth="none"` + `@require_jwt` ONLY — no `@require_session`, no `@require_company` (decision B, mirrors `cms_public_controller.get_public_page`) |
| **Authorization** | None (public/marketing data) — visibility is enforced entirely via the `publish_website`/`active`/`company_id` domain filter, not via RBAC groups |
| **Rate Limit** | None at the application layer (deferred to Kong in production — see Out of Scope) |
| **CORS** | `cors="*"` (consistent with every other route in this codebase) |

**Query Parameters**:
```
status   (optional) comma-separated, subset of: available, rented, sold, reserved
ids      (optional) comma-separated integers
sort     (optional) "newest" (default) | "oldest"
limit    (optional) integer, default 20, clamped to max 100
```

**Response Success (200)**:
```json
{
  "company_slug": "imobiliaria-exemplo",
  "count": 2,
  "limit": 20,
  "filters": {
    "status": ["available"],
    "ids": null,
    "sort": "newest"
  },
  "data": [
    {
      "id": 42,
      "reference_code": "REF-000042",
      "name": "Apartamento 2 quartos - Centro",
      "property_status": "available",
      "for_sale": true,
      "for_rent": false,
      "price": 350000.0,
      "rent_price": 0.0,
      "currency": {"id": 1, "name": "BRL", "symbol": "R$"},
      "area": 68.5,
      "num_rooms": 2,
      "num_bathrooms": 1,
      "num_parking": 1,
      "city": "São Paulo",
      "neighborhood": "Centro",
      "state": {"id": 26, "name": "São Paulo", "code": "SP"},
      "property_type": {"id": 3, "name": "Apartamento"},
      "image_url": "/api/v1/public/properties/imobiliaria-exemplo/42/image",
      "description_short": "Amplo apartamento reformado próximo ao metrô.",
      "create_date": "2026-09-01T14:32:00Z"
    }
  ],
  "_links": {
    "self": "/api/v1/public/properties/imobiliaria-exemplo?status=available&sort=newest&limit=20"
  }
}
```

**Error Responses** (envelope matches the existing `_cms_error()` helper — `{"error": "<code>", "detail": "<string>", ...extras}`):

| Code | Condition | Response |
|------|-----------|----------|
| 400 | Invalid `status` token(s) (ADR-018) | `{"error": "validation_error", "detail": "Invalid status value(s)", "allowed": ["available","rented","sold","reserved"]}` |
| 400 | Invalid `ids` format | `{"error": "validation_error", "detail": "ids must be a comma-separated list of integers"}` |
| 400 | Invalid `sort` value | `{"error": "validation_error", "detail": "sort must be 'newest' or 'oldest'"}` |
| 400 | Invalid `limit` value | `{"error": "validation_error", "detail": "limit must be a positive integer"}` |
| 401 | Missing/invalid JWT (ADR-011) | `{"error": "unauthorized"}` (standard `@require_jwt` response) |
| 404 | Unknown `company_slug` (ADR-008 anti-enumeration) | `{"error": "not_found", "detail": "Company '<slug>' not found"}` |
| 500 | Unexpected error | `{"error": "internal_error", "detail": "An unexpected error occurred."}` |

---

**Endpoint: GET /api/v1/public/properties/<string:company_slug>/<int:property_id>/image**

| Attribute | Value |
|-----------|-------|
| **Method** | GET |
| **Path** | `/api/v1/public/properties/<string:company_slug>/<int:property_id>/image` |
| **Authentication** | `# public endpoint` marker + `auth="none"` + `@require_jwt` ONLY |
| **Authorization** | None — visibility gate identical to the list endpoint (`company_id` + `active=True` + `publish_website=True`) |

**Response Success (200)**: raw image bytes, `Content-Type` set from magic-byte detection, `Content-Disposition` omitted (inline rendering for `<img>` tags, unlike the authenticated attachment-download endpoint which forces `attachment;` disposition).

**Error Responses**:

| Code | Condition | Response |
|------|-----------|----------|
| 401 | Missing/invalid JWT | `{"error": "unauthorized"}` |
| 404 | Property not found / not publicly visible / no image set | `{"error": "not_found", "detail": "Image not found"}` (single generic message across all three cases — anti-enumeration) |
| 500 | Unexpected error | `{"error": "internal_error", "detail": "An unexpected error occurred."}` |

### Seed Data (OBRIGATÓRIO — todos os solution types)

**Seed: Companies + CMS Settings**
```python
# Two companies to prove multi-tenancy isolation end-to-end
company_a = env['res.company'].create({'name': 'Imobiliária Seed A'})
company_b = env['res.company'].create({'name': 'Imobiliária Seed B'})

cms_settings_a = env['thedevkitchen.cms.settings'].create({
    'company_id': company_a.id,
    'company_slug': 'seed-imobiliaria-a',
})
cms_settings_b = env['thedevkitchen.cms.settings'].create({
    'company_id': company_b.id,
    'company_slug': 'seed-imobiliaria-b',
})
# Deliberately: company_a has CMS settings but NO company_slug is left unset for a third
# scenario company to test the 404 "no settings row" path — see below.
company_c = env['res.company'].create({'name': 'Imobiliária Seed C (no CMS settings)'})
```

**Seed: Domain Entities — Properties (per company, exercising every filter path)**
```python
# All properties reference a minimal valid seed owner/type/location per existing
# quicksol_estate seed fixtures (seed_property_owner, etc.) — reused, not duplicated.

# Company A — the "happy path" company
seed_property_available_published = Property.create({
    'name': 'seed_prop_available_published', 'company_id': company_a.id,
    'property_status': 'available', 'publish_website': True, 'active': True,
    'price': 350000.0, 'for_sale': True, ... (required fields per model),
})
seed_property_reserved_published = Property.create({
    'name': 'seed_prop_reserved_published', 'company_id': company_a.id,
    'property_status': 'reserved', 'publish_website': True, 'active': True, ...
})
seed_property_sold_published = Property.create({
    'name': 'seed_prop_sold_published', 'company_id': company_a.id,
    'property_status': 'sold', 'publish_website': True, 'active': True, ...
})
seed_property_rented_published = Property.create({
    'name': 'seed_prop_rented_published', 'company_id': company_a.id,
    'property_status': 'rented', 'publish_website': True, 'active': True, ...
})
# Must be EXCLUDED from all public results:
seed_property_unpublished = Property.create({
    'name': 'seed_prop_unpublished', 'company_id': company_a.id,
    'property_status': 'available', 'publish_website': False, 'active': True, ...
})
seed_property_maintenance_published = Property.create({
    'name': 'seed_prop_maintenance_published', 'company_id': company_a.id,
    'property_status': 'maintenance', 'publish_website': True, 'active': True, ...
    # proves: even though published, filtering status=maintenance explicitly is REJECTED (400);
    # with no status filter, it IS returned (see FR2.3 default behavior / Assumptions).
})
seed_property_archived_published = Property.create({
    'name': 'seed_prop_archived_published', 'company_id': company_a.id,
    'property_status': 'available', 'publish_website': True, 'active': True, ...
})
seed_property_archived_published.write({'active': False})  # soft-deleted — must be EXCLUDED
seed_property_no_image = Property.create({
    'name': 'seed_prop_no_image', 'company_id': company_a.id,
    'property_status': 'available', 'publish_website': True, 'active': True,
    'image': False, ...
    # proves image_url == null
})
seed_property_with_image = Property.create({
    'name': 'seed_prop_with_image', 'company_id': company_a.id,
    'property_status': 'available', 'publish_website': True, 'active': True,
    'image': <base64 fixture bytes>, ...
    # proves image_url populated + image endpoint streams bytes
})

# Company B — isolation proof
seed_property_company_b_published = Property.create({
    'name': 'seed_prop_company_b_published', 'company_id': company_b.id,
    'property_status': 'available', 'publish_website': True, 'active': True, ...
    # used to prove: requesting company A's slug with this property's id in `ids`
    # silently excludes it (cross-company `ids` isolation test)
})
```

> ⚠️ **Regras**: all seed record names/logins prefixed `seed_`; idempotent (guard with `env.ref(..., raise_if_not_found=False)` or `search`+`create` pattern before creating); every user story's acceptance criteria has at least one seed record exercising both the "included" and "excluded" side of each gate (`publish_website`, `active`, `status`, cross-company `ids`).

---

### Non-Functional Requirements

**NFR1: Security** (per ADR-008, ADR-011, ADR-017, ADR-019)
- Both routes use `@require_jwt` only — no `@require_session`, no `@require_company`. This is an intentional, documented deviation from the "triple decorator on every controller" default (ADR-011), justified because there is no Odoo user/session on this path at all (identical justification already accepted for `cms_public_controller.get_public_page`).
- `.sudo()` is required and permitted here (unlike ADR-008's "never `.sudo()`" rule for authenticated transactional queries) because there is no `res.users` context for Odoo record rules to evaluate against on a JWT-only, session-less request. Tenant isolation is instead enforced **entirely via explicit domain filters** (`company_id = resolved`, plus the mandatory `active`/`publish_website` gates) built into every query — this is the same pattern already in production for CMS public pages, just applied to a second domain (properties).
- ADR-017 (session hijack / JWT fingerprint via IP+UA+Language) does not apply — that mechanism binds a JWT to an `api_session` record, which does not exist on this session-less path. No session token is issued or consumed here.
- ADR-019 (RBAC) does not apply — there are no user profiles/groups on this path; visibility is data-driven (`publish_website`/`active`/`company_id`), not role-driven.
- `# public endpoint` marker comment is mandatory above both `@http.route` declarations (project convention, `.github/copilot-instructions.md`).
- Anti-enumeration (ADR-008 principle 5): unknown `company_slug`, cross-company `ids`, and non-public property IDs on the image route all return the same generic 404 shape — never a distinguishing error message.

**NFR2: Performance** (per `knowledge_base/performance.md`)
- **Expected volume/growth**: this is a public, potentially crawler-facing (SEO) endpoint with no per-application rate limiting at this layer — expect meaningfully higher and less predictable request volume than the authenticated `/api/v1/properties` endpoint. Query efficiency matters more here, not less.
- **Query pattern / indexes needed**: the mandatory filter set is `company_id = X AND active = True AND publish_website = True`, optionally `AND property_status IN (...)`, optionally `AND id IN (...)`, ordered by `create_date DESC/ASC`, `LIMIT N`. `company_id` (Many2one) has **no explicit index today** (`index=True` is not set on the field in `property.py`); `publish_website`, `active`, `property_status` are plain Boolean/Selection columns with no index. **Recommend a new composite index** `real_estate_property(company_id, publish_website, active, create_date)` during implementation — this exact combination is the hot path for every request to this endpoint and does not yet exist. This is a follow-up implementation task, not a schema change mandated as part of this spec's Data Model contract (see Data Model section note).
- **N+1 risk**: the public projection touches two Many2one relations per row (`property_type_id.name`, `state_id.{name,code}`) and one implicit Many2one (`currency_id`). Because the controller issues a single `search()` and then iterates the resulting recordset (not per-ID `browse()` calls in a loop), Odoo's default field-prefetch batching should collapse these into a small, constant number of additional queries regardless of `limit` — this must be verified empirically (assert query count in the E2E test for User Story 1, e.g., via `self.assertQueryCount` or equivalent) rather than assumed.
- **Redis cache-aside applicability**: this endpoint is a strong candidate for a short-TTL (30–60s) cache-aside layer (`RedisClient.get_json`/`set_json`, key e.g. `public_properties:{company_slug}:{hash_of_query_params}`) given its public/high-traffic nature — **explicitly deferred to POST-MVP**, not required for initial implementation, because (a) it introduces cache-invalidation complexity for a fast-changing field (`property_status` changes should be visible reasonably quickly, e.g., a "sold" property shouldn't linger as "available" for very long) and (b) there is no existing precedent in this codebase for domain-entity (non-auth) Redis caching to build directly on. If adopted later, prefer TTL-based expiry over write-hook invalidation (simpler, and staleness window is bounded and acceptable for marketing data).
- **Async/Celery offload**: not applicable — this is a simple, bounded (`limit ≤ 100`) synchronous read with no heavy computation; no queue offload needed.
- Pagination: `limit` max 100 (hard clamp, not error), default 20 — identical semantics to `/api/v1/properties`.
- Image endpoint: streams raw bytes for a single, already-resized-by-nobody binary field — no thumbnailing/resizing is in scope; if source images are large, this is a known follow-up (not addressed here).

**NFR3: Quality** (per ADR-022)
- Code must pass: black, isort, flake8. Pylint ≥ 8.0/10.
- 100% test coverage on all validations (status allow-list, `ids` parsing, `sort` allow-list, `limit` parsing) per ADR-003.
- Zero new JavaScript console errors — N/A, no UI is introduced.

**NFR4: Data Integrity** (per knowledge_base/09-database-best-practices.md)
- No new tables/columns; existing `real.estate.property` and `thedevkitchen.cms.settings` constraints remain authoritative.
- `active` (ADR-015 soft delete) enforced unconditionally on this path, with no override — stricter than the authenticated endpoint by design (public data should never include archived records).

**NFR5: Frontend Compatibility** (per knowledge_base/10-frontend-views-odoo18.md)
- Not applicable — this is an API-only feature (headless consumers). No Odoo views, menus, or forms are introduced. Per the project's access model, this data is consumed exclusively by the headless frontend; there is no Odoo-UI equivalent to build or test.

---

## Technical Constraints

### Must Follow (from ADRs & Knowledge Base)

| Source | Requirement | Applied To |
|--------|-------------|------------|
| ADR-001 | Flat Odoo structure (no nested feature directories) | New controller file lives at `thedevkitchen_cms/controllers/`, new service at `thedevkitchen_cms/services/` |
| ADR-003 | 100% test coverage on validations; E2E for all critical flows | `status`/`ids`/`sort`/`limit` validation; cross-company isolation |
| ADR-004 | No new models introduced, so no new naming to apply — existing `real.estate.property` (legacy exception, already documented in `CLAUDE.md` §12 item 5) and `thedevkitchen.cms.settings` are reused as-is | N/A (read-only feature) |
| ADR-005 | Swagger/OpenAPI documentation for both new routes | Post-implementation task (see Artifacts) |
| ADR-007 | HATEOAS `_links.self` on the list response | List endpoint response |
| ADR-008 | 5 mandatory security principles — **with the documented public-endpoint exception** for the "never `.sudo()`" rule (no user context exists on this path) | Company/visibility domain filtering |
| ADR-009 | Headless architecture — this is the canonical use case (SSR frontend consuming REST, no Odoo UI) | Whole feature |
| ADR-011 | `@require_jwt` only (not the full triple) — documented, precedented deviation | Both new routes |
| ADR-015 | Soft-delete — `active=True` mandatory | List + image domain filters |
| ADR-016 | Postman collection update | Post-implementation task |
| ADR-018 | Query-param validation (status allow-list, `ids` integer parsing, `sort` enum, `limit` integer) | Both new routes |
| ADR-022 | Linting standards | All new Python files |
| Feature 017 pattern | Magic-bytes MIME detection; never redirect to `/web/content/` | New image-streaming endpoint (FR4) |
| CLAUDE.md §12.6 | This feature is the "deliberate, documented" counter-example to the flagged leads/sales/tags accidental-public-endpoint gap | Both new routes carry `# public endpoint` + explicit JWT-only rationale in code comments |

### Architecture Patterns

- **Controller Pattern**: New file `thedevkitchen_cms/controllers/cms_public_property_controller.py`, sibling to the existing `cms_public_controller.py`, same `# public endpoint` + `@require_jwt`-only pattern.
- **Service Layer**: New file `thedevkitchen_cms/services/cms_public_property_service.py` — houses `resolve_company_by_slug()` (reusable, could be extracted from `cms_public_controller.py`'s inline logic during implementation to avoid duplicating the slug-resolution query in two controllers), the filter-building/validation logic, and the public serializer (`serialize_public_property()`), keeping the controller thin per `.github/instructions/controllers.instructions.md`.
- **Module placement rationale**: `thedevkitchen_cms` depends on `quicksol_estate` (confirmed via manifest inspection), never the reverse — so this feature MUST live in `thedevkitchen_cms`, which already has visibility into both `real.estate.property` (via the dependency) and `thedevkitchen.cms.settings` (its own model).

---

## Success Criteria

### Backend
- [ ] Both user stories (list + image) implemented and tested.
- [ ] 100% unit test coverage on all input validations (status/ids/sort/limit).
- [ ] E2E API tests for: happy path, 401 (no JWT), 404 (unknown slug, non-public property), 400 (each invalid-param case), multi-tenant isolation (slug scoping + cross-company `ids`).
- [ ] Query-count assertion proving no N+1 on `property_type_id`/`state_id`/`currency_id` prefetch.
- [ ] Pylint ≥ 8.0, all linters passing (ADR-022).
- [ ] Public serializer output manually diffed against `serialize_property()` to confirm no PII fields leaked.

### Frontend
- N/A — API-only feature, no Odoo views/menus introduced.

### Seeds
- [ ] Seed file created with `seed_` prefix on all records.
- [ ] Seed covers: published+each of the 4 statuses, unpublished, archived, maintenance-published (default-vs-explicit-filter proof), no-image, with-image, cross-company property.
- [ ] Seed is idempotent.
- [ ] E2E tests use these seed records as their starting state.

### Documentation
- [ ] Swagger/OpenAPI generated for both new routes (ADR-005) — via `swagger-updater` skill.
- [ ] Postman collection updated (ADR-016) — via `postman-collection-manager` skill.
- [ ] Journey flowcharts created in `specs/029-public-property-listing/flowcharts.md` (one per user story).

---

## Constitution Feedback

### New Patterns Introduced

| Pattern | Description | Constitution Section | Priority |
|---------|-------------|---------------------|----------|
| Public JWT-Only Listing Endpoint (Company-Slug Resolved) | A second instance (beyond CMS pages) of the `auth="none" + @require_jwt`-only pattern, applied to a transactional domain entity (`real.estate.property`) instead of content (`cms.page`) — confirms this is a reusable pattern, not a one-off | Security Requirements → new subsection alongside existing Redis/Token patterns | Medium |
| Public Visibility Gate via Data Field (not RBAC) | First real usage of `publish_website` as a mandatory, non-overridable public-visibility gate, combined with `active` — a pattern any future "public X listing" feature should reuse instead of inventing a new flag | Architectural Patterns | Medium |
| Public JWT-Only Binary Streaming Endpoint | Second instance of the Feature 017 "never redirect to `/web/content/`, magic-bytes MIME" pattern, now also applied on a session-less/JWT-only auth path with an additional visibility-gate check baked into the lookup domain | Architectural Patterns | Low (extension of existing Feature 017 pattern, not new) |
| Cross-Module Slug Resolution Reuse | `thedevkitchen.cms.settings.company_slug`, originally built for CMS pages (Feature 021), is now reused by a non-CMS domain feature within the same module — worth noting as the intended reuse boundary (`thedevkitchen_cms` as the "public gateway" module for slug-scoped public data), not a coincidence | Architectural Patterns / module boundaries note | Low |

### New Entities/Relationships

None — this feature introduces no new persisted entities.

### Architectural Decisions

| Decision | Rationale | ADR Required? |
|----------|-----------|---------------|
| Public property endpoints live in `thedevkitchen_cms`, not `quicksol_estate` | Dependency direction (`thedevkitchen_cms → quicksol_estate`) makes this the only module that can see both `company_slug` and `real.estate.property` | No — follows existing, already-accepted module dependency graph; documented here for traceability |
| `@require_jwt`-only (no session/company decorators) is an accepted variant of ADR-011's triple-decorator default, for genuinely session-less public routes | Already precedented by `cms_public_controller.get_public_page`; this feature is the second confirming instance | No — recommend adding a short clarifying note to ADR-011 itself during the next ADR review cycle, but not required to block this feature |

### Constitution Update Recommendation

- **Update Required**: Yes (after implementation is validated — per project convention, constitution updates happen last)
- **Suggested Version Bump**: MINOR (new precedented pattern, no breaking change to existing principles)
- **Sections to Update**:
  - [ ] Security Requirements → document the "Public JWT-Only Endpoint" pattern as an explicit, named pattern (currently only implicit via the CMS pages precedent)
  - [ ] Architectural Patterns → "Public Visibility Gate via Data Field" and "Cross-Module Slug Resolution Reuse"
  - [ ] Reference Implementations → add Feature 029 entry once implemented

---

## Assumptions & Dependencies

**Assumptions**:
- When the `status` query param is omitted, no status filtering is applied — the endpoint returns all `publish_website=True` + `active=True` properties regardless of `property_status` (including, e.g., `maintenance` or `under_construction` if an agency mistakenly marks such a property as publishable). This mirrors the existing authenticated endpoint's "optional filter, no implicit default" convention. If the product intent is actually "always restrict to the 4 public-relevant statuses even with no explicit filter," that is a one-line change to FR2.3 during planning — flagged here as an assumption, not silently decided.
- `currency` in the public payload is sourced from `property.currency_id` (falls back to company currency per the existing model default) — no separate public currency-formatting endpoint is assumed to exist or be needed.
- The headless SSR frontend is expected to hold one application-level JWT (client-credentials grant) reused across all public-endpoint calls — no new JWT scope/application type is assumed to be needed beyond what already authenticates calls to the CMS public pages endpoint.

**Dependencies**:
- Existing modules: `thedevkitchen_cms` (hosts the new controller/service), `quicksol_estate` (owns `real.estate.property`), `thedevkitchen_apigateway` (`@require_jwt` decorator, JWT validation/Redis cache-aside per Feature 023).
- External services: PostgreSQL 16 (query execution), no new Redis usage required for MVP (see NFR2 cache-aside note).
- No new Python packages — `python-magic` (MIME detection) is already a project dependency (used by Feature 017/CMS media upload).

---

## Implementation Phases

### Phase 1: Foundation
- New service module (`cms_public_property_service.py`): slug resolution (reusing/refactoring the existing inline logic from `cms_public_controller.py` if a shared helper is warranted), filter/validation logic, public serializer.
- Unit tests for all validation branches.

### Phase 2: API Layer
- New controller (`cms_public_property_controller.py`) with the two routes (list, image).
- Query-count verification for N+1 prevention.

### Phase 3: Testing & Quality
- E2E API test scripts (`integration_tests/test_public_properties*.sh`).
- Linting (black/isort/flake8/pylint) pass.

### Phase 4: Documentation & Artifacts
- Swagger/OpenAPI (via `swagger-updater` skill).
- Postman collection (via `postman-collection-manager` skill).
- Journey flowcharts (`specs/029-public-property-listing/flowcharts.md`).
- Constitution update (after implementation validated).

---

## Artifacts to Generate

> **⚠️ OBRIGATÓRIO**: Consult `.claude/skills/development-best-practices/SKILL.md` before writing any model/controller/endpoint code for this feature. Use `swagger-updater` and `postman-collection-manager` skills for their respective artifacts — never hand-edit static OpenAPI/Postman files.

After spec approval, the following should be generated (in order):

1. **Implementation plan** (`plan-idea.md` in this same directory) — via `superpowers:writing-plans`, including an explicit verification-before-completion step using `bash scripts/validate_coverage.sh` and the targeted `integration_tests/test_public_properties*.sh` scripts (not the full suite, to avoid the Odoo login-cooldown issue documented in this project's workflow notes).
2. **Constitution Update** — only after implementation is validated (per project convention: constitution updates are the LAST step, not concurrent with implementation).
3. **Swagger/Postman** — generated/updated as part of verification-before-completion, in the same pass as tests (per project convention: these are NOT deferred like the constitution update).
4. **Journey Flowcharts** (`specs/029-public-property-listing/flowcharts.md`) — one Mermaid diagram per user story (3 total), each showing: actor (SSR frontend), endpoint calls (method + path), decision points (slug found?, JWT valid?, filters valid?, image present?).

---

## Validation Checklist

### Backend Validation
- [x] Seção "Out of Scope / Non-Goals" preenchida com itens específicos da feature
- [x] Todos os requisitos de ADR referenciados e seguidos (incluindo o desvio documentado de ADR-011/ADR-008 para rotas públicas)
- [x] Padrões da knowledge base aplicados (performance.md analysis in NFR2, not boilerplate)
- [x] Multi-tenancy corretamente especificado (ADR-008) — via explicit domain filtering, documented exception to record-rule/sudo() convention explained
- [x] Segurança adequadamente definida (ADR-011 deviation documented and justified; ADR-017/019 explicitly marked N/A with rationale)
- [x] Estratégia de teste completa - unit + E2E API (ADR-003)
- [x] API segue os padrões REST + HATEOAS (ADR-007) — `_links.self` on list response
- [x] Design de banco de dados — no new schema; existing 3FN models reused; recommended index flagged for implementation
- [x] Tratamento de erros especificado (ADR-018) — full error table for both endpoints
- [x] Requisitos de qualidade de código definidos (ADR-022)

### Frontend Validation
- N/A — no Odoo views/menus introduced; feature is consumed exclusively by the headless frontend, per this project's access model.
