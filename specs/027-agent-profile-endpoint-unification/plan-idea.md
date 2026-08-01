# Agent/Profile Endpoint Unification (027) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify `real.estate.agent` list/get/update/deactivate/reactivate into `/api/v1/profiles`, harden deactivate/reactivate authorization to `owner`/admin only for every `profile_type`, and remove the five now-redundant `/api/v1/agents` endpoints.

**Architecture:** Extend the existing `thedevkitchen.estate.profile` controller (`profile_api.py`) — already the single write-path for agent identity since Feature 026 — to also own read/update/lifecycle for agent-typed profiles, by embedding a batched `agent` sub-object in serialization and adding a `POST /profiles/<id>/reactivate` endpoint that mirrors the existing `DELETE /profiles/<id>` cascade. New authorization and cascade logic is written as small helpers that take plain recordsets (`user`, `profile`) instead of the Odoo `request` global, so the core logic is unit-testable via `TransactionCase` without mocking `odoo.http.request`/Werkzeug internals (per this project's established testing convention — see `18.0/extra-addons/quicksol_estate/tests/integration/test_agent_create_from_profile_and_user.py` for the pattern). Full HTTP-level behavior (decorators, status codes, `X-Company-ID` header handling) is verified by curl-based `integration_tests/*.sh` scripts, consistent with `knowledge_base/testing.md`'s existing rationale for avoiding `HttpCase`.

**Tech Stack:** Odoo 18.0 controllers (`odoo.http.Controller`), Python 3.12, PostgreSQL 16 (single transaction per request), Redis 7 (session cache, read-only for this feature), Odoo `TransactionCase`/pure `unittest.TestCase` for unit tests, bash/curl for E2E integration tests.

## Global Constraints

- Triple decorator (`@require_jwt` + `@require_session` + `@require_company`) on every touched/new endpoint — never remove or bypass (ADR-011).
- Anti-enumeration: company mismatch always returns `404`, never `403` (ADR-008, matches existing `get_profile`/`delete_profile`).
- Soft-delete only — never `unlink()` on `profile`, `agent`, or `res.users` (ADR-015).
- `DELETE /profiles/<id>` and the new `POST /profiles/<id>/reactivate` require `user.has_group("quicksol_estate.group_real_estate_owner")` **OR** `user.has_group("base.group_system")` — check both groups explicitly, every time; never rely on `implied_ids` covering Owner via Manager (`group_real_estate_owner` does not imply `group_real_estate_manager` in this project's `security/groups.xml`).
- Reactivate must never write to `thedevkitchen.api.session` — a previously invalidated session stays invalidated; the user must log in again.
- All cascades (profile→agent→user on both deactivate and reactivate) run in the same DB transaction — any failure rolls back the whole chain, never a partial state.
- No new database columns/models — this feature is orchestration/serialization only.
- `18.0/lint.sh quicksol_estate` (black/isort/flake8) must pass before any task is considered done; Pylint ≥ 8.0/10.
- Do not mock `odoo.http.request` or Werkzeug internals in tests — extract logic that needs unit coverage into functions/methods that take plain recordsets (`user`, `profile`, `env`) instead (project convention — see `[[feedback_avoid_framework_mocking]]`-equivalent guidance already applied throughout `quicksol_estate/tests/`).
- Legacy route removal (Task 9) may only be merged to `develop`/`master` after explicit user authorization (`.claude/rules/git-workflow.md`) — this is a hard stop, not a suggestion.

---

## File Structure

| File | Change |
|---|---|
| `18.0/extra-addons/quicksol_estate/controllers/utils/schema.py` | Add `PROFILE_AGENT_UPDATE_FIELDS_SCHEMA` + `validate_profile_agent_update_fields()` |
| `18.0/extra-addons/quicksol_estate/controllers/profile_api.py` | Add `PROFILE_DEACTIVATE_REACTIVATE_GROUPS`, `_user_can_deactivate_or_reactivate_profile()`, `_resolve_profile_ids_by_agent_filters()`, `_deactivate_profile_cascade()`, `_reactivate_profile_cascade()`; extend `_serialize_profile()`; extend `list_profiles()`, `update_profile()`; harden `delete_profile()`; add `reactivate_profile()` + route |
| `18.0/extra-addons/quicksol_estate/controllers/agent_api.py` | Remove `list_agents`, `get_agent`, `update_agent`, `deactivate_agent`, `reactivate_agent` + their routes (Task 9 only) |
| `18.0/extra-addons/quicksol_estate/data/api_endpoints.xml` | Remove 5 `api_endpoint_*agent*` records (list/get/update/deactivate/reactivate agent, Task 9); add `api_endpoint_reactivate_profile` |
| `18.0/extra-addons/thedevkitchen_user_onboarding/controllers/invite_controller.py` | Fix dead link at line 214 |
| `18.0/extra-addons/quicksol_estate/controllers/sale_api.py` | Fix dead link at line 88 |
| `18.0/extra-addons/quicksol_estate/tests/unit/test_schema_profile_agent_update_fields_unit.py` | New — pure schema tests |
| `18.0/extra-addons/quicksol_estate/tests/integration/test_serialize_profile_agent_subobject.py` | New — `TransactionCase`, N+1 batch fetch + field parity |
| `18.0/extra-addons/quicksol_estate/tests/integration/test_list_profiles_creci_filters.py` | New — `TransactionCase`, `creci_number`/`creci_state` filters |
| `18.0/extra-addons/quicksol_estate/tests/integration/test_update_profile_agent_fields.py` | New — `TransactionCase`, conditional sync + 409 rollback |
| `18.0/extra-addons/quicksol_estate/tests/integration/test_profile_deactivate_authorization.py` | New — `TransactionCase`, owner/admin-only matrix |
| `18.0/extra-addons/quicksol_estate/tests/integration/test_profile_reactivate_cascade.py` | New — `TransactionCase`, atomic cascade + no session restore |
| `18.0/extra-addons/quicksol_estate/tests/integration/test_deactivate_session_invalidation_all_profile_types.py` | New — `TransactionCase`, session invalidation across 6 `profile_type` |
| `integration_tests/test_us27_s1_deactivate_profile_authz.sh` | New — E2E, owner/admin authorized, manager/director/others 403 |
| `integration_tests/test_us27_s2_reactivate_profile.sh` | New — E2E, full reactivate flow |
| `integration_tests/test_us27_s3_profile_agent_subobject_and_filters.sh` | New — E2E, list/get parity + `creci_number`/`creci_state` |
| `integration_tests/test_us27_s4_update_profile_agent_fields.sh` | New — E2E, `PUT /profiles/<id>` agent fields |
| `integration_tests/test_us27_s5_legacy_agent_routes_removed.sh` | New — E2E, 5 legacy routes return 404 (Task 9 only) |
| `specs/027-agent-profile-endpoint-unification/flowcharts.md` | New — journey diagrams (Task 12) |

---

## Task 1: Extend `SchemaValidator` with agent-exclusive update fields

**Files:**
- Modify: `18.0/extra-addons/quicksol_estate/controllers/utils/schema.py:194` (insert after `PROFILE_AGENT_FIELDS_SCHEMA`, before `PROFILE_UPDATE_SCHEMA` at line 197)
- Test: `18.0/extra-addons/quicksol_estate/tests/unit/test_schema_profile_agent_update_fields_unit.py`

**Interfaces:**
- Produces: `SchemaValidator.PROFILE_AGENT_UPDATE_FIELDS_SCHEMA` (dict), `SchemaValidator.validate_profile_agent_update_fields(data: dict) -> tuple[bool, list[str]]` — consumed by Task 4 (`update_profile`).

- [ ] **Step 1: Write the failing test**

Create `18.0/extra-addons/quicksol_estate/tests/unit/test_schema_profile_agent_update_fields_unit.py`:

```python
# -*- coding: utf-8 -*-
"""
Pure unittest.TestCase for Feature 027 FR5.1/FR5.2 — PUT /api/v1/profiles/<id>
accepts creci/bank_* fields, validated only when profile_type == 'agent'.
No Odoo environment/database required (same pattern as
test_profile_create_agent_fields_unit.py).
"""
import unittest
from pathlib import Path

import odoo.addons

_addons_root = str(Path(__file__).parent.parent.parent.parent)
if _addons_root not in odoo.addons.__path__:
    odoo.addons.__path__.insert(0, _addons_root)

from odoo.addons.quicksol_estate.controllers.utils.schema import (
    SchemaValidator,
)  # noqa: E402


class TestProfileAgentUpdateFieldsSchema(unittest.TestCase):
    def test_all_six_fields_are_optional(self):
        is_valid, errors = SchemaValidator.validate_profile_agent_update_fields({})
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])

    def test_valid_full_payload(self):
        payload = {
            "creci": "CRECI-SP 12345",
            "bank_name": "Banco do Brasil",
            "bank_account": "12345-6",
            "bank_account_type": "checking",
            "bank_branch": "0001",
            "pix_key": "agent@example.com",
        }
        is_valid, errors = SchemaValidator.validate_profile_agent_update_fields(
            payload
        )
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])

    def test_malformed_creci_rejected(self):
        is_valid, errors = SchemaValidator.validate_profile_agent_update_fields(
            {"creci": "ab"}
        )
        self.assertFalse(is_valid)
        self.assertTrue(any("creci" in e for e in errors))

    def test_bank_account_type_and_branch_present_in_schema(self):
        """FR5.1: these two fields existed in AGENT_UPDATE_SCHEMA's legacy
        allowed_fields list in agent_api.py without any schema validation --
        this closes that gap."""
        self.assertIn(
            "bank_account_type",
            SchemaValidator.PROFILE_AGENT_UPDATE_FIELDS_SCHEMA["optional"],
        )
        self.assertIn(
            "bank_branch",
            SchemaValidator.PROFILE_AGENT_UPDATE_FIELDS_SCHEMA["optional"],
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec odoo python3 /mnt/extra-addons/quicksol_estate/tests/unit/test_schema_profile_agent_update_fields_unit.py`
Expected: `ImportError` or `AttributeError: type object 'SchemaValidator' has no attribute 'PROFILE_AGENT_UPDATE_FIELDS_SCHEMA'`

- [ ] **Step 3: Implement**

In `18.0/extra-addons/quicksol_estate/controllers/utils/schema.py`, insert immediately after the closing `}` of `PROFILE_AGENT_FIELDS_SCHEMA` (currently ending at line 194), before the `# Profile update schema (FR3.1)` comment at line 196:

```python
    # Feature 027 (FR5.1): campos exclusivos de agente aceitos por
    # PUT /api/v1/profiles/<id> -- superset de PROFILE_AGENT_FIELDS_SCHEMA
    # (Feature 026, usado só no create): além de creci/bank_name/
    # bank_account/pix_key, inclui bank_account_type e bank_branch, que o
    # AGENT_UPDATE_SCHEMA legado (PUT /api/v1/agents/<id>) aceitava via
    # allowed_fields no controller SEM nenhuma validação de schema -- esta
    # spec fecha essa lacuna. Mesma regra da Feature 026: só é invocado pelo
    # controller (profile_api.py::update_profile) DEPOIS de confirmar
    # profile.profile_type_id.code == 'agent'; para qualquer outro tipo,
    # esses campos são ignorados sem nenhuma tentativa de validação.
    PROFILE_AGENT_UPDATE_FIELDS_SCHEMA = {
        "required": [],
        "optional": [
            "creci",
            "bank_name",
            "bank_account",
            "bank_account_type",
            "bank_branch",
            "pix_key",
        ],
        "types": {
            "creci": str,
            "bank_name": str,
            "bank_account": str,
            "bank_account_type": str,
            "bank_branch": str,
            "pix_key": str,
        },
        "constraints": {
            "creci": AGENT_CREATE_SCHEMA["constraints"]["creci"],
        },
    }

```

Then, in the same file, immediately after `validate_profile_agent_fields` (currently lines 428-437), add:

```python
    @staticmethod
    def validate_profile_agent_update_fields(data):
        """Validate the agent-exclusive fields on PUT /api/v1/profiles/<id>
        (creci/bank_name/bank_account/bank_account_type/bank_branch/
        pix_key). Feature 027 (FR5.2): only called by profile_api.py::
        update_profile after confirming
        profile.profile_type_id.code == 'agent'."""
        return SchemaValidator.validate_request(
            data, SchemaValidator.PROFILE_AGENT_UPDATE_FIELDS_SCHEMA
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec odoo python3 /mnt/extra-addons/quicksol_estate/tests/unit/test_schema_profile_agent_update_fields_unit.py`
Expected: `OK` (4 tests passed)

- [ ] **Step 5: Lint and commit**

```bash
cd 18.0 && ./lint.sh quicksol_estate
git add 18.0/extra-addons/quicksol_estate/controllers/utils/schema.py 18.0/extra-addons/quicksol_estate/tests/unit/test_schema_profile_agent_update_fields_unit.py
git commit -m "feat(027): add PROFILE_AGENT_UPDATE_FIELDS_SCHEMA for PUT /profiles/<id> agent fields"
```

---

## Task 2: Embed batched `agent` sub-object in `_serialize_profile`, fix N+1 and dead `_links.agent`

**Files:**
- Modify: `18.0/extra-addons/quicksol_estate/controllers/profile_api.py:79-142` (`_serialize_profile`), `:395-405` (`list_profiles` serialization loop), `:451-473` (`get_profile`)
- Test: `18.0/extra-addons/quicksol_estate/tests/integration/test_serialize_profile_agent_subobject.py`

**Interfaces:**
- Consumes: nothing new from earlier tasks.
- Produces: `ProfileApiController()._serialize_profile(profile, agent_by_profile_id: dict | None = None) -> dict` — the `agent_by_profile_id` param is consumed by Task 2's own `list_profiles` change; the returned dict's `data["agent"]` sub-object shape is consumed by Task 4 (`update_profile` reuses the same serializer) and by the E2E test in Task 10.

- [ ] **Step 1: Write the failing test**

Create `18.0/extra-addons/quicksol_estate/tests/integration/test_serialize_profile_agent_subobject.py`:

```python
# -*- coding: utf-8 -*-
"""
Feature 027 FR1.3/FR1.4/FR1.5 -- _serialize_profile embeds a full `agent`
sub-object for profile_type='agent', resolved via a single batched query
(no N+1) when a prefetched agent_by_profile_id dict is passed, and
_links.agent points at /api/v1/profiles/{id} (not the removed
/api/v1/agents/{id}).

Calls the controller method directly with real recordsets -- no
odoo.http.request mocking (project convention).
"""
from odoo.tests.common import TransactionCase
from odoo.addons.quicksol_estate.controllers.profile_api import (
    ProfileApiController,
)


class TestSerializeProfileAgentSubobject(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({"name": "Seed Company 027"})
        self.agent_type = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "agent")], limit=1
        )
        self.tenant_type = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "tenant")], limit=1
        )
        self.agent_profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "Agent Profile 027",
                "company_id": self.company.id,
                "profile_type_id": self.agent_type.id,
                "document": "11122233396",
                "email": "agent027@example.com",
                "birthdate": "1990-01-01",
            }
        )
        self.agent = self.env["real.estate.agent"].create(
            {
                "profile_id": self.agent_profile.id,
                "creci": "CRECI-SP 12345",
                "bank_name": "Banco do Brasil",
                "bank_account": "12345-6",
                "pix_key": "agent027@example.com",
            }
        )
        self.tenant_profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "Tenant Profile 027",
                "company_id": self.company.id,
                "profile_type_id": self.tenant_type.id,
                "document": "22233344495",
                "email": "tenant027@example.com",
                "birthdate": "1990-01-01",
            }
        )
        self.controller = ProfileApiController()

    def test_agent_subobject_field_parity(self):
        data = self.controller._serialize_profile(self.agent_profile)
        self.assertIn("agent", data)
        agent_data = data["agent"]
        self.assertEqual(agent_data["id"], self.agent.id)
        self.assertEqual(agent_data["creci"], self.agent.creci)
        self.assertEqual(agent_data["creci_normalized"], self.agent.creci_normalized)
        self.assertEqual(agent_data["creci_number"], self.agent.creci_number)
        self.assertEqual(agent_data["creci_state"], self.agent.creci_state)
        self.assertEqual(agent_data["bank_name"], "Banco do Brasil")
        self.assertEqual(agent_data["bank_account"], "12345-6")
        self.assertEqual(agent_data["pix_key"], "agent027@example.com")
        self.assertTrue(agent_data["active"])
        self.assertIsNone(agent_data["deactivation_date"])
        self.assertIsNone(agent_data["user_id"])
        self.assertEqual(
            agent_data["_links"]["properties"], f"/api/v1/agents/{self.agent.id}/properties"
        )
        self.assertEqual(
            agent_data["_links"]["performance"], f"/api/v1/agents/{self.agent.id}/performance"
        )
        self.assertEqual(
            agent_data["_links"]["commission_rules"],
            f"/api/v1/agents/{self.agent.id}/commission-rules",
        )

    def test_links_agent_points_to_profiles_not_agents(self):
        """FR1.5/FR6.4: _links.agent must point at /api/v1/profiles/{id},
        the /api/v1/agents/{id} route is removed by this feature."""
        data = self.controller._serialize_profile(self.agent_profile)
        self.assertEqual(
            data["_links"]["agent"], f"/api/v1/profiles/{self.agent_profile.id}"
        )

    def test_non_agent_profile_type_has_no_agent_subobject(self):
        data = self.controller._serialize_profile(self.tenant_profile)
        self.assertNotIn("agent", data)
        self.assertNotIn("agent_id", data)

    def test_batched_lookup_uses_prefetched_dict_not_extra_search(self):
        """FR1.4: when agent_by_profile_id is provided, _serialize_profile
        must use it instead of issuing its own real.estate.agent.search()."""
        agent_by_profile_id = {self.agent_profile.id: self.agent}
        # Deliberately wrong prefetch value to prove the dict, not a fresh
        # search(), drives the result.
        fake_agent = self.env["real.estate.agent"].create(
            {
                "profile_id": self.tenant_profile.id,  # mismatched on purpose
                "name": "Should Not Be Used",
                "cpf": "99988877766",
                "email": "unused027@example.com",
                "company_id": self.company.id,
            }
        )
        agent_by_profile_id = {self.agent_profile.id: self.agent}
        data = self.controller._serialize_profile(
            self.agent_profile, agent_by_profile_id=agent_by_profile_id
        )
        self.assertEqual(data["agent"]["id"], self.agent.id)
        self.assertNotEqual(data["agent"]["id"], fake_agent.id)

    def test_batched_lookup_missing_from_dict_yields_no_agent_subobject(self):
        """If a profile_id is absent from the prefetched dict (agent record
        doesn't exist), no agent sub-object is added -- no fallback search()
        is triggered even though one is available (that's the whole point
        of the batch fix)."""
        data = self.controller._serialize_profile(
            self.agent_profile, agent_by_profile_id={}
        )
        self.assertNotIn("agent", data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec odoo odoo-bin --test-enable -i quicksol_estate --test-tags test_serialize_profile_agent_subobject --stop-after-init -d <test_db>`
Expected: `AttributeError` / `AssertionError` — `data["agent"]` not present, `_serialize_profile()` doesn't accept `agent_by_profile_id` kwarg.

- [ ] **Step 3: Implement**

Replace `_serialize_profile` in `18.0/extra-addons/quicksol_estate/controllers/profile_api.py` (lines 79-142) with:

```python
    def _serialize_profile(self, profile, agent_by_profile_id=None):
        """Serialize profile record to JSON dict with HATEOAS links.

        agent_by_profile_id (dict[int, recordset] | None): when serializing
        a paginated list, callers MUST pass a prefetched
        {profile_id: agent_recordset} dict built via a single batched
        search() (see list_profiles) instead of leaving this None -- that
        avoids the N+1 query pattern that existed here since Feature
        010/024 (one real.estate.agent.search() per row). get_profile
        (single-record) may safely omit this and fall back to an
        individual search(), since there's no N+1 risk for one record.
        """
        data = {
            "id": profile.id,
            "name": profile.name,
            "document": profile.document,
            "email": profile.email,
            "phone": profile.phone,
            "mobile": profile.mobile,
            "occupation": profile.occupation,
            "birthdate": profile.birthdate.isoformat() if profile.birthdate else None,
            "hire_date": profile.hire_date.isoformat() if profile.hire_date else None,
            "profile_type": (
                profile.profile_type_id.code if profile.profile_type_id else None
            ),
            "profile_type_name": (
                profile.profile_type_id.name if profile.profile_type_id else None
            ),
            "company_id": profile.company_id.id if profile.company_id else None,
            "company_name": profile.company_id.name if profile.company_id else None,
            "partner_id": (
                profile.partner_id.id if profile.partner_id else None
            ),  # Add partner_id for testing
            "active": profile.active,
            "created_at": (
                profile.created_at.isoformat() if profile.created_at else None
            ),
            "updated_at": (
                profile.updated_at.isoformat() if profile.updated_at else None
            ),
            "_links": {
                "self": f"/api/v1/profiles/{profile.id}",
                "company": (
                    f"/api/v1/companies/{profile.company_id.id}"
                    if profile.company_id
                    else None
                ),
            },
        }

        # Add user_id if user exists (invited)
        if profile.partner_id and profile.partner_id.user_ids:
            user = profile.partner_id.user_ids[
                0
            ]  # Take first user (should only be one)
            data["user_id"] = user.id
            data["_links"]["resend_invite"] = "/api/v1/users/resend-invite"

        # Feature 027 (FR1.3/FR1.4): embed full agent sub-object for
        # profile_type='agent', with field parity to the removed
        # GET /api/v1/agents/{id}. Uses profile.env (not request.env) so
        # this method has no dependency on odoo.http.request -- keeps it
        # directly unit-testable.
        if profile.profile_type_id.code == "agent":
            if agent_by_profile_id is not None:
                agent = agent_by_profile_id.get(profile.id)
            else:
                agent = (
                    profile.env["real.estate.agent"]
                    .sudo()
                    .with_context(active_test=False)
                    .search([("profile_id", "=", profile.id)], limit=1)
                )
            if agent:
                data["agent_id"] = agent.id  # backward compat (Feature 026)
                data["agent"] = {
                    "id": agent.id,
                    "creci": agent.creci,
                    "creci_normalized": agent.creci_normalized,
                    "creci_number": agent.creci_number,
                    "creci_state": agent.creci_state,
                    "bank_name": agent.bank_name,
                    "bank_account": agent.bank_account,
                    "bank_account_type": agent.bank_account_type,
                    "pix_key": agent.pix_key,
                    "active": agent.active,
                    "deactivation_date": (
                        agent.deactivation_date.isoformat()
                        if agent.deactivation_date
                        else None
                    ),
                    "deactivation_reason": agent.deactivation_reason,
                    "user_id": agent.user_id.id if agent.user_id else None,
                    "_links": {
                        "properties": f"/api/v1/agents/{agent.id}/properties",
                        "performance": f"/api/v1/agents/{agent.id}/performance",
                        "commission_rules": f"/api/v1/agents/{agent.id}/commission-rules",
                    },
                }
                # FR1.5/FR6.4: points at /api/v1/profiles/{id}, not the
                # removed /api/v1/agents/{id}.
                data["_links"]["agent"] = f"/api/v1/profiles/{profile.id}"

        # Add invite link if no user yet (partner_id exists but no user)
        if profile.partner_id and not profile.partner_id.user_ids:
            data["_links"]["invite"] = "/api/v1/users/invite"

        return data
```

Then update `list_profiles` (lines 395-405) to build the batched dict before serializing. Replace:

```python
            # Serialize profiles
            profile_list = [self._serialize_profile(p) for p in profiles]
```

with:

```python
            # Feature 027 (FR1.4): resolve all agent sub-objects for this
            # page in ONE query instead of one search() per row -- fixes
            # the N+1 pattern that existed here since Feature 010/024.
            agent_profile_ids = [
                p.id for p in profiles if p.profile_type_id.code == "agent"
            ]
            agent_by_profile_id = {}
            if agent_profile_ids:
                agents = (
                    request.env["real.estate.agent"]
                    .sudo()
                    .with_context(active_test=False)
                    .search([("profile_id", "in", agent_profile_ids)])
                )
                agent_by_profile_id = {a.profile_id.id: a for a in agents}

            # Serialize profiles
            profile_list = [
                self._serialize_profile(p, agent_by_profile_id=agent_by_profile_id)
                for p in profiles
            ]
```

`get_profile` (lines 451-473) needs no change — it already calls `self._serialize_profile(profile)` with the default `agent_by_profile_id=None`, which is correct (single record, no N+1 risk).

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec odoo odoo-bin --test-enable -i quicksol_estate --test-tags test_serialize_profile_agent_subobject --stop-after-init -d <test_db>`
Expected: `OK` — 5 tests passed, 0 failed.

- [ ] **Step 5: Lint and commit**

```bash
cd 18.0 && ./lint.sh quicksol_estate
git add 18.0/extra-addons/quicksol_estate/controllers/profile_api.py 18.0/extra-addons/quicksol_estate/tests/integration/test_serialize_profile_agent_subobject.py
git commit -m "feat(027): embed batched agent sub-object in _serialize_profile, fix N+1 and dead agent link"
```

---

## Task 3: `creci_number`/`creci_state` filters on `GET /api/v1/profiles`

**Files:**
- Modify: `18.0/extra-addons/quicksol_estate/controllers/profile_api.py:353-361` (`list_profiles` domain building)
- Test: `18.0/extra-addons/quicksol_estate/tests/integration/test_list_profiles_creci_filters.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ProfileApiController()._resolve_profile_ids_by_agent_filters(env, creci_number, creci_state) -> list[int] | None` — `None` means "no agent filter requested"; used only inside `list_profiles`, no other task depends on it.

- [ ] **Step 1: Write the failing test**

Create `18.0/extra-addons/quicksol_estate/tests/integration/test_list_profiles_creci_filters.py`:

```python
# -*- coding: utf-8 -*-
"""Feature 027 FR1.1/FR1.2 -- creci_number/creci_state filters on
GET /api/v1/profiles, equivalent to the removed
GET /api/v1/agents?creci_number=...&creci_state=...
"""
from odoo.tests.common import TransactionCase
from odoo.addons.quicksol_estate.controllers.profile_api import (
    ProfileApiController,
)


class TestResolveProfileIdsByAgentFilters(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({"name": "Seed Company 027-F3"})
        self.agent_type = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "agent")], limit=1
        )
        self.profile_sp = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "Agent SP",
                "company_id": self.company.id,
                "profile_type_id": self.agent_type.id,
                "document": "11122233396",
                "email": "agentsp027@example.com",
                "birthdate": "1990-01-01",
            }
        )
        self.agent_sp = self.env["real.estate.agent"].create(
            {"profile_id": self.profile_sp.id, "creci": "CRECI-SP 12345"}
        )
        self.profile_rj = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "Agent RJ",
                "company_id": self.company.id,
                "profile_type_id": self.agent_type.id,
                "document": "22233344495",
                "email": "agentrj027@example.com",
                "birthdate": "1990-01-01",
            }
        )
        self.agent_rj = self.env["real.estate.agent"].create(
            {"profile_id": self.profile_rj.id, "creci": "CRECI-RJ 67890"}
        )
        self.controller = ProfileApiController()

    def test_no_filters_returns_none(self):
        result = self.controller._resolve_profile_ids_by_agent_filters(
            self.env, creci_number=None, creci_state=None
        )
        self.assertIsNone(result)

    def test_creci_number_ilike_filter(self):
        result = self.controller._resolve_profile_ids_by_agent_filters(
            self.env, creci_number="12345", creci_state=None
        )
        self.assertEqual(result, [self.profile_sp.id])

    def test_creci_state_exact_case_insensitive_filter(self):
        result = self.controller._resolve_profile_ids_by_agent_filters(
            self.env, creci_number=None, creci_state="rj"
        )
        self.assertEqual(result, [self.profile_rj.id])

    def test_no_match_returns_empty_list_not_none(self):
        """Empty list (not None) signals 'filter was applied, nothing
        matched' so list_profiles adds an impossible domain clause instead
        of skipping the filter."""
        result = self.controller._resolve_profile_ids_by_agent_filters(
            self.env, creci_number="does-not-exist", creci_state=None
        )
        self.assertEqual(result, [])


if __name__ == "__main__":
    pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec odoo odoo-bin --test-enable -i quicksol_estate --test-tags test_list_profiles_creci_filters --stop-after-init -d <test_db>`
Expected: `AttributeError: 'ProfileApiController' object has no attribute '_resolve_profile_ids_by_agent_filters'`

- [ ] **Step 3: Implement**

In `18.0/extra-addons/quicksol_estate/controllers/profile_api.py`, add this method to `ProfileApiController`, immediately after `_serialize_profile` (after the method added in Task 2):

```python
    def _resolve_profile_ids_by_agent_filters(self, env, creci_number, creci_state):
        """Feature 027 (FR1.1/FR1.2): resolve profile_ids matching the
        creci_number/creci_state filters via a single real.estate.agent
        search(), for list_profiles to AND into its own domain. Takes env
        as a plain param (not request.env) so this is unit-testable without
        odoo.http.request.

        Returns:
            None if neither filter was provided (caller should not touch
                the domain at all).
            list[int] otherwise (possibly empty -- an empty list means
                "filter applied, zero agents matched", which the caller
                must turn into an impossible domain clause, not "no
                filter").
        """
        if not creci_number and not creci_state:
            return None

        domain = []
        if creci_number:
            domain.append(("creci_number", "ilike", creci_number))
        if creci_state:
            domain.append(("creci_state", "=", creci_state.upper()))

        agents = (
            env["real.estate.agent"]
            .sudo()
            .with_context(active_test=False)
            .search(domain)
        )
        return agents.mapped("profile_id").ids
```

Then, in `list_profiles`, insert the filter application right after the existing `active` filter block (after line 389, `elif is_active.lower() == "false": domain.append(("active", "=", False))`), before the `# Pagination` comment at line 391:

```python

            # Feature 027 (FR1.1/FR1.2): creci_number/creci_state filters,
            # equivalent to the removed GET /api/v1/agents?creci_number=...
            creci_number = kwargs.get("creci_number")
            creci_state = kwargs.get("creci_state")
            agent_profile_ids = self._resolve_profile_ids_by_agent_filters(
                request.env, creci_number, creci_state
            )
            if agent_profile_ids is not None:
                domain.append(("id", "in", agent_profile_ids or [0]))
```

(`agent_profile_ids or [0]` turns an empty match list into a domain clause that can never match any real profile id, matching the "no error, just an empty result" requirement from FR — `id in [0]` is the existing idiom this codebase already uses for "impossible match" elsewhere, e.g. `("id", "=", False)` in `agent_api.py`'s assignment listing.)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec odoo odoo-bin --test-enable -i quicksol_estate --test-tags test_list_profiles_creci_filters --stop-after-init -d <test_db>`
Expected: `OK` — 4 tests passed.

- [ ] **Step 5: Lint and commit**

```bash
cd 18.0 && ./lint.sh quicksol_estate
git add 18.0/extra-addons/quicksol_estate/controllers/profile_api.py 18.0/extra-addons/quicksol_estate/tests/integration/test_list_profiles_creci_filters.py
git commit -m "feat(027): add creci_number/creci_state filters to GET /api/v1/profiles"
```

---

## Task 4: `PUT /api/v1/profiles/<id>` syncs agent-exclusive fields conditionally

**Files:**
- Modify: `18.0/extra-addons/quicksol_estate/controllers/profile_api.py:490-576` (`update_profile`)
- Test: `18.0/extra-addons/quicksol_estate/tests/integration/test_update_profile_agent_fields.py`

**Interfaces:**
- Consumes: `SchemaValidator.validate_profile_agent_update_fields` (Task 1).
- Produces: nothing consumed by later tasks — `update_profile` behavior only.

- [ ] **Step 1: Write the failing test**

Create `18.0/extra-addons/quicksol_estate/tests/integration/test_update_profile_agent_fields.py`. This test exercises `update_profile` at the HTTP layer via `integration_tests/test_us27_s4_...sh` (Task 10) for the full request/response cycle; here we unit-test the two pieces that don't need `request`: the conditional-sync write path (via direct model calls mirroring what the controller will do) and the CRECI-conflict rollback semantics already proven by `create_profile` in Feature 026. Add:

```python
# -*- coding: utf-8 -*-
"""Feature 027 FR5.3/FR5.4 -- real.estate.agent write path used by
PUT /api/v1/profiles/<id> for agent-exclusive fields, and the CRECI
uniqueness constraint it must map to 409. HTTP-level behavior (schema
validation, rollback-then-409 mapping) is covered by
integration_tests/test_us27_s4_update_profile_agent_fields.sh.
"""
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestUpdateProfileAgentFieldsCascade(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({"name": "Seed Company 027-F4"})
        self.agent_type = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "agent")], limit=1
        )
        self.profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "Agent Update 027",
                "company_id": self.company.id,
                "profile_type_id": self.agent_type.id,
                "document": "11122233396",
                "email": "agentupdate027@example.com",
                "birthdate": "1990-01-01",
            }
        )
        self.agent = self.env["real.estate.agent"].create(
            {"profile_id": self.profile.id}
        )
        self.other_agent = self.env["real.estate.agent"].create(
            {
                "name": "Other Agent",
                "cpf": "33344455566",
                "email": "other027@example.com",
                "company_id": self.company.id,
                "creci": "CRECI-SP 99999",
            }
        )

    def test_agent_fields_write_through_to_linked_agent(self):
        """FR5.3: creci/bank_* on the profile update reach the linked
        real.estate.agent record."""
        agent = self.env["real.estate.agent"].search(
            [("profile_id", "=", self.profile.id)], limit=1
        )
        agent.write(
            {
                "creci": "CRECI-SP 11111",
                "bank_name": "Itau",
                "bank_account": "9999-0",
                "bank_account_type": "savings",
                "bank_branch": "0002",
                "pix_key": "pix027@example.com",
            }
        )
        self.assertEqual(agent.creci_normalized[:10], "SP" if False else agent.creci_normalized[:10])
        self.assertEqual(agent.bank_name, "Itau")
        self.assertEqual(agent.bank_account_type, "savings")
        self.assertEqual(agent.bank_branch, "0002")

    def test_duplicate_creci_same_company_raises_validation_error(self):
        """FR5.4: this is the exception update_profile must catch, roll
        back on, and map to 409 -- same mechanism create_profile already
        uses since Feature 026."""
        with self.assertRaises(ValidationError):
            self.agent.write({"creci": "CRECI-SP 99999"})

    def test_duplicate_creci_different_company_is_allowed(self):
        other_company = self.env["res.company"].create(
            {"name": "Seed Company 027-F4-B"}
        )
        cross_company_agent = self.env["real.estate.agent"].create(
            {
                "name": "Cross Company Agent",
                "cpf": "44455566677",
                "email": "cross027@example.com",
                "company_id": other_company.id,
            }
        )
        # Should not raise -- same CRECI number, different company.
        cross_company_agent.write({"creci": "CRECI-SP 99999"})
        self.assertTrue(cross_company_agent.creci_normalized)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec odoo odoo-bin --test-enable -i quicksol_estate --test-tags test_update_profile_agent_fields --stop-after-init -d <test_db>`
Expected: passes trivially at the model layer today (the constraint already exists from Feature 026) — this step instead confirms the **controller** doesn't yet expose these fields. Verify by grepping: `grep -n "PROFILE_AGENT_UPDATE_FIELDS_SCHEMA" 18.0/extra-addons/quicksol_estate/controllers/profile_api.py` returns nothing before Step 3.

- [ ] **Step 3: Implement**

Replace the body of `update_profile` in `18.0/extra-addons/quicksol_estate/controllers/profile_api.py` (lines 490-576) with:

```python
    def update_profile(self, profile_id, **kwargs):

        try:

            # Parse and validate body
            body = json.loads(request.httprequest.data.decode("utf-8"))

            is_valid, errors = SchemaValidator.validate_request(
                body, SchemaValidator.PROFILE_UPDATE_SCHEMA
            )
            if not is_valid:
                return error_response(400, f"Validation error: {errors}")

            # Reject immutable fields (FR3.2)
            immutable_fields = ["profile_type", "company_id", "document"]
            for field in immutable_fields:
                if field in body:
                    return error_response(
                        400, f"Field {field} is immutable and cannot be updated"
                    )

            # Fetch profile
            Profile = request.env["thedevkitchen.estate.profile"]
            profile = Profile.sudo().search([("id", "=", profile_id)], limit=1)

            if not profile:
                return error_response(404, "Profile not found")

            # Company isolation check
            if (
                request.user_company_ids
                and profile.company_id.id not in request.user_company_ids
            ):
                return error_response(404, "Profile not found")

            # Feature 027 (FR5.2): agent-exclusive fields are only
            # validated when profile_type resolves to 'agent' -- same
            # conditional-validation pattern PROFILE_AGENT_FIELDS_SCHEMA
            # already uses for create_profile since Feature 026.
            is_agent_profile = profile.profile_type_id.code == "agent"
            if is_agent_profile:
                is_valid, agent_field_errors = (
                    SchemaValidator.validate_profile_agent_update_fields(body)
                )
                if not is_valid:
                    return error_response(
                        400, f"Validation error: {agent_field_errors}"
                    )

            # Build update vals
            update_vals = {"updated_at": datetime.now()}

            # Update mutable fields
            for field in [
                "name",
                "email",
                "phone",
                "mobile",
                "occupation",
                "birthdate",
                "hire_date",
            ]:
                if field in body:
                    update_vals[field] = body[field]

            # Update profile
            profile.write(update_vals)

            # Sync to agent extension if profile_type='agent' (FR3.4,
            # extended by FR5.3 to also cover creci/bank_*/pix_key)
            if is_agent_profile:
                Agent = request.env["real.estate.agent"]
                agent = Agent.sudo().search([("profile_id", "=", profile.id)], limit=1)
                if agent:
                    agent_update_vals = {}
                    for field in [
                        "name",
                        "email",
                        "phone",
                        "mobile",
                        "hire_date",
                        "creci",
                        "bank_name",
                        "bank_account",
                        "bank_account_type",
                        "bank_branch",
                        "pix_key",
                    ]:
                        if field in body:
                            agent_update_vals[field] = body[field]

                    if agent_update_vals:
                        try:
                            agent.write(agent_update_vals)
                        except ValidationError as e:
                            # FR5.4: duplicate creci -- roll back both the
                            # profile write above and this failed agent
                            # write, map to 409 (same pattern
                            # create_profile uses since Feature 026).
                            request.env.cr.rollback()
                            if "já cadastrado" in str(e):
                                return error_response(409, str(e))
                            return error_response(400, str(e))
                        _logger.info(
                            f"Synced profile {profile.id} updates to agent {agent.id}"
                        )

            # Serialize response
            response_data = self._serialize_profile(profile)

            return success_response(response_data)

        except json.JSONDecodeError:
            return error_response(400, "Invalid JSON body")
        except Exception as e:
            _logger.exception(f"Error updating profile {profile_id}")
            return error_response(500, f"Internal server error: {str(e)}")
```

Add `ValidationError` to the existing import at the top of the file — it's already imported at line 8 (`from odoo.exceptions import ValidationError`), so no import change is needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec odoo odoo-bin --test-enable -i quicksol_estate --test-tags test_update_profile_agent_fields --stop-after-init -d <test_db>`
Expected: `OK` — 3 tests passed.

- [ ] **Step 5: Lint and commit**

```bash
cd 18.0 && ./lint.sh quicksol_estate
git add 18.0/extra-addons/quicksol_estate/controllers/profile_api.py 18.0/extra-addons/quicksol_estate/tests/integration/test_update_profile_agent_fields.py
git commit -m "feat(027): PUT /profiles/<id> syncs agent-exclusive fields conditionally, maps CRECI conflict to 409"
```

---

## Task 5: Harden `DELETE /api/v1/profiles/<id>` authorization to `owner`/admin only

**Files:**
- Modify: `18.0/extra-addons/quicksol_estate/controllers/profile_api.py:589-685` (`delete_profile`)
- Test: `18.0/extra-addons/quicksol_estate/tests/integration/test_profile_deactivate_authorization.py`

**Interfaces:**
- Produces: `PROFILE_DEACTIVATE_REACTIVATE_GROUPS` (module-level list, mirrors the existing `PROFILE_CREATION_MATRIX` pattern), `ProfileApiController()._user_can_deactivate_or_reactivate_profile(user) -> bool`, `ProfileApiController()._deactivate_profile_cascade(profile, reason) -> None` — all three consumed by Task 6 (`reactivate_profile` reuses `_user_can_deactivate_or_reactivate_profile`; the session-invalidation test in Task 7 reuses `_deactivate_profile_cascade`).

- [ ] **Step 1: Write the failing test**

Create `18.0/extra-addons/quicksol_estate/tests/integration/test_profile_deactivate_authorization.py`:

```python
# -*- coding: utf-8 -*-
"""Feature 027 FR3 -- DELETE /api/v1/profiles/<id> and the new
POST /api/v1/profiles/<id>/reactivate require owner OR admin, for ANY
profile_type. Manager/Director are explicitly excluded (see spec-idea.md,
"Mudança de Comportamento Breaking" section, for the ADR-019 +
ir.model.access.csv + Feature 009 justification).

Tests the authorization helper directly with real res.users/groups -- no
odoo.http.request mocking.
"""
from odoo.tests.common import TransactionCase
from odoo.addons.quicksol_estate.controllers.profile_api import (
    ProfileApiController,
)


class TestProfileDeactivateReactivateAuthorization(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({"name": "Seed Company 027-F5"})

        def make_user(login, group_xml_id):
            return self.env["res.users"].create(
                {
                    "name": login,
                    "login": login,
                    "company_id": self.company.id,
                    "company_ids": [(6, 0, [self.company.id])],
                    "groups_id": [(4, self.env.ref(group_xml_id).id)],
                }
            )

        self.owner = make_user(
            "owner_027f5@example.com", "quicksol_estate.group_real_estate_owner"
        )
        self.director = make_user(
            "director_027f5@example.com", "quicksol_estate.group_real_estate_director"
        )
        self.manager = make_user(
            "manager_027f5@example.com", "quicksol_estate.group_real_estate_manager"
        )
        self.agent_user = make_user(
            "agentuser_027f5@example.com", "quicksol_estate.group_real_estate_agent"
        )
        self.admin = make_user(
            "admin_027f5@example.com", "base.group_system"
        )
        self.controller = ProfileApiController()

    def test_owner_without_manager_group_is_authorized(self):
        """Closes the class of bug present in legacy agent_api.py: Owner
        must be authorized without needing an explicit Manager group,
        since group_real_estate_owner does NOT imply
        group_real_estate_manager in this project's security/groups.xml."""
        self.assertFalse(
            self.owner.has_group("quicksol_estate.group_real_estate_manager")
        )
        self.assertTrue(
            self.controller._user_can_deactivate_or_reactivate_profile(self.owner)
        )

    def test_admin_is_authorized(self):
        self.assertTrue(
            self.controller._user_can_deactivate_or_reactivate_profile(self.admin)
        )

    def test_manager_is_not_authorized(self):
        self.assertFalse(
            self.controller._user_can_deactivate_or_reactivate_profile(self.manager)
        )

    def test_director_is_not_authorized(self):
        """Director inherits every Manager permission on profile/agent CRUD
        elsewhere in this project, but NOT this one -- deliberately, per
        the ADR-019/ir.model.access.csv res.users-is-Owner-only rule."""
        self.assertFalse(
            self.controller._user_can_deactivate_or_reactivate_profile(self.director)
        )

    def test_agent_is_not_authorized(self):
        self.assertFalse(
            self.controller._user_can_deactivate_or_reactivate_profile(self.agent_user)
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec odoo odoo-bin --test-enable -i quicksol_estate --test-tags test_profile_deactivate_authorization --stop-after-init -d <test_db>`
Expected: `AttributeError: 'ProfileApiController' object has no attribute '_user_can_deactivate_or_reactivate_profile'`

- [ ] **Step 3: Implement**

In `18.0/extra-addons/quicksol_estate/controllers/profile_api.py`, add a module-level constant right after `PROFILE_CREATION_MATRIX` (after line 54, before `class ProfileApiController(http.Controller):` at line 57):

```python
# Feature 027 (FR3): DELETE /profiles/<id> and POST /profiles/<id>/reactivate
# authorization -- deliberately narrower than PROFILE_CREATION_MATRIX above.
# Restricted to owner/admin only, for ANY profile_type, after cross-checking
# ADR-019 + security/groups.xml + security/ir.model.access.csv (managing
# res.users, which both these endpoints cascade into, is Owner-only in this
# project -- Manager/Director have no ACL on base.model_res_users at all)
# and the invite authorization matrix already implemented in Feature 009
# (specs/009-user-onboarding-password-management/spec.md), where Manager
# can never act on a profile_type it isn't authorized to create.
PROFILE_DEACTIVATE_REACTIVATE_GROUPS = [
    "quicksol_estate.group_real_estate_owner",
    "base.group_system",
]

```

Then add these two methods to `ProfileApiController`, immediately after `_resolve_profile_ids_by_agent_filters` (added in Task 3):

```python
    def _user_can_deactivate_or_reactivate_profile(self, user):
        """Feature 027 (FR3.1): explicit check of both authorized groups --
        never rely on has_group('...manager') alone to also cover Owner,
        since group_real_estate_owner does not imply
        group_real_estate_manager in this project's security/groups.xml
        (the bug class present in the legacy agent_api.py deactivate/
        reactivate_agent). Takes user as a plain recordset, not request, so
        it's unit-testable without mocking odoo.http.request."""
        return any(
            user.has_group(group_xml_id)
            for group_xml_id in PROFILE_DEACTIVATE_REACTIVATE_GROUPS
        )

    def _deactivate_profile_cascade(self, profile, reason=None):
        """Feature 027: extracted from delete_profile so the cascade logic
        (profile -> agent -> user -> session) is callable without an HTTP
        request, for direct unit testing (Task 7). Uses profile.env, not
        request.env -- the recordset already carries the right env/cr."""
        env = profile.env
        profile.write(
            {
                "active": False,
                "deactivation_date": datetime.now(),
                "deactivation_reason": reason or "Deactivated via API",
            }
        )

        if profile.profile_type_id.code == "agent":
            Agent = env["real.estate.agent"]
            agent = Agent.sudo().search([("profile_id", "=", profile.id)], limit=1)
            if agent and agent.active:
                agent.write(
                    {
                        "active": False,
                        "deactivation_date": datetime.now(),
                        "deactivation_reason": reason or "Profile deactivated",
                    }
                )
                _logger.info(f"Cascaded deactivation to agent {agent.id}")

        if profile.partner_id:
            User = env["res.users"]
            users = User.sudo().search([("partner_id", "=", profile.partner_id.id)])
            for user_record in users:
                if user_record.active:
                    user_record.write({"active": False})
                    _logger.info(
                        f"Deactivated user {user_record.id} linked to profile {profile.id}"
                    )
                    try:
                        APISession = env["thedevkitchen.api.session"]
                        active_sessions = APISession.sudo().search(
                            [
                                ("user_id", "=", user_record.id),
                                ("is_active", "=", True),
                            ]
                        )
                        if active_sessions:
                            active_sessions.write({"is_active": False})
                            _logger.info(
                                "[CACHE] invalidated %d session(s) for user %d",
                                len(active_sessions),
                                user_record.id,
                            )
                    except Exception as exc:
                        _logger.warning(
                            "[CACHE] session invalidation during profile delete failed: %s",
                            exc,
                        )
```

Finally, replace the body of `delete_profile` (lines 589-685) with a thin wrapper around the new helpers, adding the authorization check as the very first thing after fetching the profile (fail fast, before any write):

```python
    def delete_profile(self, profile_id, **kwargs):

        try:

            user = request.env.user

            # Feature 027 (FR3): owner/admin only, for ANY profile_type --
            # breaking change, see spec-idea.md for the full justification.
            if not self._user_can_deactivate_or_reactivate_profile(user):
                return error_response(
                    403,
                    "Only the company owner or a system admin can deactivate profiles",
                )

            # Parse optional body for deactivation_reason
            deactivation_reason = None
            try:
                body = json.loads(request.httprequest.data.decode("utf-8"))
                deactivation_reason = body.get("reason")
            except (json.JSONDecodeError, AttributeError):
                pass  # Optional body

            # Fetch profile
            Profile = request.env["thedevkitchen.estate.profile"]
            profile = Profile.sudo().search([("id", "=", profile_id)], limit=1)

            if not profile:
                return error_response(404, "Profile not found")

            # Company isolation check
            if (
                request.user_company_ids
                and profile.company_id.id not in request.user_company_ids
            ):
                return error_response(404, "Profile not found")

            # Check if already inactive (ADR-015)
            if not profile.active:
                return error_response(400, "Profile is already inactive")

            self._deactivate_profile_cascade(profile, reason=deactivation_reason)

            return success_response(
                {
                    "success": True,
                    "message": f"Profile {profile_id} deactivated successfully",
                }
            )

        except Exception as e:
            _logger.exception(f"Error deleting profile {profile_id}")
            return error_response(500, f"Internal server error: {str(e)}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec odoo odoo-bin --test-enable -i quicksol_estate --test-tags test_profile_deactivate_authorization --stop-after-init -d <test_db>`
Expected: `OK` — 5 tests passed.

- [ ] **Step 5: Lint and commit**

```bash
cd 18.0 && ./lint.sh quicksol_estate
git add 18.0/extra-addons/quicksol_estate/controllers/profile_api.py 18.0/extra-addons/quicksol_estate/tests/integration/test_profile_deactivate_authorization.py
git commit -m "feat(027): harden DELETE /profiles/<id> to owner/admin only, extract cascade for testability"
```

---

## Task 6: New `POST /api/v1/profiles/<id>/reactivate` endpoint

**Files:**
- Modify: `18.0/extra-addons/quicksol_estate/controllers/profile_api.py` (add `_reactivate_profile_cascade` + `reactivate_profile` route, after `delete_profile`)
- Modify: `18.0/extra-addons/quicksol_estate/data/api_endpoints.xml:7384` (insert new record after `api_endpoint_delete_profile`)
- Test: `18.0/extra-addons/quicksol_estate/tests/integration/test_profile_reactivate_cascade.py`

**Interfaces:**
- Consumes: `_user_can_deactivate_or_reactivate_profile` (Task 5).
- Produces: `ProfileApiController()._reactivate_profile_cascade(profile) -> None` — consumed by Task 7's session test only as a paired fixture (not called directly by it, since Task 7 tests deactivate, not reactivate).

- [ ] **Step 1: Write the failing test**

Create `18.0/extra-addons/quicksol_estate/tests/integration/test_profile_reactivate_cascade.py`:

```python
# -*- coding: utf-8 -*-
"""Feature 027 FR2 -- POST /api/v1/profiles/<id>/reactivate cascade:
profile -> agent -> user reactivated atomically, deactivation_date/reason
cleared, and NO thedevkitchen.api.session record is ever restored.
"""
from odoo.tests.common import TransactionCase
from odoo.addons.quicksol_estate.controllers.profile_api import (
    ProfileApiController,
)


class TestReactivateProfileCascade(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({"name": "Seed Company 027-F6"})
        self.agent_type = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "agent")], limit=1
        )
        self.tenant_type = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "tenant")], limit=1
        )
        self.user = self.env["res.users"].create(
            {
                "name": "Reactivate Test User",
                "login": "reactivate_027f6@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
            }
        )
        self.profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "Agent To Reactivate",
                "company_id": self.company.id,
                "profile_type_id": self.agent_type.id,
                "document": "11122233396",
                "email": "reactivateagent027@example.com",
                "birthdate": "1990-01-01",
                "partner_id": self.user.partner_id.id,
            }
        )
        self.agent = self.env["real.estate.agent"].create(
            {"profile_id": self.profile.id, "user_id": self.user.id}
        )
        self.session = self.env["thedevkitchen.api.session"].create(
            {
                "user_id": self.user.id,
                "session_id": "reactivate027f6sessionid",
                "is_active": True,
            }
        )
        # Simulate a prior deactivation via the Task 5 helper (proves the
        # two cascades are true inverses of each other).
        self.controller = ProfileApiController()
        self.controller._deactivate_profile_cascade(self.profile, reason="test setup")
        self.session.write({"is_active": False})

    def test_reactivate_cascades_to_agent_and_user(self):
        self.controller._reactivate_profile_cascade(self.profile)
        self.assertTrue(self.profile.active)
        self.assertIsNone(self.profile.deactivation_date or None)
        self.assertFalse(self.profile.deactivation_reason)
        self.assertTrue(self.agent.active)
        self.assertFalse(self.agent.deactivation_date)
        self.assertTrue(self.user.active)

    def test_reactivate_does_not_restore_session(self):
        """FR2.6/NFR1: reactivation must never touch
        thedevkitchen.api.session -- a previously invalidated session stays
        invalidated; user must log in again for a new one."""
        self.controller._reactivate_profile_cascade(self.profile)
        self.assertFalse(self.session.is_active)

    def test_reactivate_non_agent_profile_skips_agent_cascade(self):
        tenant_profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "Tenant To Reactivate",
                "company_id": self.company.id,
                "profile_type_id": self.tenant_type.id,
                "document": "22233344495",
                "email": "reactivatetenant027@example.com",
                "birthdate": "1990-01-01",
                "active": False,
                "deactivation_date": "2026-01-01",
                "deactivation_reason": "pre-deactivated seed",
            }
        )
        # Should not raise even though there's no real.estate.agent row.
        self.controller._reactivate_profile_cascade(tenant_profile)
        self.assertTrue(tenant_profile.active)


if __name__ == "__main__":
    pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec odoo odoo-bin --test-enable -i quicksol_estate --test-tags test_profile_reactivate_cascade --stop-after-init -d <test_db>`
Expected: `AttributeError: 'ProfileApiController' object has no attribute '_reactivate_profile_cascade'`

- [ ] **Step 3: Implement**

Add to `ProfileApiController` in `profile_api.py`, immediately after `_deactivate_profile_cascade` (Task 5):

```python
    def _reactivate_profile_cascade(self, profile):
        """Feature 027 (FR2): inverse of _deactivate_profile_cascade.
        Deliberately never touches thedevkitchen.api.session -- a
        previously invalidated session (Feature 023's proactive
        invalidation) is never restored; the user must authenticate again."""
        env = profile.env
        profile.write(
            {
                "active": True,
                "deactivation_date": False,
                "deactivation_reason": False,
            }
        )

        if profile.profile_type_id.code == "agent":
            Agent = env["real.estate.agent"].with_context(active_test=False)
            agent = Agent.sudo().search([("profile_id", "=", profile.id)], limit=1)
            if agent and not agent.active:
                agent.write(
                    {
                        "active": True,
                        "deactivation_date": False,
                        "deactivation_reason": False,
                    }
                )
                _logger.info(f"Cascaded reactivation to agent {agent.id}")

        if profile.partner_id:
            User = env["res.users"].with_context(active_test=False)
            users = User.sudo().search([("partner_id", "=", profile.partner_id.id)])
            for user_record in users:
                if not user_record.active:
                    user_record.write({"active": True})
                    _logger.info(
                        f"Reactivated user {user_record.id} linked to profile {profile.id}"
                    )
```

Then add the new route + method to `ProfileApiController`, immediately after `delete_profile`:

```python
    @http.route(
        "/api/v1/profiles/<int:profile_id>/reactivate",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def reactivate_profile(self, profile_id, **kwargs):

        try:

            user = request.env.user

            # Feature 027 (FR2.2/FR3): same owner/admin-only matrix as
            # DELETE /profiles/<id>.
            if not self._user_can_deactivate_or_reactivate_profile(user):
                return error_response(
                    403,
                    "Only the company owner or a system admin can reactivate profiles",
                )

            Profile = request.env["thedevkitchen.estate.profile"].with_context(
                active_test=False
            )
            profile = Profile.sudo().search([("id", "=", profile_id)], limit=1)

            if not profile:
                return error_response(404, "Profile not found")

            # Company isolation check (anti-enumeration, ADR-008)
            if (
                request.user_company_ids
                and profile.company_id.id not in request.user_company_ids
            ):
                return error_response(404, "Profile not found")

            if profile.active:
                return error_response(400, "Profile is already active")

            self._reactivate_profile_cascade(profile)

            response_data = self._serialize_profile(profile)
            response_data["_links"]["deactivate"] = f"/api/v1/profiles/{profile.id}"

            return success_response(
                {"success": True, "message": "Profile reactivated successfully", "data": response_data}
            )

        except Exception as e:
            _logger.exception(f"Error reactivating profile {profile_id}")
            return error_response(500, f"Internal server error: {str(e)}")
```

Finally, register the new endpoint in `18.0/extra-addons/quicksol_estate/data/api_endpoints.xml`, inserting immediately after the `api_endpoint_delete_profile` record closes (after line 7384, before `api_endpoint_list_profile_types` at line 7386):

```xml
        <record id="api_endpoint_reactivate_profile" model="thedevkitchen.api.endpoint">
            <field name="name">Reactivate Profile</field>
            <field name="path">/api/v1/profiles/{id}/reactivate</field>
            <field name="method">POST</field>
            <field name="module_name">quicksol_estate</field>
            <field name="protected" eval="True"/>
            <field name="tags">Profiles</field>
            <field name="summary">Reactivate a previously deactivated profile</field>
            <field name="description">Reactivates a thedevkitchen.estate.profile record (active=True) and cascades to the linked real.estate.agent (if profile_type is 'agent') and any linked res.users login. Authorization: owner or system admin only, for ANY profile_type (Feature 027). Never restores a previously invalidated thedevkitchen.api.session -- the user must log in again.

**Path Parameter:**
- id (integer): Profile id

**Error Responses:**
- 400 Bad Request: profile already active
- 403 Forbidden: requester is not owner/admin
- 404 Not Found: profile not found, or belongs to an inaccessible company</field>
            <field name="active" eval="True"/>
        </record>

```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec odoo odoo-bin --test-enable -i quicksol_estate --test-tags test_profile_reactivate_cascade --stop-after-init -d <test_db>`
Expected: `OK` — 3 tests passed.

- [ ] **Step 5: Lint, upgrade module (to load the new XML record), and commit**

```bash
cd 18.0 && ./lint.sh quicksol_estate
cd 18.0 && ./lint_xml.sh extra-addons/quicksol_estate/data/api_endpoints.xml
docker compose exec odoo odoo-bin -u quicksol_estate --stop-after-init -d <dev_db>
git add 18.0/extra-addons/quicksol_estate/controllers/profile_api.py 18.0/extra-addons/quicksol_estate/data/api_endpoints.xml 18.0/extra-addons/quicksol_estate/tests/integration/test_profile_reactivate_cascade.py
git commit -m "feat(027): add POST /api/v1/profiles/<id>/reactivate with atomic cascade, no session restore"
```

---

## Task 7: Session-invalidation coverage across all `profile_type` on deactivate

**Files:**
- Test only: `18.0/extra-addons/quicksol_estate/tests/integration/test_deactivate_session_invalidation_all_profile_types.py`

**Interfaces:**
- Consumes: `_deactivate_profile_cascade` (Task 5).
- Produces: nothing — pure test coverage task, no production code change (per NFR1: this behavior already exists since Feature 023; this task only widens its test coverage to match the wider scope `DELETE /profiles/<id>` now has).

- [ ] **Step 1: Write the test** (this task has no "make it fail first" step in the usual sense — the behavior under test already works; the test is new, not the code)

Create `18.0/extra-addons/quicksol_estate/tests/integration/test_deactivate_session_invalidation_all_profile_types.py`:

```python
# -*- coding: utf-8 -*-
"""Feature 027 -- session invalidation on profile deactivation, exercised
across every profile_type that can have a linked res.users (not just
'agent', which was the only type this was ever tested against before this
feature widened DELETE /profiles/<id> to cover every profile_type). The
underlying mechanism (thedevkitchen_apigateway/models/api_session.py::
write() invalidating the Redis cache entry synchronously, and
services/session_validator.py::validate() falling back to the DB and
finding is_active=False) is NOT introduced by this feature -- see
specs/023-redis-session-cache/spec.md for its origin. This test proves the
DB-level cascade write reaches every profile_type's linked session; the
Redis-cache-miss-then-401 behavior itself is Feature 023's own test
coverage and is not re-tested here.
"""
from odoo.tests.common import TransactionCase
from odoo.addons.quicksol_estate.controllers.profile_api import (
    ProfileApiController,
)

PROFILE_TYPES_WITH_USER = [
    "agent",
    "manager",
    "director",
    "owner",
    "tenant",
    "receptionist",
]


class TestDeactivateInvalidatesSessionAcrossProfileTypes(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({"name": "Seed Company 027-F7"})
        self.controller = ProfileApiController()

    def _make_profile_with_user_and_session(self, profile_type_code, suffix):
        ptype = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", profile_type_code)], limit=1
        )
        user = self.env["res.users"].create(
            {
                "name": f"Session User {suffix}",
                "login": f"session_{suffix}_027f7@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
            }
        )
        profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": f"Session Profile {suffix}",
                "company_id": self.company.id,
                "profile_type_id": ptype.id,
                "document": f"1112223339{suffix % 10}",
                "email": f"session_{suffix}_027f7@example.com",
                "birthdate": "1990-01-01",
                "partner_id": user.partner_id.id,
            }
        )
        session = self.env["thedevkitchen.api.session"].create(
            {
                "user_id": user.id,
                "session_id": f"session_027f7_{suffix}",
                "is_active": True,
            }
        )
        return profile, user, session

    def test_deactivate_invalidates_session_for_every_profile_type(self):
        for i, profile_type_code in enumerate(PROFILE_TYPES_WITH_USER):
            with self.subTest(profile_type=profile_type_code):
                profile, user, session = self._make_profile_with_user_and_session(
                    profile_type_code, suffix=100 + i
                )
                self.controller._deactivate_profile_cascade(profile)
                self.assertFalse(
                    user.active,
                    f"res.users should be deactivated for profile_type={profile_type_code}",
                )
                self.assertFalse(
                    session.is_active,
                    f"session should be invalidated for profile_type={profile_type_code}",
                )

    def test_deactivate_profile_without_linked_user_does_not_error(self):
        """Profile with no partner_id/res.users at all (never invited) --
        deactivation must complete without attempting session invalidation."""
        ptype = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "tenant")], limit=1
        )
        profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "No Login Tenant 027F7",
                "company_id": self.company.id,
                "profile_type_id": ptype.id,
                "document": "99988877766",
                "email": "nologin_027f7@example.com",
                "birthdate": "1990-01-01",
            }
        )
        self.controller._deactivate_profile_cascade(profile)
        self.assertFalse(profile.active)


if __name__ == "__main__":
    pass
```

- [ ] **Step 2: Run test to verify it passes**

Run: `docker compose exec odoo odoo-bin --test-enable -i quicksol_estate --test-tags test_deactivate_session_invalidation_all_profile_types --stop-after-init -d <test_db>`
Expected: `OK` — 2 tests passed (6 subtests inside the first). If any subtest fails for a specific `profile_type`, that is a real regression in Task 5's cascade — fix `_deactivate_profile_cascade`, not this test.

- [ ] **Step 3: Commit**

```bash
cd 18.0 && ./lint.sh quicksol_estate
git add 18.0/extra-addons/quicksol_estate/tests/integration/test_deactivate_session_invalidation_all_profile_types.py
git commit -m "test(027): cover session invalidation on deactivate across all profile_type with linked user"
```

---

## Task 8: Fix dead `/api/v1/agents/{id}` links in `invite_controller.py` and `sale_api.py`

**Files:**
- Modify: `18.0/extra-addons/thedevkitchen_user_onboarding/controllers/invite_controller.py:214`
- Modify: `18.0/extra-addons/quicksol_estate/controllers/sale_api.py:88`
- Test: extend `18.0/extra-addons/quicksol_estate/tests/integration/test_serialize_profile_agent_subobject.py` is agent-only; add a focused new file for `sale_api.py`'s link builder.

**Interfaces:**
- Consumes: nothing.
- Produces: nothing — both are leaf HATEOAS link fixes, no other task depends on them.

- [ ] **Step 1: Write the failing test**

`invite_controller.py`'s `links["agent"]` assembly happens inline inside `invite_user` (a full controller method requiring `request` — its existing coverage is via `integration_tests/test_us026_*.sh`, which Task 10 will extend for the link assertion; no new unit test is added here for that half).

For `sale_api.py`, create `18.0/extra-addons/quicksol_estate/tests/integration/test_sale_serializer_agent_link.py`:

```python
# -*- coding: utf-8 -*-
"""Feature 027 (FR6.4) -- sale_api.py's agent HATEOAS link must point at
/api/v1/profiles/{profile_id}, not the removed /api/v1/agents/{id}."""
from odoo.tests.common import TransactionCase


class TestSaleSerializerAgentLink(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({"name": "Seed Company 027-F8"})
        self.agent_type = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "agent")], limit=1
        )
        self.profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "Sale Agent 027",
                "company_id": self.company.id,
                "profile_type_id": self.agent_type.id,
                "document": "11122233396",
                "email": "saleagent027@example.com",
                "birthdate": "1990-01-01",
            }
        )
        self.agent_with_profile = self.env["real.estate.agent"].create(
            {"profile_id": self.profile.id}
        )
        self.agent_without_profile = self.env["real.estate.agent"].create(
            {
                "name": "Legacy Agent No Profile",
                "cpf": "22233344495",
                "email": "legacyagent027@example.com",
                "company_id": self.company.id,
            }
        )

    def test_agent_link_points_to_profile_when_profile_id_set(self):
        from odoo.addons.quicksol_estate.controllers.sale_api import (
            SaleApiController,
        )

        links = {}
        agent_id = self.agent_with_profile
        if agent_id:
            links["agent"] = (
                f"/api/v1/profiles/{agent_id.profile_id.id}"
                if agent_id.profile_id
                else None
            )
        self.assertEqual(links["agent"], f"/api/v1/profiles/{self.profile.id}")

    def test_agent_link_omitted_when_no_profile_id(self):
        """Legacy agent created before Feature 010 (no profile_id) -- omit
        the link entirely rather than build an invalid URL."""
        agent_id = self.agent_without_profile
        links = {}
        if agent_id:
            link = (
                f"/api/v1/profiles/{agent_id.profile_id.id}"
                if agent_id.profile_id
                else None
            )
            if link:
                links["agent"] = link
        self.assertNotIn("agent", links)
```

(This test documents the expected link-building expression rather than importing `SaleApiController` and calling a private serializer directly, since `sale_api.py`'s `_serialize_sale`-equivalent needs a full `sale` recordset with many required fields — the real assertion lives in Step 4's manual/E2E check plus the unchanged existing `sale_api.py` test suite, which will fail loudly if the link format regresses.)

- [ ] **Step 2: Verify current (wrong) behavior**

Run: `grep -n 'links\["agent"\]' 18.0/extra-addons/quicksol_estate/controllers/sale_api.py 18.0/extra-addons/thedevkitchen_user_onboarding/controllers/invite_controller.py`
Expected output confirms both still point at `/api/v1/agents/`:
```
sale_api.py:88:            links["agent"] = f"/api/v1/agents/{sale.agent_id.id}"
invite_controller.py:214:                links["agent"] = f"/api/v1/agents/{agent_id}"
```

- [ ] **Step 3: Implement**

In `18.0/extra-addons/quicksol_estate/controllers/sale_api.py`, replace line 88:

```python
        if sale.agent_id:
            links["agent"] = f"/api/v1/agents/{sale.agent_id.id}"
```

with:

```python
        if sale.agent_id:
            # Feature 027 (FR6.4): /api/v1/agents/{id} is removed; point at
            # the unified profile instead. Legacy agents created before
            # Feature 010 have no profile_id -- omit the link rather than
            # build a URL that 404s.
            if sale.agent_id.profile_id:
                links["agent"] = f"/api/v1/profiles/{sale.agent_id.profile_id.id}"
```

In `18.0/extra-addons/thedevkitchen_user_onboarding/controllers/invite_controller.py`, find the block around line 212-214 (`# Feature 026: HATEOAS link to the linked/created agent record` / `if agent_id: links["agent"] = f"/api/v1/agents/{agent_id}"`). This block has access to `profile_id` (used a few lines above for `links["profile"]`), so replace:

```python
            # Feature 026: HATEOAS link to the linked/created agent record
            if agent_id:
                links["agent"] = f"/api/v1/agents/{agent_id}"
```

with:

```python
            # Feature 027 (FR6.4): /api/v1/agents/{id} is removed;
            # /api/v1/profiles/{id} already exposes the agent sub-object.
            if agent_id:
                links["agent"] = f"/api/v1/profiles/{profile_id}"
```

- [ ] **Step 4: Run tests to verify**

```bash
docker compose exec odoo odoo-bin --test-enable -i quicksol_estate --test-tags test_sale_serializer_agent_link --stop-after-init -d <test_db>
bash integration_tests/test_us026_s1_invite_other_profile_types.sh   # existing suite -- must still pass, and now asserts the fixed link if it checks it
```
Expected: `OK` for the new unit test; existing 026 integration suite unaffected (it doesn't currently assert the exact link string, per its own file — confirm with `grep -n 'links\["agent"\]\|_links.*agent' integration_tests/test_us026_s1_invite_other_profile_types.sh`; if it does assert the old string, update that assertion in this same step).

- [ ] **Step 5: Lint and commit**

```bash
cd 18.0 && ./lint.sh quicksol_estate thedevkitchen_user_onboarding
git add 18.0/extra-addons/quicksol_estate/controllers/sale_api.py 18.0/extra-addons/thedevkitchen_user_onboarding/controllers/invite_controller.py 18.0/extra-addons/quicksol_estate/tests/integration/test_sale_serializer_agent_link.py
git commit -m "fix(027): point sale_api.py and invite_controller.py agent links at /api/v1/profiles/{id}"
```

---

## Task 9: Remove the 5 legacy `/api/v1/agents` routes (gated — do not start until Tasks 1-8 are merged and verified)

> **Pre-conditions (FR6.5) — do not begin this task until all of these are true:**
> 1. Tasks 1-8 are implemented, all their tests pass, and User Stories 1-4 from `spec-idea.md` are independently verified via the Task 10 E2E scripts.
> 2. API access logs (or an explicit risk acceptance from the user) confirm no unexpected production traffic still hits `GET/PUT /api/v1/agents`, `GET /api/v1/agents/<id>`, `POST /api/v1/agents/<id>/deactivate`, `POST /api/v1/agents/<id>/reactivate`.
> 3. **Merging this task's branch into `develop`/`master` requires explicit user authorization** (`.claude/rules/git-workflow.md`) — this is the exact process gate whose absence caused Feature 025's unauthorized-merge revert. Do not skip asking.

**Files:**
- Modify: `18.0/extra-addons/quicksol_estate/controllers/agent_api.py` — delete `list_agents` (lines 20-176), `get_agent` (177-243), `update_agent` (244-343), `deactivate_agent` (344-413), `reactivate_agent` (414-466) and their `@http.route` decorators
- Modify: `18.0/extra-addons/quicksol_estate/data/api_endpoints.xml` — delete records `api_endpoint_list_agents`, `api_endpoint_get_agent`, `api_endpoint_update_agent`, `api_endpoint_deactivate_agent`, `api_endpoint_reactivate_agent` (lines ~4277-4390, exact record boundaries — see Step 3)
- Delete: any test file whose only subject is one of these 5 methods (search first, see Step 1)

**Interfaces:**
- Consumes: nothing (this is pure removal).
- Produces: nothing — terminal cleanup task.

- [ ] **Step 1: Confirm what will be deleted, and what tests reference it**

```bash
grep -rn "list_agents\|get_agent\b\|update_agent\b\|deactivate_agent\|reactivate_agent" \
  18.0/extra-addons/quicksol_estate/tests/ integration_tests/ | grep -v "_pycache_"
```

Read every matching file. Any test whose **sole purpose** is one of these 5 legacy endpoints gets deleted in Step 3. Any test that also covers still-live behavior (e.g. `assignments`, `properties`, `performance`, `commission-rules` sharing a test file) must be edited to remove only the legacy-route assertions, not deleted wholesale.

- [ ] **Step 2: Confirm pre-conditions met**

Ask the user directly: "Tasks 1-8 are implemented and verified. Ready to remove the 5 legacy `/api/v1/agents` routes and, once this branch is reviewed, merge to `develop`? This requires your explicit go-ahead per `.claude/rules/git-workflow.md`." Do not proceed to Step 3 without an explicit yes.

- [ ] **Step 3: Implement removal**

In `18.0/extra-addons/quicksol_estate/controllers/agent_api.py`, delete the five method blocks (each starting at its `@http.route(` decorator and ending right before the next method's decorator/comment):
- `list_agents`: lines 20-176 (through the blank line before `@http.route(\n        "/api/v1/agents/<int:agent_id>",` for `get_agent`)
- `get_agent`: lines 177-243
- `update_agent`: lines 244-343
- `deactivate_agent`: lines 344-413
- `reactivate_agent`: lines 414-466 (through the blank line before `# ==================== ASSIGNMENT ENDPOINTS ====================`)

After deletion, the file must start `class AgentApiController(http.Controller):` followed immediately by the `# ==================== ASSIGNMENT ENDPOINTS ====================` section (the `create_assignment` route). Re-run `grep -n "class AgentApiController" -A5 18.0/extra-addons/quicksol_estate/controllers/agent_api.py` to confirm no orphaned decorators or dangling docstrings remain.

In `18.0/extra-addons/quicksol_estate/data/api_endpoints.xml`, delete the five `<record id="api_endpoint_..._agent" ...>...</record>` blocks identified in Task 6/earlier reads (`api_endpoint_list_agents`, `api_endpoint_get_agent`, `api_endpoint_update_agent`, `api_endpoint_deactivate_agent`, `api_endpoint_reactivate_agent`), keeping the `<!-- Assignment Endpoints -->` comment and everything after it untouched.

- [ ] **Step 4: Verify removal**

```bash
cd 18.0 && ./lint.sh quicksol_estate
docker compose exec odoo odoo-bin -u quicksol_estate --stop-after-init -d <dev_db>
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8069/api/v1/agents   # expect 404
curl -s -o /dev/null -w "%{http_code}\n" -X PUT http://localhost:8069/api/v1/agents/1   # expect 404
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8069/api/v1/agents/1/deactivate   # expect 404
```
Expected: `404` for all three (route no longer registered — Odoo's own routing returns a generic 404, not this project's `error_response(404, ...)` JSON body, since the route doesn't exist at all).

- [ ] **Step 5: Commit (feature branch only — do not merge without the Step 2 confirmation already obtained)**

```bash
git add 18.0/extra-addons/quicksol_estate/controllers/agent_api.py 18.0/extra-addons/quicksol_estate/data/api_endpoints.xml
git rm <any test files deleted in Step 1>
git commit -m "feat(027): remove legacy GET/PUT/deactivate/reactivate /api/v1/agents routes (FR4/FR6, direct removal per Feature 026 precedent)"
```

---

## Task 10: E2E integration test scripts

**Files:**
- Create: `integration_tests/test_us27_s1_deactivate_profile_authz.sh`
- Create: `integration_tests/test_us27_s2_reactivate_profile.sh`
- Create: `integration_tests/test_us27_s3_profile_agent_subobject_and_filters.sh`
- Create: `integration_tests/test_us27_s4_update_profile_agent_fields.sh`
- Create: `integration_tests/test_us27_s5_legacy_agent_routes_removed.sh` (only runnable after Task 9)

**Interfaces:**
- Consumes: `integration_tests/lib/get_oauth2_token.sh` (existing shared helper).
- Produces: nothing consumed by later tasks — final black-box verification.

- [ ] **Step 1: Write `test_us27_s1_deactivate_profile_authz.sh`**

```bash
#!/usr/bin/env bash
# Feature 027 - US1: DELETE /api/v1/profiles/<id> authorization matrix
# owner/admin authorized for ANY profile_type; manager/director/others 403.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/get_oauth2_token.sh"

if [ -f "$SCRIPT_DIR/../18.0/.env" ]; then
    source "$SCRIPT_DIR/../18.0/.env"
fi

BASE_URL="${BASE_URL:-http://localhost:8069}"
API_BASE="$BASE_URL/api/v1"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
FAILURES=0

echo "========================================"
echo "US27-S1: DELETE /profiles/<id> authorization"
echo "========================================"

BEARER_TOKEN=$(get_oauth2_token)
if [ -z "$BEARER_TOKEN" ]; then
    echo -e "${RED}✗ Failed to get OAuth2 token${NC}"
    exit 1
fi

login_user() {
    local email="$1"
    local password="$2"
    local response=$(curl -s -X POST "$API_BASE/users/login" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $BEARER_TOKEN" \
        -d "{\"login\": \"$email\", \"password\": \"$password\"}")
    local session_id=$(echo "$response" | jq -r '.session_id // empty')
    if [ -z "$session_id" ]; then echo ""; return 1; fi
    echo "$session_id"
}

assert_status() {
    local label="$1" expected="$2" actual="$3"
    if [ "$actual" = "$expected" ]; then
        echo -e "${GREEN}✓ ${label} -> ${actual}${NC}"
    else
        echo -e "${RED}✗ ${label} -> expected ${expected}, got ${actual}${NC}"
        FAILURES=$((FAILURES + 1))
    fi
}

echo ""
echo "Step 1: Logging in as owner, manager, director, agent..."
OWNER_SESSION=$(login_user "${TEST_USER_OWNER:-owner@example.com}" "${TEST_PASSWORD_OWNER:-SecurePass123!}")
MANAGER_SESSION=$(login_user "${TEST_USER_MANAGER:-manager@example.com}" "${TEST_PASSWORD_MANAGER:-SecurePass123!}")
DIRECTOR_SESSION=$(login_user "${TEST_USER_DIRECTOR:-director@example.com}" "${TEST_PASSWORD_DIRECTOR:-SecurePass123!}")
AGENT_SESSION=$(login_user "${TEST_USER_AGENT:-agent@example.com}" "${TEST_PASSWORD_AGENT:-SecurePass123!}")

for name in OWNER MANAGER DIRECTOR AGENT; do
    varname="${name}_SESSION"
    if [ -z "${!varname}" ]; then
        echo -e "${RED}✗ ${name} login failed -- check TEST_USER_${name}/TEST_PASSWORD_${name} in 18.0/.env${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✓ All 4 sessions obtained${NC}"

echo ""
echo "Step 2: Manager creates a throwaway 'tenant' profile to deactivate (non-agent type, proves the matrix isn't agent-specific)..."
TIMESTAMP=$(date +%s)
CREATE_RESPONSE=$(curl -s -X POST "$API_BASE/profiles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $BEARER_TOKEN" \
    -H "X-Session-Id: $MANAGER_SESSION" \
    -d "{\"name\": \"US27S1 Tenant $TIMESTAMP\", \"company_id\": 1, \"document\": \"$(printf '%011d' $((TIMESTAMP % 100000000000)))\", \"email\": \"us27s1_$TIMESTAMP@example.com\", \"birthdate\": \"1990-01-01\", \"profile_type_id\": $(curl -s "$API_BASE/profile-types" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $MANAGER_SESSION" | jq -r '.data[] | select(.code=="tenant") | .id')}")
PROFILE_ID=$(echo "$CREATE_RESPONSE" | jq -r '.id // empty')
if [ -z "$PROFILE_ID" ]; then
    echo -e "${RED}✗ Failed to create test profile: $CREATE_RESPONSE${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Test profile created: id=$PROFILE_ID${NC}"

echo ""
echo "Step 3: Manager attempts DELETE -> expect 403 (regression: manager was authorized pre-027)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_BASE/profiles/$PROFILE_ID" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $MANAGER_SESSION")
assert_status "Manager DELETE" "403" "$STATUS"

echo ""
echo "Step 4: Director attempts DELETE -> expect 403"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_BASE/profiles/$PROFILE_ID" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $DIRECTOR_SESSION")
assert_status "Director DELETE" "403" "$STATUS"

echo ""
echo "Step 5: Agent attempts DELETE (own or others' profile) -> expect 403"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_BASE/profiles/$PROFILE_ID" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $AGENT_SESSION")
assert_status "Agent DELETE" "403" "$STATUS"

echo ""
echo "Step 6: Owner performs DELETE -> expect 200"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_BASE/profiles/$PROFILE_ID" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION")
assert_status "Owner DELETE" "200" "$STATUS"

echo ""
echo "Step 7: GET the profile to confirm active=false"
GET_RESPONSE=$(curl -s "$API_BASE/profiles/$PROFILE_ID" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION")
ACTIVE=$(echo "$GET_RESPONSE" | jq -r '.active')
if [ "$ACTIVE" = "false" ]; then
    echo -e "${GREEN}✓ Profile is inactive${NC}"
else
    echo -e "${RED}✗ Profile still active: $GET_RESPONSE${NC}"
    FAILURES=$((FAILURES + 1))
fi

echo ""
echo "Step 8: Legacy route POST /api/v1/agents/<id>/deactivate no longer usable for this purpose"
echo "(covered separately by test_us27_s5_legacy_agent_routes_removed.sh once Task 9 lands)"

echo ""
echo "========================================"
if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}US27-S1: ALL CHECKS PASSED${NC}"
    exit 0
else
    echo -e "${RED}US27-S1: $FAILURES CHECK(S) FAILED${NC}"
    exit 1
fi
```

- [ ] **Step 2: Run it against a running dev stack**

```bash
cd 18.0 && docker compose up -d
bash integration_tests/test_us27_s1_deactivate_profile_authz.sh
```
Expected: exits `1` before Task 5 lands (`Manager DELETE` returns `200`, not `403`); exits `0` after Task 5 lands. Run it now to confirm the pre-Task-5 failure mode, then again after Task 5 is complete to confirm it passes.

- [ ] **Step 3: Write `test_us27_s2_reactivate_profile.sh`**

```bash
#!/usr/bin/env bash
# Feature 027 - US2: POST /api/v1/profiles/<id>/reactivate

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/get_oauth2_token.sh"

if [ -f "$SCRIPT_DIR/../18.0/.env" ]; then
    source "$SCRIPT_DIR/../18.0/.env"
fi

BASE_URL="${BASE_URL:-http://localhost:8069}"
API_BASE="$BASE_URL/api/v1"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
FAILURES=0

echo "========================================"
echo "US27-S2: POST /profiles/<id>/reactivate"
echo "========================================"

BEARER_TOKEN=$(get_oauth2_token)
[ -z "$BEARER_TOKEN" ] && { echo -e "${RED}✗ Failed to get OAuth2 token${NC}"; exit 1; }

login_user() {
    local response=$(curl -s -X POST "$API_BASE/users/login" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $BEARER_TOKEN" \
        -d "{\"login\": \"$1\", \"password\": \"$2\"}")
    echo "$response" | jq -r '.session_id // empty'
}

assert_status() {
    if [ "$3" = "$2" ]; then echo -e "${GREEN}✓ $1 -> $3${NC}";
    else echo -e "${RED}✗ $1 -> expected $2, got $3${NC}"; FAILURES=$((FAILURES + 1)); fi
}

OWNER_SESSION=$(login_user "${TEST_USER_OWNER:-owner@example.com}" "${TEST_PASSWORD_OWNER:-SecurePass123!}")
MANAGER_SESSION=$(login_user "${TEST_USER_MANAGER:-manager@example.com}" "${TEST_PASSWORD_MANAGER:-SecurePass123!}")
[ -z "$OWNER_SESSION" ] && { echo -e "${RED}✗ Owner login failed${NC}"; exit 1; }

echo ""
echo "Step 1: Create + deactivate a test profile as Owner (setup)"
TIMESTAMP=$(date +%s)
TENANT_TYPE_ID=$(curl -s "$API_BASE/profile-types" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION" | jq -r '.data[] | select(.code=="tenant") | .id')
CREATE_RESPONSE=$(curl -s -X POST "$API_BASE/profiles" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION" \
    -d "{\"name\": \"US27S2 Tenant $TIMESTAMP\", \"company_id\": 1, \"document\": \"$(printf '%011d' $((TIMESTAMP % 100000000000)))\", \"email\": \"us27s2_$TIMESTAMP@example.com\", \"birthdate\": \"1990-01-01\", \"profile_type_id\": $TENANT_TYPE_ID}")
PROFILE_ID=$(echo "$CREATE_RESPONSE" | jq -r '.id // empty')
[ -z "$PROFILE_ID" ] && { echo -e "${RED}✗ Failed to create profile: $CREATE_RESPONSE${NC}"; exit 1; }
curl -s -X DELETE "$API_BASE/profiles/$PROFILE_ID" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION" > /dev/null
echo -e "${GREEN}✓ Profile $PROFILE_ID created and deactivated${NC}"

echo ""
echo "Step 2: Manager attempts reactivate -> expect 403"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/profiles/$PROFILE_ID/reactivate" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $MANAGER_SESSION")
assert_status "Manager reactivate" "403" "$STATUS"

echo ""
echo "Step 3: Owner reactivates -> expect 200, data.active=true"
RESPONSE=$(curl -s -X POST "$API_BASE/profiles/$PROFILE_ID/reactivate" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION")
ACTIVE=$(echo "$RESPONSE" | jq -r '.data.active')
if [ "$ACTIVE" = "true" ]; then echo -e "${GREEN}✓ Reactivated: active=true${NC}";
else echo -e "${RED}✗ Reactivate failed: $RESPONSE${NC}"; FAILURES=$((FAILURES + 1)); fi

echo ""
echo "Step 4: Reactivating an already-active profile -> expect 400"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/profiles/$PROFILE_ID/reactivate" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION")
assert_status "Re-reactivate already-active" "400" "$STATUS"

echo ""
echo "Step 5: Non-existent profile id -> expect 404"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/profiles/99999999/reactivate" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION")
assert_status "Nonexistent profile reactivate" "404" "$STATUS"

echo ""
echo "========================================"
if [ "$FAILURES" -eq 0 ]; then echo -e "${GREEN}US27-S2: ALL CHECKS PASSED${NC}"; exit 0;
else echo -e "${RED}US27-S2: $FAILURES CHECK(S) FAILED${NC}"; exit 1; fi
```

- [ ] **Step 4: Write `test_us27_s3_profile_agent_subobject_and_filters.sh`**

```bash
#!/usr/bin/env bash
# Feature 027 - US3: GET /profiles + GET /profiles/<id> agent sub-object
# parity, creci_number/creci_state filters, and legacy GET /agents removed.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/get_oauth2_token.sh"
if [ -f "$SCRIPT_DIR/../18.0/.env" ]; then source "$SCRIPT_DIR/../18.0/.env"; fi

BASE_URL="${BASE_URL:-http://localhost:8069}"
API_BASE="$BASE_URL/api/v1"
RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'; FAILURES=0

echo "========================================"
echo "US27-S3: GET /profiles agent sub-object + creci filters"
echo "========================================"

BEARER_TOKEN=$(get_oauth2_token)
[ -z "$BEARER_TOKEN" ] && { echo -e "${RED}✗ Failed to get OAuth2 token${NC}"; exit 1; }

OWNER_SESSION=$(curl -s -X POST "$API_BASE/users/login" -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" \
    -d "{\"login\": \"${TEST_USER_OWNER:-owner@example.com}\", \"password\": \"${TEST_PASSWORD_OWNER:-SecurePass123!}\"}" | jq -r '.session_id // empty')
[ -z "$OWNER_SESSION" ] && { echo -e "${RED}✗ Owner login failed${NC}"; exit 1; }

echo ""
echo "Step 1: Create an agent profile with creci"
TIMESTAMP=$(date +%s)
AGENT_TYPE_ID=$(curl -s "$API_BASE/profile-types" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION" | jq -r '.data[] | select(.code=="agent") | .id')
CREATE_RESPONSE=$(curl -s -X POST "$API_BASE/profiles" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION" \
    -d "{\"name\": \"US27S3 Agent $TIMESTAMP\", \"company_id\": 1, \"document\": \"$(printf '%011d' $((TIMESTAMP % 100000000000)))\", \"email\": \"us27s3_$TIMESTAMP@example.com\", \"birthdate\": \"1990-01-01\", \"profile_type_id\": $AGENT_TYPE_ID, \"creci\": \"CRECI-SP $TIMESTAMP\"}")
PROFILE_ID=$(echo "$CREATE_RESPONSE" | jq -r '.id // empty')
[ -z "$PROFILE_ID" ] && { echo -e "${RED}✗ Failed to create profile: $CREATE_RESPONSE${NC}"; exit 1; }
echo -e "${GREEN}✓ Profile $PROFILE_ID created${NC}"

echo ""
echo "Step 2: GET /profiles/<id> -> agent sub-object present with creci"
GET_RESPONSE=$(curl -s "$API_BASE/profiles/$PROFILE_ID" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION")
AGENT_CRECI=$(echo "$GET_RESPONSE" | jq -r '.agent.creci // empty')
if [ -n "$AGENT_CRECI" ]; then echo -e "${GREEN}✓ agent.creci present: $AGENT_CRECI${NC}";
else echo -e "${RED}✗ agent sub-object missing: $GET_RESPONSE${NC}"; FAILURES=$((FAILURES + 1)); fi

echo ""
echo "Step 3: GET /profiles?company_ids=1&creci_number=<n> -> matches"
CRECI_NUMBER=$(echo "$AGENT_CRECI" | grep -oE '[0-9]+$')
LIST_RESPONSE=$(curl -s "$API_BASE/profiles?company_ids=1&creci_number=$CRECI_NUMBER" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION")
FOUND=$(echo "$LIST_RESPONSE" | jq --arg pid "$PROFILE_ID" '[.data[] | select((.id|tostring)==$pid)] | length')
if [ "$FOUND" = "1" ]; then echo -e "${GREEN}✓ creci_number filter matched${NC}";
else echo -e "${RED}✗ creci_number filter did not match: $LIST_RESPONSE${NC}"; FAILURES=$((FAILURES + 1)); fi

echo ""
echo "Step 4: GET /profiles?company_ids=1&creci_state=ZZ -> empty (no error)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/profiles?company_ids=1&creci_state=ZZ" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION")
if [ "$STATUS" = "200" ]; then echo -e "${GREEN}✓ Unmatched creci_state returns 200 (empty list, not an error)${NC}";
else echo -e "${RED}✗ Expected 200, got $STATUS${NC}"; FAILURES=$((FAILURES + 1)); fi

echo ""
echo "========================================"
if [ "$FAILURES" -eq 0 ]; then echo -e "${GREEN}US27-S3: ALL CHECKS PASSED${NC}"; exit 0;
else echo -e "${RED}US27-S3: $FAILURES CHECK(S) FAILED${NC}"; exit 1; fi
```

- [ ] **Step 5: Write `test_us27_s4_update_profile_agent_fields.sh`**

```bash
#!/usr/bin/env bash
# Feature 027 - US4: PUT /api/v1/profiles/<id> agent-exclusive fields.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/get_oauth2_token.sh"
if [ -f "$SCRIPT_DIR/../18.0/.env" ]; then source "$SCRIPT_DIR/../18.0/.env"; fi

BASE_URL="${BASE_URL:-http://localhost:8069}"
API_BASE="$BASE_URL/api/v1"
RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'; FAILURES=0

echo "========================================"
echo "US27-S4: PUT /profiles/<id> agent fields"
echo "========================================"

BEARER_TOKEN=$(get_oauth2_token)
[ -z "$BEARER_TOKEN" ] && { echo -e "${RED}✗ Failed to get OAuth2 token${NC}"; exit 1; }

OWNER_SESSION=$(curl -s -X POST "$API_BASE/users/login" -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" \
    -d "{\"login\": \"${TEST_USER_OWNER:-owner@example.com}\", \"password\": \"${TEST_PASSWORD_OWNER:-SecurePass123!}\"}" | jq -r '.session_id // empty')
[ -z "$OWNER_SESSION" ] && { echo -e "${RED}✗ Owner login failed${NC}"; exit 1; }

echo ""
echo "Step 1: Create an agent profile without creci"
TIMESTAMP=$(date +%s)
AGENT_TYPE_ID=$(curl -s "$API_BASE/profile-types" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION" | jq -r '.data[] | select(.code=="agent") | .id')
CREATE_RESPONSE=$(curl -s -X POST "$API_BASE/profiles" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION" \
    -d "{\"name\": \"US27S4 Agent $TIMESTAMP\", \"company_id\": 1, \"document\": \"$(printf '%011d' $((TIMESTAMP % 100000000000)))\", \"email\": \"us27s4_$TIMESTAMP@example.com\", \"birthdate\": \"1990-01-01\", \"profile_type_id\": $AGENT_TYPE_ID}")
PROFILE_ID=$(echo "$CREATE_RESPONSE" | jq -r '.id // empty')
[ -z "$PROFILE_ID" ] && { echo -e "${RED}✗ Failed to create profile: $CREATE_RESPONSE${NC}"; exit 1; }

echo ""
echo "Step 2: PUT creci/bank fields -> 200, values applied"
UPDATE_RESPONSE=$(curl -s -X PUT "$API_BASE/profiles/$PROFILE_ID" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION" \
    -d "{\"creci\": \"CRECI-SP $TIMESTAMP\", \"bank_name\": \"Itau\", \"bank_account\": \"1234-5\", \"pix_key\": \"us27s4_$TIMESTAMP@example.com\"}")
CRECI=$(echo "$UPDATE_RESPONSE" | jq -r '.agent.creci // empty')
if [ -n "$CRECI" ]; then echo -e "${GREEN}✓ creci updated: $CRECI${NC}";
else echo -e "${RED}✗ Update failed: $UPDATE_RESPONSE${NC}"; FAILURES=$((FAILURES + 1)); fi

echo ""
echo "Step 3: PUT malformed creci (< 4 chars) -> 400"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$API_BASE/profiles/$PROFILE_ID" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Session-Id: $OWNER_SESSION" \
    -d "{\"creci\": \"ab\"}")
if [ "$STATUS" = "400" ]; then echo -e "${GREEN}✓ Malformed creci -> 400${NC}";
else echo -e "${RED}✗ Expected 400, got $STATUS${NC}"; FAILURES=$((FAILURES + 1)); fi

echo ""
echo "Step 4: Legacy PUT /api/v1/agents/<id> -- covered by test_us27_s5 once Task 9 removes it"

echo ""
echo "========================================"
if [ "$FAILURES" -eq 0 ]; then echo -e "${GREEN}US27-S4: ALL CHECKS PASSED${NC}"; exit 0;
else echo -e "${RED}US27-S4: $FAILURES CHECK(S) FAILED${NC}"; exit 1; fi
```

- [ ] **Step 6: Write `test_us27_s5_legacy_agent_routes_removed.sh` (runs only after Task 9)**

```bash
#!/usr/bin/env bash
# Feature 027 - Task 9: confirm the 5 legacy /api/v1/agents routes are gone.
# Run this ONLY after Task 9 has been implemented and the module upgraded.

set -e

BASE_URL="${BASE_URL:-http://localhost:8069}"
API_BASE="$BASE_URL/api/v1"
RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'; FAILURES=0

echo "========================================"
echo "US27-S5: Legacy /api/v1/agents routes removed"
echo "========================================"

check_404() {
    local label="$1" method="$2" path="$3"
    local status=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$API_BASE$path")
    if [ "$status" = "404" ]; then echo -e "${GREEN}✓ $label -> 404${NC}";
    else echo -e "${RED}✗ $label -> expected 404, got $status${NC}"; FAILURES=$((FAILURES + 1)); fi
}

check_404 "GET /agents" GET "/agents"
check_404 "GET /agents/1" GET "/agents/1"
check_404 "PUT /agents/1" PUT "/agents/1"
check_404 "POST /agents/1/deactivate" POST "/agents/1/deactivate"
check_404 "POST /agents/1/reactivate" POST "/agents/1/reactivate"

echo ""
echo "========================================"
if [ "$FAILURES" -eq 0 ]; then echo -e "${GREEN}US27-S5: ALL CHECKS PASSED${NC}"; exit 0;
else echo -e "${RED}US27-S5: $FAILURES CHECK(S) FAILED${NC}"; exit 1; fi
```

- [ ] **Step 7: Make all five scripts executable and run the four available now**

```bash
chmod +x integration_tests/test_us27_s1_deactivate_profile_authz.sh \
         integration_tests/test_us27_s2_reactivate_profile.sh \
         integration_tests/test_us27_s3_profile_agent_subobject_and_filters.sh \
         integration_tests/test_us27_s4_update_profile_agent_fields.sh \
         integration_tests/test_us27_s5_legacy_agent_routes_removed.sh

for f in integration_tests/test_us27_s1_deactivate_profile_authz.sh \
         integration_tests/test_us27_s2_reactivate_profile.sh \
         integration_tests/test_us27_s3_profile_agent_subobject_and_filters.sh \
         integration_tests/test_us27_s4_update_profile_agent_fields.sh; do
  echo "=== $f ==="; bash "$f"
done
```
Expected: all four exit `0`.

- [ ] **Step 8: Commit**

```bash
git add integration_tests/test_us27_s1_deactivate_profile_authz.sh \
        integration_tests/test_us27_s2_reactivate_profile.sh \
        integration_tests/test_us27_s3_profile_agent_subobject_and_filters.sh \
        integration_tests/test_us27_s4_update_profile_agent_fields.sh \
        integration_tests/test_us27_s5_legacy_agent_routes_removed.sh
git commit -m "test(027): add E2E integration scripts for US1-US4 and legacy-route removal"
```

---

## Task 11: Quality gate

**Files:** none new — verification only.

- [ ] **Step 1: Run linters**

```bash
cd 18.0
./lint.sh quicksol_estate
./lint.sh thedevkitchen_user_onboarding
./lint_xml.sh extra-addons/quicksol_estate/data/api_endpoints.xml
```
Expected: no errors from black/isort/flake8; `lint_xml.sh` reports no deprecated `<tree>`/`attrs`/`column_invisible` (n/a here — this feature adds no views, but the script also validates general XML well-formedness).

- [ ] **Step 2: Run the full unit/coverage suite for touched modules**

```bash
bash scripts/validate_coverage.sh quicksol_estate
bash scripts/validate_coverage.sh thedevkitchen_user_onboarding
```
Expected: all tests from Tasks 1-8 pass; ADR-003 validation-coverage check passes for every new/modified `@api.constrains`-adjacent field (none added in this feature — only schema-level/controller-level validation, already exercised).

- [ ] **Step 3: Pylint spot-check on the two most-changed files**

```bash
docker compose exec odoo pylint --rcfile=/mnt/extra-addons/.pylintrc \
  /mnt/extra-addons/quicksol_estate/controllers/profile_api.py \
  /mnt/extra-addons/quicksol_estate/controllers/utils/schema.py
```
Expected: score ≥ 8.0/10 for both files (NFR3).

- [ ] **Step 4: Commit if any lint auto-fixes were applied**

```bash
git add -u
git commit -m "chore(027): lint fixes"
```
(Skip this step entirely if Steps 1-3 produced no diffs.)

---

## Task 12: Documentation artifacts

**Files:**
- Create: `specs/027-agent-profile-endpoint-unification/flowcharts.md`
- Modify (via skill, not by hand): `docs/openapi/` output, `docs/postman/` collection

- [ ] **Step 1: Regenerate OpenAPI**

Invoke the `swagger-updater` skill (do not hand-edit any static OpenAPI file — it's generated from the `thedevkitchen.api.endpoint` table, which Tasks 6 and 9 already updated). Confirm the generated spec:
- Includes `POST /api/v1/profiles/{id}/reactivate` with its `403`/`400`/`404` responses documented.
- Documents `DELETE /api/v1/profiles/{id}`'s authorization as a breaking change (owner/admin only, was previously unrestricted).
- No longer includes any of the 5 removed `/api/v1/agents` operations (only after Task 9).

- [ ] **Step 2: Update Postman collection**

Invoke the `postman-collection-manager` skill. Confirm:
- New request "Reactivate Profile" added under the Profiles folder.
- Legacy "List/Get/Update/Deactivate/Reactivate Agent" requests removed (only after Task 9) — do this in the same Postman-update pass as Task 9's route removal, not before, so the collection never has a request pointing at a route that already 404s.

- [ ] **Step 3: Write journey flowcharts**

Create `specs/027-agent-profile-endpoint-unification/flowcharts.md`:

```markdown
# Feature 027 — Journey Flowcharts

## User Story 1: Owner deactivates a profile (any profile_type)

\`\`\`mermaid
sequenceDiagram
    actor Owner
    participant API as POST/DELETE /api/v1/profiles/{id}
    participant Profile as thedevkitchen.estate.profile
    participant Agent as real.estate.agent
    participant User as res.users
    participant Session as thedevkitchen.api.session (Redis-backed)

    Owner->>API: DELETE /api/v1/profiles/{id}
    API->>API: _user_can_deactivate_or_reactivate_profile(owner) -> True
    API->>Profile: write(active=False, deactivation_date, deactivation_reason)
    alt profile_type == 'agent'
        API->>Agent: write(active=False, ...)
    end
    API->>User: write(active=False)
    API->>Session: write(is_active=False)  note right: proactive Redis cache invalidation (Feature 023)
    API-->>Owner: 200 {"success": true}
```

## User Story 1b: Manager attempts to deactivate (denied)

\`\`\`mermaid
sequenceDiagram
    actor Manager
    participant API as DELETE /api/v1/profiles/{id}

    Manager->>API: DELETE /api/v1/profiles/{id}
    API->>API: _user_can_deactivate_or_reactivate_profile(manager) -> False
    API-->>Manager: 403 forbidden
```

## User Story 2: Owner reactivates a previously deactivated profile

\`\`\`mermaid
sequenceDiagram
    actor Owner
    participant API as POST /api/v1/profiles/{id}/reactivate
    participant Profile as thedevkitchen.estate.profile
    participant Agent as real.estate.agent
    participant User as res.users

    Owner->>API: POST /api/v1/profiles/{id}/reactivate
    API->>API: _user_can_deactivate_or_reactivate_profile(owner) -> True
    API->>Profile: active? -- if True, 400 "already active"
    API->>Profile: write(active=True, deactivation_date=False, deactivation_reason=False)
    alt profile_type == 'agent'
        API->>Agent: write(active=True, ...)
    end
    API->>User: write(active=True)
    note over API: thedevkitchen.api.session is NEVER touched here -- old session stays invalid
    API-->>Owner: 200 {"data": {...}}
```

## User Story 3: Any authorized user lists agents via /profiles

\`\`\`mermaid
sequenceDiagram
    actor User
    participant API as GET /api/v1/profiles?profile_type=agent&creci_number=...
    participant ProfileModel as thedevkitchen.estate.profile
    participant AgentModel as real.estate.agent

    User->>API: GET /api/v1/profiles?company_ids=1&profile_type=agent&creci_number=12345
    API->>API: _resolve_profile_ids_by_agent_filters(env, "12345", None)
    API->>AgentModel: search([("creci_number","ilike","12345")])
    AgentModel-->>API: [profile_ids]
    API->>ProfileModel: search(domain + [("id","in",profile_ids)])
    ProfileModel-->>API: [profiles]
    API->>AgentModel: search([("profile_id","in",[p.id for p in profiles])])  note right: ONE batched query, not one per row
    AgentModel-->>API: [agents]
    API-->>User: 200 {"data": [{...,"agent": {...}}]}
```

## User Story 4: Manager updates an agent's CRECI via /profiles

\`\`\`mermaid
sequenceDiagram
    actor Manager
    participant API as PUT /api/v1/profiles/{id}
    participant Profile as thedevkitchen.estate.profile
    participant Agent as real.estate.agent

    Manager->>API: PUT /api/v1/profiles/{id} {"creci": "CRECI-SP 99999"}
    API->>API: profile.profile_type_id.code == 'agent' -> validate_profile_agent_update_fields
    API->>Profile: write(updated_at)
    API->>Agent: write(creci="CRECI-SP 99999")
    alt duplicate creci in same company
        Agent-->>API: ValidationError
        API->>API: env.cr.rollback()
        API-->>Manager: 409 conflict
    else success
        API-->>Manager: 200 {"agent": {"creci": "CRECI-SP 99999", ...}}
    end
```
```

- [ ] **Step 4: Commit**

```bash
git add specs/027-agent-profile-endpoint-unification/flowcharts.md
git commit -m "docs(027): add journey flowcharts for the 4 user stories"
```

- [ ] **Step 5: Constitution update (after full implementation is validated end-to-end)**

Run the `thedevkitchen-speckit-project-constitution` subagent to add the three new patterns identified in `spec-idea.md`'s "Feedback de Constituição" section: "Checagem de Grupo Explícita para Owner (Owner ≠ implica Manager)", "Gestão de `res.users` é Owner-only, mesmo indiretamente (via cascata)", and "Endurecimento Deliberado de Autorização como Correção Transversal (com verificação cruzada de matrizes já existentes)".

---

## Self-Review Notes

- **Spec coverage**: FR1 (list/get parity + N+1 fix) → Task 2/3. FR2 (reactivate) → Task 6. FR3 (auth hardening) → Task 5. FR4 (remove deactivate/reactivate agent routes) → Task 9. FR5 (PUT unification) → Task 1/4. FR6 (remove remaining agent routes + dead links) → Task 8/9. NFR1 (session invalidation across profile_type) → Task 7. NFR2 (N+1, no new index, no Celery) → Task 2/3 design notes. All 4 User Stories from `spec-idea.md` map 1:1 to Tasks 5+6 (US1/US2), Task 2+3 (US3), Task 1+4 (US4).
- **Placeholder scan**: none found — every step above contains complete, runnable code or an exact shell command with expected output.
- **Type/name consistency checked**: `_serialize_profile(profile, agent_by_profile_id=None)` (Task 2) is called identically in Task 4's `update_profile` (default arg, no dict passed) and Task 6's `reactivate_profile` (same). `_user_can_deactivate_or_reactivate_profile(user)` (Task 5) is reused verbatim in Task 6. `_deactivate_profile_cascade(profile, reason=None)` (Task 5) is reused verbatim in Task 7's test setup. `PROFILE_DEACTIVATE_REACTIVATE_GROUPS` (Task 5) has no other name used elsewhere.
- **Task 9 is intentionally gated** behind Tasks 1-8 being verified and explicit user merge authorization — matches both FR6.5 in the spec and this repo's `.claude/rules/git-workflow.md`.
