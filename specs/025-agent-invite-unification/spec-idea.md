# Feature Specification: Unify Agent Creation into the Invite Flow (Deprecate POST /api/v1/agents)

**Feature Branch**: `025-agent-invite-unification`
**Created**: 2026-07-15
**Status**: Draft
**ADR References**: ADR-004, ADR-005, ADR-007 (planned, not yet implemented on these endpoints), ADR-008, ADR-009, ADR-011, ADR-015, ADR-016, ADR-018, ADR-019, ADR-022

---

## ✅ Decisions (all resolved — see "Constitution Feedback" and inline callouts)

This spec was generated without an interactive clarification round (the `AskUserQuestion` tool was unavailable in the generating session). Decisions #1 and #2 below have since been **confirmed by the user**: `POST /api/v1/agents` is to be **removed** (not left running indefinitely) once the unified invite flow is implemented and validated, and Swagger/OpenAPI regeneration is a **mandatory, explicit deliverable** of this feature (not a "nice to have" follow-up). Decision #3 remains open.

1. **✅ RESOLVED — Deprecated-endpoint fate: REMOVE after implementation.** `POST /api/v1/agents` is deprecated during the implementation/validation window (Phase 2–3: `Deprecation`/`Sunset` headers, OpenAPI `deprecated: true`, Postman relabeling — see User Story 2) and then **physically removed** (route unregistered, controller method deleted, `thedevkitchen.api.endpoint` registry record removed) once the unified `POST /api/v1/users/invite` flow is implemented, tested, and validated end-to-end. This replaces the earlier default of "deprecate indefinitely, keep working." See the new **User Story 4** and **FR6 (Endpoint Removal)** below for the concrete removal criteria and steps.
2. **✅ RESOLVED — Swagger/OpenAPI must be updated.** Regenerating Swagger/OpenAPI is a mandatory part of this feature's Definition of Done, covering both the interim deprecation state (Phase 2–3) and the final removal state (Phase 5): the `POST /api/v1/agents` operation must first be marked `deprecated: true` with a pointer to the replacement flow, and then be **removed entirely from the generated spec** once the endpoint itself is deleted. Use the `swagger-updater` skill for both passes — never hand-edit static OpenAPI files (per ADR-005, the spec is generated dynamically from the `thedevkitchen_api_endpoint` table).
3. **✅ RESOLVED — Nested `agent` object confirmed.** Keep the existing "profile-first" invite contract (`POST /api/v1/profiles` then `POST /api/v1/users/invite` with `profile_id`), and add an **optional nested `agent` object** to the `POST /api/v1/users/invite` request body, applicable only when the target profile's `profile_type_id.code == 'agent'`. The flat, `create_agent`-style payload alternative (all fields at the top level, no pre-existing `profile_id`) was considered and rejected — it would fork the invite contract per profile type and duplicate the profile-creation validation that `POST /api/v1/profiles` already owns.

All three open decisions are now resolved. The sections below (FR2, FR3, request/response contracts, data model, RBAC matrix, removal plan, test strategy) already reflect these confirmed decisions — no further revision needed before handing off to planning.

---

## Executive Summary

Today, inviting a new "agent" profile through `POST /api/v1/users/invite` creates a `res.users` login linked to a `thedevkitchen.estate.profile` record, but — unlike `POST /api/v1/agents` — it never creates the corresponding `real.estate.agent` domain record (CRECI license, bank/commission payout data). This means the only way to fully onboard an agent (record + login) today is two disconnected calls to two different subsystems that duplicate profile-creation logic and validation. This feature unifies the two paths: when the profile behind an invite is of type `agent`, `POST /api/v1/users/invite` applies the same field validation used by `POST /api/v1/agents` (CRECI format/uniqueness, bank fields) and atomically creates the `real.estate.agent` record alongside the `res.users` account, in the same transaction as the invite. `POST /api/v1/agents` is first marked deprecated (headers + OpenAPI + Postman, functionally unchanged during this window) to give existing integrations a migration signal, and is then **removed entirely** — route, controller, and OpenAPI/Postman entries — once the unified flow is implemented and validated (Open Decision #1, confirmed).

---

## Current State (as verified in code, not assumed)

### `POST /api/v1/agents` (`quicksol_estate/controllers/agent_api.py::create_agent`)
- Auth: `@require_jwt` + `@require_session` + `@require_company` (ADR-011), plus manual RBAC check (`group_real_estate_manager` or `base.group_system` only).
- Request validated against `SchemaValidator.AGENT_CREATE_SCHEMA`:
  - **Required**: `name` (3–255 chars), `cpf` (11 digits after stripping mask), `email` (contains `@` and `.`), `company_id` (int).
  - **Optional**: `phone`, `mobile`, `creci` (≥4 chars, further validated/normalized by `CreciValidator`, unique per `company_id` via `@api.constrains`), `hire_date`, `bank_name`, `bank_account`, `pix_key`.
- Behavior: creates a `thedevkitchen.estate.profile` (profile_type `agent`) **and** a `real.estate.agent` record in the same call, atomically. **Does NOT create a `res.users` record and does NOT send any email.** No invite/login is issued.
- Response: 201 with agent data + `_links` (`self`, `properties`, `deactivate`, `profile`).

### `POST /api/v1/users/invite` (`thedevkitchen_user_onboarding/controllers/invite_controller.py::invite_user`)
- Auth: same triple decorator + `@trace_http_request`.
- Request: only accepts `profile_id` (must reference a pre-existing `thedevkitchen.estate.profile`, created earlier via `POST /api/v1/profiles`, which validates `PROFILE_CREATE_SCHEMA`: required `name`, `company_id`, `document`, `email`, `birthdate`, `profile_type_id`; optional `phone`, `mobile`, `occupation`, `hire_date` — **no CRECI, no bank fields**).
- Behavior: checks the profile doesn't already have a linked `res.users` (409 if it does), calls `InviteService.check_authorization()` against the ADR-024 authorization matrix, calls `InviteService.create_user_from_profile()` which creates **only** a `res.users` record (locked, `signup_pending=True`) linked to the profile via `partner_id`, generates a SHA-256-hashed invite token (Feature 009 pattern), and sends the invite email. **It never creates a `real.estate.agent` record, regardless of the profile's type.**
- Gap confirmed in code: `real.estate.agent.create()` already has logic (lines ~438–453 of `models/agent.py`) to sync cadastral fields (`name`, `cpf`←`document`, `email`, `phone`, `mobile`, `company_id`, `hire_date`) from a `profile_id` via `setdefault()` — i.e., the model layer is *already* prepared to create an agent record from an existing profile; only the controller-level orchestration in `invite_user` is missing.
- Authorization matrix for who can invite an `agent` profile (`InviteService.INVITE_AUTHORIZATION`, ADR-024): `owner`, `director`, `manager` groups. (Note: broader than `create_agent`'s manager-or-admin-only check — see FR4 below for the reconciliation this feature must apply.)

### Consequence of the gap
An agency using only the invite flow today ends up with agents who have login access but **no** `real.estate.agent` record — breaking every agent-scoped feature (assignments, commission rules, performance, CRECI compliance tracking) for API-invited agents. This is the functional bug this feature fixes, not just a code-organization cleanup.

---

## User Scenarios & Testing

### User Story 1: Manager invites a new Agent with full cadastral + license data (Priority: P1) 🎯 MVP

**As a** Manager or Owner (per ADR-024 authorization matrix)
**I want to** invite a new agent and have their CRECI license and bank/commission payout data captured in the same flow
**So that** the agent has both system access and a complete, functional `real.estate.agent` record without a second manual step

**Acceptance Criteria**:
- [ ] Given a profile with `profile_type_id.code == 'agent'` already created via `POST /api/v1/profiles`, when `POST /api/v1/users/invite` is called with `profile_id` and a valid nested `agent` object (`creci`, `hire_date`, `bank_name`, `bank_account`, `pix_key` — all optional per current `AGENT_CREATE_SCHEMA` parity), then the response is 201 and includes both `user.id` and the newly created `agent.id`, and a `real.estate.agent` record exists with `profile_id` set to the invited profile.
- [ ] Given the same setup but `agent.creci` fails `CreciValidator` format validation, when `POST /api/v1/users/invite` is called, then the response is 400 `validation_error` and **no** `res.users`, invite token, or `real.estate.agent` record is created (atomic rollback — no partial user-without-agent state, reproducing today's `create_agent` guarantee).
- [ ] Given `agent.creci` is well-formed but already used by another active agent in the **same** `company_id`, when `POST /api/v1/users/invite` is called, then the response is 409 `conflict` (mirrors `real.estate.agent._check_creci_format` uniqueness constraint) and no records are created.
- [ ] Given a profile of type `agent` and no `agent` object at all in the request body, when `POST /api/v1/users/invite` is called, then the flow succeeds exactly as today (agent-specific fields are all optional) **plus** a bare `real.estate.agent` record is still created (using only the cadastral data already on the profile — this is the bug fix: agent record creation is no longer optional/skippable for `agent`-type profiles).
- [ ] Given a profile from a **different** company than the requester's active company (`X-Company-ID` header), when `POST /api/v1/users/invite` is called, then the response is 404 `not_found` (multi-tenancy isolation per ADR-008 — do not leak cross-company existence).
- [ ] Given the requester is an `agent`-group user (not owner/director/manager), when `POST /api/v1/users/invite` targets an `agent` profile, then the response is 403 `forbidden` (ADR-024 authorization matrix unchanged — agents cannot invite other agents).

**Test Coverage** (per ADR-003):

| Type | Test Name | Description | Status |
|------|-----------|-------------|--------|
| Unit | `test_invite_agent_creci_format_invalid()` | CRECI format validation rejects invite, no records created | ⚠️ Required |
| Unit | `test_invite_agent_creci_uniqueness_same_company()` | Duplicate CRECI within company blocked (409) | ⚠️ Required |
| Unit | `test_invite_agent_creci_allowed_across_companies()` | Same CRECI number allowed in different `company_id` | ⚠️ Required |
| Unit | `test_invite_agent_bank_fields_optional()` | Bank fields absent → agent still created with blanks | ⚠️ Required |
| Unit | `test_invite_agent_required_fields_from_profile()` | name/cpf/email/company_id sourced correctly from profile via `setdefault()` sync | ⚠️ Required |
| Unit | `test_invite_non_agent_profile_unaffected()` | Non-`agent` profile types skip agent-creation branch entirely | ⚠️ Required |
| E2E (API) | `test_manager_invites_agent_full_flow()` | profile create → invite w/ agent object → user + agent + token all exist | ⚠️ Required |
| E2E (API) | `test_invite_agent_atomic_rollback_on_validation_failure()` | Invalid CRECI → no `res.users` row committed (`search` returns empty post-call) | ⚠️ Required |
| E2E (API) | `test_multitenancy_isolation_invite_cross_company()` | Profile in company B invited by company A user → 404 | ⚠️ Required |
| E2E (API) | `test_agent_cannot_invite_agent()` | 403 for requester in `group_real_estate_agent` | ⚠️ Required |

### User Story 2: `POST /api/v1/agents` is deprecated (transition window) before removal (Priority: P1) 🎯 MVP

**As an** existing API consumer that calls `POST /api/v1/agents` directly (agent record without login)
**I want to** receive a clear, machine-readable deprecation signal before the endpoint is removed
**So that** I have time to migrate to `POST /api/v1/profiles` + `POST /api/v1/users/invite` before my integration breaks

**Acceptance Criteria**:
- [ ] Given a valid `AGENT_CREATE_SCHEMA` payload, when `POST /api/v1/agents` is called during the deprecation window (Phase 2–3, before removal), then the response is unchanged (201, same body shape) — **behavior parity during the transition, not an immediate breaking change**.
- [ ] Given any call to `POST /api/v1/agents` during the deprecation window, when the response is returned, then it includes a `Deprecation: true` header and a `Sunset: <date>` header, and the response body's `_links` includes a `"deprecated_notice"` link pointing at the new recommended flow (`/api/v1/profiles` → `/api/v1/users/invite`).
- [ ] Given the OpenAPI spec is regenerated (`GET /api/v1/openapi.json`) during the deprecation window, when the `POST /api/v1/agents` operation is inspected, then it has `"deprecated": true` and a `description` pointing to the replacement flow.
- [ ] Given the Postman collection is regenerated during the deprecation window, when the "Agents" folder is inspected, then `POST /api/v1/agents` is renamed/annotated `"[DEPRECATED] Create Agent (legacy)"` and a new request `"Invite Agent (recommended)"` demonstrates the unified flow.

**Test Coverage**:

| Type | Test Name | Description | Status |
|------|-----------|-------------|--------|
| Unit | `test_create_agent_response_includes_deprecation_headers()` | `Deprecation`/`Sunset` headers present | ⚠️ Required |
| E2E (API) | `test_create_agent_legacy_behavior_unchanged()` | Existing integration test suite for `create_agent` still passes unmodified during the deprecation window | ⚠️ Required |
| Integration | `test_openapi_agents_post_marked_deprecated()` | `deprecated: true` present in generated spec (ADR-005) | ⚠️ Required |

### User Story 4: `POST /api/v1/agents` is removed once the unified flow is validated (Priority: P1) 🎯 MVP

**As the** platform team maintaining the API surface
**I want to** physically remove `POST /api/v1/agents` once `POST /api/v1/users/invite` fully covers agent creation
**So that** the API surface has a single, validated path for onboarding agents and no duplicated validation logic to maintain

**Acceptance Criteria**:
- [ ] Given User Stories 1–3 are implemented, tested, and passing (unit + E2E per ADR-003), when the removal step of this feature is executed, then the `create_agent` route/controller method in `quicksol_estate/controllers/agent_api.py` is deleted (not just disabled), and its `thedevkitchen.api.endpoint` registry row is deleted.
- [ ] Given the endpoint has been removed, when `POST /api/v1/agents` is called, then the response is a standard 404 (route no longer registered) — the same behavior any unregistered route returns, not a custom "endpoint removed" message.
- [ ] Given the endpoint has been removed, when the OpenAPI spec is regenerated (`GET /api/v1/openapi.json`), then the `POST /api/v1/agents` operation no longer appears in the spec at all.
- [ ] Given the endpoint has been removed, when the Postman collection is regenerated, then the legacy `"[DEPRECATED] Create Agent (legacy)"` request is deleted from the collection, leaving only `"Invite Agent (recommended)"`.
- [ ] Given the endpoint has been removed, when the existing `create_agent` integration test suite is inspected, then those test files are deleted (superseded by User Story 1's `test_invite_agent_*`/`test_manager_invites_agent_full_flow` suite) rather than left to fail against a nonexistent route.

**Test Coverage**:

| Type | Test Name | Description | Status |
|------|-----------|-------------|--------|
| E2E (API) | `test_create_agent_route_returns_404_after_removal()` | Confirms the route is gone, not just deprecated | ⚠️ Required |
| Integration | `test_openapi_agents_post_absent_after_removal()` | `POST /api/v1/agents` no longer present in generated OpenAPI spec | ⚠️ Required |
| Integration | `test_postman_collection_legacy_agent_request_removed()` | Legacy request no longer present in regenerated Postman collection | ⚠️ Required |

**Removal preconditions (all must hold before executing this story)**:
1. User Story 1 (unified invite flow) is implemented and its full test suite passes.
2. User Story 2's deprecation window has been in place for at least one full release cycle so consumers had a chance to see the `Deprecation`/`Sunset` headers (exact duration is a rollout/release-management decision, not a spec-level gate).
3. A check of `thedevkitchen_apigateway`'s API access log (per `modules-custom.md`) confirms no unexpected production traffic is still hitting `POST /api/v1/agents`, or the team has explicitly accepted the migration risk for any remaining callers.

### User Story 3: Manager resends an invite for an agent profile without re-supplying agent data (Priority: P2)

**As a** Manager
**I want to** resend an invite email for an agent whose `real.estate.agent` record already exists
**So that** I don't need to know or resend CRECI/bank data again

**Acceptance Criteria**:
- [ ] Given a `res.users` with `signup_pending=True` already linked to an agent profile (and its `real.estate.agent` record already exists from the original invite), when `POST /api/v1/users/resend-invite` is called, then it only regenerates the token/email — **no** agent-creation logic runs again (idempotent, no duplicate `real.estate.agent` row, no 409).
- [ ] Given `resend-invite` is called for a user whose agent record does NOT exist (edge case: agent record was manually deleted after invite), when called, then behavior is unchanged from today (resend only touches the token/email layer) — flagged as an existing edge case, not newly introduced by this feature.

**Test Coverage**:

| Type | Test Name | Description | Status |
|------|-----------|-------------|--------|
| Unit | `test_resend_invite_does_not_recreate_agent()` | No new `real.estate.agent` row after resend | ⚠️ Required |

---

## Requirements

### Functional Requirements

**FR1: Unified Field Validation**
- FR1.1: When `POST /api/v1/users/invite` targets a profile with `profile_type_id.code == 'agent'`, the request body MAY include an optional `agent` object.
- FR1.2: If present, `agent.creci` MUST pass the same validation as `AGENT_CREATE_SCHEMA` today: `len(creci) >= 4`, normalized via `CreciValidator.normalize()`, and unique per `company_id` among active agents (mirrors `real.estate.agent._check_creci_format`).
- FR1.3: If present, `agent.bank_account`, `agent.bank_name`, `agent.pix_key`, `agent.hire_date` MUST be type-validated identically to `AGENT_CREATE_SCHEMA`'s optional-field rules (all strings, no additional format constraints beyond what the model's own field constraints already enforce).
- FR1.4: Core identity fields (`name`, `cpf`/`document`, `email`, `company_id`) are NOT re-collected in the `agent` object — they are already required and validated by `PROFILE_CREATE_SCHEMA` at profile-creation time (`POST /api/v1/profiles`), and are propagated into the new `real.estate.agent` record via the existing `profile_id` sync logic in `real.estate.agent.create()`.
- FR1.5: Validation of the `agent` object MUST occur BEFORE any `res.users` record is created (fail fast, no partial state).

**FR2: Atomic Agent Record Creation During Invite**
- FR2.1: When the target profile's type is `agent`, `invite_user` MUST create a `real.estate.agent` record (via `profile_id=profile_record.id` plus any provided `agent` object fields) in the SAME database transaction as the `res.users` creation and the invite-token generation.
- FR2.2: If `real.estate.agent` creation fails for any reason (validation, DB constraint), the entire request MUST fail atomically — no `res.users`, no invite token, no email sent (Odoo's implicit transaction rollback on unhandled exception, consistent with the "Atomic Dual Record Creation" pattern already documented in the constitution for portal entities).
- FR2.3: The invite email MUST only be sent after both the `res.users` and `real.estate.agent` records are successfully committed to the transaction (email send remains best-effort/non-blocking per existing `email_sent` handling — a failed email must not roll back the transaction, matching current behavior).
- FR2.4: For all other profile types (`owner`, `director`, `manager`, `prospector`, `receptionist`, `financial`, `legal`, `property_owner`, `tenant`), `invite_user` behavior is UNCHANGED — no domain-entity creation is added by this feature for those types (out of scope; see Assumptions).

**FR3: Response Contract**
- FR3.1: When an `agent` record is created as part of the invite, the `201` response body's `data` object MUST include `agent_id` (the new `real.estate.agent` id) alongside the existing `id` (user id), `profile_id`.
- FR3.2: HATEOAS `links` MUST add `"agent": "/api/v1/agents/{agent_id}"` when an agent record was created.

**FR4: Authorization Reconciliation**
- FR4.1: The invite flow's existing ADR-024 authorization matrix (`owner`/`director`/`manager` may invite `agent`) governs who can trigger this unified flow — this is BROADER than `create_agent`'s current manager-or-system-admin-only check.
- FR4.2: This feature does NOT change `create_agent`'s existing authorization (manager or `base.group_system` only) — the two endpoints may have different authorization scopes during the deprecation period; this discrepancy MUST be called out explicitly in both endpoints' OpenAPI descriptions so consumers are not surprised (`director`/`owner` roles gain a *new* capability via the invite path that they did not have via `create_agent`).
- FR4.3: `director` and `owner` inviting an `agent` profile is intentional per the existing, unmodified ADR-024 matrix — this feature does not need to add new RBAC rules, only route the already-authorized action through the new agent-creation code path.

**FR5: Deprecation of `POST /api/v1/agents` (transition window)**
- FR5.1: Add `Deprecation: true` and `Sunset: <date>` HTTP response headers to every response from `create_agent` (success and error paths), per the IETF `Deprecation` HTTP header draft convention already implicitly referenced by ADR-005's OpenAPI tooling.
- FR5.2: Update the `thedevkitchen.api.endpoint` registry record (ADR-005 dynamic OpenAPI generation source) for this route to `deprecated=True` with a `description` pointing consumers to `POST /api/v1/profiles` + `POST /api/v1/users/invite`.
- FR5.3: During the transition window, `create_agent`'s functional behavior (fields, validation, response body shape minus the new headers) is UNCHANGED — this is a deprecation notice, not an immediate behavior migration.
- FR5.4: Update the Postman collection (ADR-016) per User Story 2's acceptance criteria (relabel, do not yet delete).

**FR6: Removal of `POST /api/v1/agents` (confirmed — Open Decision #1)**
- FR6.1: Once User Story 4's removal preconditions are satisfied, delete the `create_agent` controller method and its `@http.route` registration from `quicksol_estate/controllers/agent_api.py` entirely — this is a hard removal, not a permanent deprecation.
- FR6.2: Delete the corresponding `thedevkitchen.api.endpoint` registry row so the dynamic OpenAPI generator (ADR-005) stops emitting the operation.
- FR6.3: Regenerate the OpenAPI spec via the `swagger-updater` skill and confirm `POST /api/v1/agents` no longer appears (this is a mandatory documentation step, not optional follow-up — see Open Decision #2).
- FR6.4: Update the Postman collection via the `postman-collection-manager` skill to delete the legacy `"[DEPRECATED] Create Agent (legacy)"` request, leaving only the unified `"Invite Agent (recommended)"` flow.
- FR6.5: Delete `create_agent`'s now-superseded integration/unit tests rather than leaving them to fail against a removed route; their coverage is superseded by User Story 1's test suite.

### Data Model (per ADR-004, knowledge_base/09-database-best-practices.md)

**No new entities are introduced.** This feature only changes controller-level orchestration across two existing entities:

**Entity: `real.estate.agent`** (existing, unchanged schema)
- **Model Name**: `real.estate.agent` (pre-existing; NOT renamed — out of scope, and changing it would violate the "no unrelated renames" principle for a controller-orchestration feature)
- Relevant existing fields used by this feature: `profile_id` (Many2one → `thedevkitchen.estate.profile`, already supports `setdefault()` sync from profile), `creci`, `creci_normalized` (computed, stored, indexed), `bank_name`, `bank_account`, `bank_account_type`, `pix_key`, `hire_date`, `company_id` (required FK, multi-tenancy).
- Existing constraint reused, not modified: `_check_creci_format` (`@api.constrains('creci', 'creci_normalized', 'company_id')`) — uniqueness of `creci_normalized` scoped to `company_id`.

**Entity: `thedevkitchen.estate.profile`** (existing, unchanged schema)
- No schema change. `profile_type_id.code` is read to branch the new logic; `document`, `name`, `email`, `phone`, `mobile`, `hire_date`, `company_id` are the fields propagated into the new `real.estate.agent` record (already-existing `setdefault()` sync in `agent.py::create()`).

**Entity: `res.users`** (existing, unchanged schema)
- No schema change. Creation logic (`InviteService.create_user_from_profile`) unchanged.

**New validation surface (controller-level only, no migration required)**:
```python
# thedevkitchen_user_onboarding/controllers/invite_controller.py (new logic sketch)
agent_payload = data.get("agent")  # optional nested object
if profile_type == "agent":
    if agent_payload:
        is_valid, errors = SchemaValidator.validate_agent_invite_extra(agent_payload)
        if not is_valid:
            return self._error_response(400, "validation_error", ", ".join(errors))
    # ... create user (existing) ...
    agent_vals = {"profile_id": profile_record.id}
    if agent_payload:
        agent_vals.update({k: v for k, v in agent_payload.items() if v is not None})
    agent = request.env["real.estate.agent"].sudo().create(agent_vals)  # raises on CRECI conflict -> rolls back whole request
```

**New schema (extends `quicksol_estate/controllers/utils/schema.py::SchemaValidator`)**:
```python
AGENT_INVITE_EXTRA_SCHEMA = {
    "required": [],
    "optional": ["creci", "hire_date", "bank_name", "bank_account", "pix_key"],
    "types": {
        "creci": str, "hire_date": str, "bank_name": str,
        "bank_account": str, "pix_key": str,
    },
    "constraints": {
        "creci": lambda v: len(v) >= 4 if v else True,
    },
}
```
(Full CRECI normalization/uniqueness enforcement stays in the model's `@api.constrains`, not duplicated in the schema layer — consistent with how `create_agent` already relies on the model constraint, not just the schema, for the uniqueness check.)

**Record Rules**: No new record rules — both entities already have company-scoped `ir.rule`s in place (ADR-008/ADR-019); this feature does not touch record rules.

### API Endpoints (per ADR-007, ADR-009, ADR-011)

**Endpoint: POST /api/v1/users/invite (modified)**

| Attribute | Value |
|-----------|-------|
| **Method** | POST |
| **Path** | `/api/v1/users/invite` |
| **Authentication** | `@require_jwt` + `@require_session` + `@require_company` (unchanged) |
| **Authorization** | Per ADR-024 matrix: `owner`, `director`, `manager` may invite `agent` profiles (unchanged authorization, now also gates agent-record creation) |
| **Rate Limit** | None currently (consistent with existing endpoint) |

**Request Body** (extends existing contract, per ADR-018):
```json
{
  "profile_id": "integer (required, existing profile with profile_type_id.code == 'agent')",
  "agent": {
    "creci": "string (optional, min 4 chars, format+uniqueness validated per company)",
    "hire_date": "string (optional, ISO date)",
    "bank_name": "string (optional)",
    "bank_account": "string (optional, max 20 chars per model field)",
    "pix_key": "string (optional)"
  }
}
```
(The `agent` object is ignored/optional for non-agent profile types; including it for a non-agent profile is a no-op, not an error — avoids surprising 400s for clients that always send a generic payload shape.)

**Response Success (201)** (per ADR-007 HATEOAS — note: full HATEOAS `links` array format per ADR-007 is planned but not yet implemented on this endpoint; current response uses the existing `links` dict shape, extended here, not converted):
```json
{
  "success": true,
  "data": {
    "id": 42,
    "name": "Jane Agent",
    "email": "jane@example.com",
    "document": "12345678901",
    "profile": "agent",
    "profile_id": 17,
    "agent_id": 88,
    "signup_pending": true,
    "invite_sent_at": "2026-07-15T10:00:00Z",
    "invite_expires_at": "2026-07-16T10:00:00Z"
  },
  "message": "User invited successfully. Email sent to jane@example.com",
  "links": {
    "self": "/api/v1/users/42",
    "resend_invite": "/api/v1/users/42/resend-invite",
    "collection": "/api/v1/users",
    "profile": "/api/v1/profiles/17",
    "agent": "/api/v1/agents/88"
  }
}
```

**Error Responses** (extends existing envelope):
| Code | Condition | Response |
|------|-----------|----------|
| 400 | `agent.creci` fails format validation | `{"success": false, "error": "validation_error", "message": "...", "details": {...}}` |
| 403 | Requester not authorized for `agent` profile type (ADR-024) | `{"success": false, "error": "forbidden", "message": "..."}` |
| 404 | Profile not found / cross-company (ADR-008 anti-leakage) | `{"success": false, "error": "not_found", "message": "..."}` |
| 409 | Profile already has a linked user, OR `agent.creci` already used in company | `{"success": false, "error": "conflict", "message": "...", "details": {...}}` |
| 500 | Unexpected error (includes agent-creation failures not otherwise categorized) | `{"success": false, "error": "internal_error", "message": "..."}` |

**Endpoint: POST /api/v1/agents (deprecated → removed)**

| Attribute | Value |
|-----------|-------|
| **Method** | POST |
| **Path** | `/api/v1/agents` |
| **Status (transition window, Phase 2–3)** | **DEPRECATED** — functionally unchanged (FR5.3), new response headers only |
| **Status (after removal, Phase 5)** | **REMOVED** — route, controller method, `thedevkitchen.api.endpoint` row, tests, OpenAPI operation, and Postman request all deleted (FR6) |
| **Authentication (during transition)** | `@require_jwt` + `@require_session` + `@require_company` (unchanged) |
| **Authorization (during transition)** | `group_real_estate_manager` or `base.group_system` only (unchanged — narrower than the invite flow's ADR-024 matrix, see FR4.2) |
| **New Response Headers (during transition)** | `Deprecation: true`, `Sunset: <date>` |

During the transition window, no other changes to this endpoint's contract. After removal, calling this path returns a standard 404 (unregistered route).

### Seed Data (MANDATORY — all solution types)

**Seed: Companies**
```python
seed_company_a = env['res.company'].create({'name': 'Empresa A (Seed 025)'})
seed_company_b = env['res.company'].create({'name': 'Empresa B (Seed 025)'})
```

**Seed: Users per Role**
```python
seed_users = {
    'owner_a':      {'login': 'seed_owner_a_025@test.com',      'company': seed_company_a, 'group': 'group_real_estate_owner'},
    'manager_a':    {'login': 'seed_manager_a_025@test.com',    'company': seed_company_a, 'group': 'group_real_estate_manager'},
    'agent_a':      {'login': 'seed_agent_a_025@test.com',      'company': seed_company_a, 'group': 'group_real_estate_agent'},
    'manager_b':    {'login': 'seed_manager_b_025@test.com',    'company': seed_company_b, 'group': 'group_real_estate_manager'},  # isolation
}
```

**Seed: Profile Type**
```python
# Reuse existing seeded 'agent' profile_type (thedevkitchen.profile.type, code='agent') — do not duplicate.
```

**Seed: Domain Entities**
```python
# Profile pending invite (company A) — used by User Story 1 happy-path tests
seed_profile_pending_agent = env['thedevkitchen.estate.profile'].create({
    'name': 'Seed Agent Pending', 'company_id': seed_company_a.id,
    'profile_type_id': agent_profile_type.id,
    'document': '<valid CPF>', 'email': 'seed_agent_pending_025@test.com',
    'birthdate': '1990-01-01',
})

# Existing agent with a CRECI already registered (company A) — used for the uniqueness-conflict test
seed_agent_existing_creci = env['real.estate.agent'].create({
    'name': 'Seed Agent Existing', 'cpf': '<valid CPF>', 'email': 'seed_agent_existing_025@test.com',
    'company_id': seed_company_a.id, 'creci': 'CRECI-SP-999999-J',
})

# Profile pending invite (company B) — used for cross-company isolation test
seed_profile_pending_agent_b = env['thedevkitchen.estate.profile'].create({
    'name': 'Seed Agent Pending B', 'company_id': seed_company_b.id,
    'profile_type_id': agent_profile_type.id,
    'document': '<valid CPF>', 'email': 'seed_agent_pending_b_025@test.com',
    'birthdate': '1990-01-01',
})
```

> **Rules**: All seed IDs/logins use `seed_` prefix (project convention already followed by Features 019/024). Idempotent creation (guard with `search()` before `create()` in the actual seed script). Every acceptance criterion above has a corresponding seed record to start from.

---

### Non-Functional Requirements

**NFR1: Security** (per ADR-008, ADR-011, ADR-017, ADR-019)
- `POST /api/v1/users/invite` keeps the existing triple-decorator chain; no new public surface is introduced.
- The new `agent` object does not accept `company_id` (it is always derived from the already-validated profile, closing off a potential company-spoofing vector that a naive flat-payload design would have reopened — this is a concrete security reason behind the confirmed nested-object shape, decision #3).
- Anti-enumeration unaffected: 404 for cross-company profile access (unchanged from current `invite_user` behavior).

**NFR2: Performance** (per `knowledge_base/performance.md`)
- **Data volume**: Agent invites are a low-frequency, admin-driven operation (order of tens per company per month, not a hot list/read path) — no pagination or list-endpoint concerns apply to this feature.
- **Query pattern / indexing**: The added `real.estate.agent.create()` call reuses the existing `creci_normalized` indexed field and its existing `@api.constrains` uniqueness check (`search()` scoped by `company_id` + `creci_normalized`, both already indexed per `knowledge_base/performance.md` — "real_estate_agent(creci_normalized) — indexed lookup field"). No new index is required.
- **N+1 risk**: None introduced — this feature adds exactly one additional `create()` call (single INSERT) per invite request; it does not add any list/read endpoint or related-field traversal.
- **Redis cache-aside applicability**: Not applicable. This is a low-frequency write path (invite issuance), not a read/auth hot path — it does not qualify for the JWT/session cache-aside pattern (Feature 023), which is scoped to per-request auth lookups, not business writes.
- **Async/Celery offload**: The invite email send (`invite_service.send_invite_email`) already uses Odoo's `mail.template` queuing (`force_send=False` per constitution's Transactional Email Pattern) — no additional async offload is needed for the new `real.estate.agent.create()` call, since a single-row INSERT with an already-indexed uniqueness check is sub-millisecond and must remain synchronous/transactional anyway (FR2.2 requires it to participate in the same rollback boundary as the `res.users` creation — moving it to Celery would break that atomicity guarantee). No new queue is introduced.
- Target: `POST /api/v1/users/invite` p95 response time remains `< 300ms` (unchanged budget from Feature 009's baseline for this endpoint; the added `real.estate.agent` INSERT + one indexed uniqueness lookup is not expected to move this budget).

**NFR3: Quality** (per ADR-022)
- Code must pass: black, isort, flake8 (`18.0/lint.sh`).
- Pylint score ≥ 8.0/10.
- 100% test coverage on the new/modified validations (`AGENT_INVITE_EXTRA_SCHEMA`, the `profile_type == 'agent'` branch, deprecation headers).

**NFR4: Data Integrity** (per knowledge_base/09-database-best-practices.md)
- No schema change; existing 3NF design (`profile` ↔ `agent` ↔ `res.users`, all linked via FK, not duplicated columns) is preserved and, if anything, improved (this feature removes a previously-possible inconsistent state: profile+user without agent).
- Soft delete (ADR-015) unaffected — no new delete paths introduced.
- Atomicity: FR2.2 is the core integrity guarantee of this feature (no partial user-without-agent state for `agent`-type invites going forward).

**NFR5: Frontend Compatibility**
- Not applicable — both endpoints are API-only, consumed exclusively via the headless frontend (per the project's Access Model: only the `admin` Odoo user touches the Odoo UI; Owner/Manager/Director invite agents through the headless frontend calling these REST endpoints). No Odoo views/menus are introduced or modified. No Cypress tests required for this feature.

---

## Technical Constraints

### Must Follow (from ADRs & Knowledge Base)

| Source | Requirement | Applied To |
|--------|-------------|------------|
| ADR-004 | `thedevkitchen_` prefix for NEW modules only — `quicksol_estate` and `real.estate.agent` are the pre-existing, documented legacy exception (constitution §12 item 5); this feature does not rename them | Model names |
| ADR-005 | OpenAPI regeneration; `deprecated: true` marker | `thedevkitchen.api.endpoint` record for `POST /api/v1/agents` |
| ADR-008 | Company isolation; no company-spoofing via nested `agent` payload | Invite controller |
| ADR-009 | Headless auth model — both endpoints admin/manager/owner-driven via API only | Access Model |
| ADR-011 | Triple decorator on both endpoints (unchanged) | Controllers |
| ADR-015 | Soft delete — not touched by this feature | N/A |
| ADR-016 | Postman collection update (deprecated folder/label) | `docs/postman/` |
| ADR-018 | Schema validation for new `agent` object | `SchemaValidator.AGENT_INVITE_EXTRA_SCHEMA` |
| ADR-019 | RBAC — ADR-024 invite matrix vs. `create_agent`'s narrower check; discrepancy documented (FR4.2), not silently resolved | Authorization |
| ADR-022 | Linting standards | All modified code |
| Constitution §"Atomic Dual Record Creation" | Pattern reused for user+agent atomicity | `invite_user` |
| Constitution §"Transactional Email Patterns" | `force_send=False`, non-blocking email failure | `send_invite_email` (unchanged) |

### Architecture Patterns

- **Controller Pattern**: Per `.github/instructions/controllers.instructions.md`
- **Testing Pattern**: Per `.github/instructions/test-strategy.instructions.md`
- **Reference Implementation**: Feature 009 (invite token lifecycle) + Feature 010 (unified profile, `create_agent`'s existing `profile_id` sync in `agent.py::create()`) are the two closest prior-art patterns this feature composes.

---

## Success Criteria

### Backend
- [ ] All 4 user stories implemented and tested
- [ ] 100% unit test coverage on new validations (`AGENT_INVITE_EXTRA_SCHEMA`, CRECI uniqueness path reused, atomicity rollback)
- [ ] E2E API tests for all critical flows (invite-creates-agent, legacy `create_agent` parity during transition, cross-company isolation)
- [ ] Multi-company isolation verified for the new `agent` object (no `company_id` spoofing possible)
- [ ] Code quality: Pylint ≥ 8.0, all linters passing (ADR-022)
- [ ] Security requirements validated (ADR-008, ADR-011)
- [ ] `POST /api/v1/agents` existing integration test suite passes unmodified during the deprecation window (regression guard for FR5.3)
- [ ] `POST /api/v1/agents` route, controller method, registry row, and superseded tests are deleted once User Story 4's removal preconditions are met (FR6)
- [ ] `POST /api/v1/agents` returns 404 post-removal and no longer appears in the generated OpenAPI spec

### Frontend
- Not applicable (API-only feature; see NFR5).

### Seeds
- [ ] Seed data file created with `seed_` prefix on all IDs/logins
- [ ] Seed covers owner/manager/agent roles across two companies (isolation testing)
- [ ] Seed includes one profile pending invite + one existing agent with a registered CRECI (conflict testing)
- [ ] Seed is idempotent
- [ ] API tests use seed records as initial state

### Documentation
- [ ] Constitution feedback analyzed and documented (see below)
- [ ] Swagger/OpenAPI regenerated (per ADR-005) — **mandatory, two passes** — see `.claude/skills/swagger-updater/SKILL.md`:
  - [ ] Pass 1 (deprecation window): new `agent` object documented on `POST /api/v1/users/invite`; `deprecated: true` + description added to `POST /api/v1/agents`
  - [ ] Pass 2 (post-removal): `POST /api/v1/agents` operation fully absent from the regenerated spec
- [ ] Postman collection updated (per ADR-016) — see `.claude/skills/postman-collection-manager/SKILL.md` — two passes mirroring Swagger (relabel during transition, delete after removal)
- [ ] Journey flowcharts created at `specs/025-agent-invite-unification/flowcharts.md` (one per user story, including the removal story)

---

## Constitution Feedback

### New Patterns Introduced

| Pattern | Description | Constitution Section | Priority |
|---------|-------------|---------------------|----------|
| Endpoint Deprecation Pattern | `Deprecation`/`Sunset` HTTP headers + OpenAPI `deprecated: true` + Postman folder relabeling, while keeping legacy behavior functionally intact | New subsection under "Security Requirements" or a new "API Lifecycle / Deprecation Patterns" section | Medium — this is the first documented endpoint deprecation in the project; future deprecations should follow the same template |
| Nested Optional Sub-Object for Type-Conditional Fields | When one profile type among several needs extra fields on a shared endpoint, add an optional nested object (`agent: {...}`) rather than forking the endpoint or flattening type-specific fields into the shared schema | "Architectural Patterns" | Low — reusable for future profile types (e.g., `tenant: {...}` fields if the portal-invite flow ever needs type-specific extensions) |

### New Entities/Relationships

None — no new entities introduced; this feature only closes a gap in existing `profile` ↔ `agent` ↔ `res.users` orchestration.

### Architectural Decisions

| Decision | Rationale | ADR Required? |
|----------|-----------|---------------|
| Keep `POST /api/v1/agents` behavior unchanged during the deprecation window (no internal delegation to invite flow), then remove it entirely (confirmed, Open Decision #1) | Deprecation window avoids a silent breaking change for consumers who intentionally create agent records without granting login access; full removal afterward avoids permanently maintaining two parallel, duplicated-validation code paths | No — captured in this spec as the confirmed plan (deprecate → remove); User Story 4/FR6 define the removal criteria and steps |
| Company ID for the new agent record is always derived from the profile, never accepted in the `agent` request object | Closes a company-spoofing vector; consistent with ADR-008's "creation/update operations validate company ownership" | No — this is an application of existing ADR-008, not a new decision |

### Constitution Update Recommendation

- **Update Required**: Yes (after implementation is complete and validated)
- **Suggested Version Bump**: MINOR (new "Endpoint Deprecation Pattern" documented as a reusable pattern, no principle redefinition)
- **Sections to Update**:
  - [ ] Architectural Patterns → add "Endpoint Deprecation Pattern"
  - [ ] Reference Implementations → add Feature 025 entry once implemented

---

## Assumptions & Dependencies

**Assumptions**:
- Non-`agent` profile types (owner, tenant, property_owner, etc.) are explicitly OUT OF SCOPE for this feature — their invite flow is unchanged. If the team later wants similar "create domain entity on invite" unification for `tenant`/`property_owner` profiles, that is a separate feature.
- `AGENT_CREATE_SCHEMA`'s existing required-field list (`name`, `cpf`, `company_id`, `email`) is fully satisfied by `PROFILE_CREATE_SCHEMA`'s required fields (`name`, `company_id`, `document`, `email`, `birthdate`, `profile_type_id`) — verified by direct comparison of both schemas in `quicksol_estate/controllers/utils/schema.py`. No new required fields need to be added to profile creation.
- The three Open Decisions above are resolved with their stated defaults unless the team overrides them before planning begins.

**Dependencies**:
- Existing modules: `quicksol_estate` (agent model/controller), `thedevkitchen_user_onboarding` (invite controller/service), `thedevkitchen_apigateway` (auth decorators, OpenAPI generation, API endpoint registry)
- External services: PostgreSQL 16 (transaction atomicity), Redis 7 (unaffected by this feature — no new cache usage)
- Authentication: OAuth2 + session via `thedevkitchen_apigateway` (unchanged)

---

## Implementation Phases

### Phase 1: Foundation
- Add `AGENT_INVITE_EXTRA_SCHEMA` to `SchemaValidator`
- Unit tests for schema validation (success + failure per field)

### Phase 2: API Layer
- Modify `invite_controller.py::invite_user` to branch on `profile_type == 'agent'`, validate the optional `agent` object, and create `real.estate.agent` atomically
- Add `agent_id` to response body + `agent` link
- Add `Deprecation`/`Sunset` headers to `agent_api.py::create_agent`
- Update `thedevkitchen.api.endpoint` registry record for `create_agent` (`deprecated=True`)

### Phase 3: Testing & Quality
- Unit tests (schema, atomicity/rollback, CRECI reuse)
- E2E API tests (happy path, conflict, cross-company isolation, legacy parity regression)
- Lint/quality gates (ADR-022)

### Phase 4: Documentation & Artifacts (deprecation window)
- OpenAPI regeneration (both endpoints: new `agent` object + `deprecated: true` on `create_agent`) — `swagger-updater` skill
- Postman collection update (relabel legacy request) — `postman-collection-manager` skill
- Journey flowcharts (`flowcharts.md`)
- Constitution update (Endpoint Deprecation Pattern)

### Phase 5: Removal of `POST /api/v1/agents` (after removal preconditions are met — User Story 4)
- Confirm removal preconditions (User Story 1 fully tested; deprecation window elapsed; API access log shows negligible/accepted traffic)
- Delete `create_agent` controller method + route registration (`agent_api.py`)
- Delete the `thedevkitchen.api.endpoint` registry row
- Delete superseded `create_agent` unit/integration tests
- Regenerate OpenAPI (confirm operation is absent) — `swagger-updater` skill
- Regenerate Postman collection (delete legacy request) — `postman-collection-manager` skill

---

## Artifacts to Generate

> **⚠️ MANDATORY**: Consult `.claude/skills/development-best-practices/SKILL.md` before implementing the model/controller changes above. Use `.claude/skills/swagger-updater/SKILL.md` and `.claude/skills/postman-collection-manager/SKILL.md` for the respective documentation artifacts — never hand-edit static OpenAPI/Postman files.

After specification approval, generate:

1. **Constitution Update** — new "Endpoint Deprecation Pattern" (see Constitution Feedback above); recommend running the `thedevkitchen-speckit-project-constitution` subagent once implementation is validated.
2. **Copilot Instructions Update** — if the deprecation header pattern is deemed reusable, add a short example to `.github/copilot-instructions.md`.
3. **Post-Development Tasks** (after implementation is complete and validated):
   - OpenAPI (`docs/openapi/`) via `swagger-updater` skill
   - Postman collection via `postman-collection-manager` skill
   - Journey flowcharts at `specs/025-agent-invite-unification/flowcharts.md`

---

## Validation Checklist

### Backend Validation
- [ ] All ADR requirements referenced and followed
- [ ] Knowledge base patterns applied (performance analysis complete, not generic — see NFR2)
- [ ] Multi-tenancy correctly specified (ADR-008) — company_id always derived, never accepted from the `agent` object
- [ ] Security properly defined (ADR-011, ADR-019) — authorization discrepancy between the two endpoints explicitly documented (FR4.2), not silently left inconsistent
- [ ] Test strategy complete — unit + E2E API (ADR-003)
- [ ] Database design normalized — no schema change, 3NF preserved
- [ ] Error handling specified (ADR-018) — 400/403/404/409/500 all mapped
- [ ] Code quality requirements defined (ADR-022)

### Frontend Validation
- Not applicable (API-only feature, no views/menus introduced).
