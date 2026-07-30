# -*- coding: utf-8 -*-
"""Feature 027 FR5.3/FR5.4 -- the agent-sync half of PUT /api/v1/profiles/<id>.

These tests call the REAL controller code that update_profile uses
(ProfileApiController._sync_profile_update_to_agent and
._agent_conflict_status), not agent.write() directly: both helpers take
plain recordsets/dicts and never touch odoo.http.request, so reverting the
FR5.3 field list or the FR5.4 409 mapping makes them fail.

The request-level half (schema validation, cr.rollback() before the 409 is
returned, and the proof that the profile write is rolled back too) is
covered end-to-end by integration_tests/test_us27_s4_update_profile_agent_fields.sh
Step 4 (test_update_profile_creci_conflict_returns_409_with_rollback) --
TransactionCase forbids cr.rollback(), so that half cannot live here.
"""
from odoo.addons.quicksol_estate.controllers.profile_api import ProfileApiController
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestUpdateProfileAgentFieldsCascade(TransactionCase):
    def setUp(self):
        super().setUp()
        self.controller = ProfileApiController()
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
                "cpf": "83680110863",
                "email": "other027@example.com",
                "company_id": self.company.id,
                "creci": "CRECI-SP 99999",
            }
        )

    # ----- FR5.3: the agent sync loop -----

    def test_sync_writes_all_agent_exclusive_fields(self):
        """The six fields FR5.3 moved here from the removed
        PUT /api/v1/agents/<id> all reach the linked real.estate.agent."""
        body = {
            "creci": "CRECI-SP 11111",
            "bank_name": "Itau",
            "bank_account": "9999-0",
            "bank_account_type": "savings",
            "bank_branch": "0002",
            "pix_key": "pix027@example.com",
        }

        written = self.controller._sync_profile_update_to_agent(self.agent, body)

        self.assertEqual(set(written), set(body))
        self.assertEqual(self.agent.creci_normalized, "CRECI/SP 11111")
        self.assertEqual(self.agent.creci_state, "SP")
        self.assertEqual(self.agent.creci_number, "11111")
        self.assertEqual(self.agent.bank_name, "Itau")
        self.assertEqual(self.agent.bank_account, "9999-0")
        self.assertEqual(self.agent.bank_account_type, "savings")
        self.assertEqual(self.agent.bank_branch, "0002")
        self.assertEqual(self.agent.pix_key, "pix027@example.com")

    def test_sync_also_carries_the_shared_profile_fields(self):
        """name/email/phone/mobile/hire_date were already synced before
        Feature 027 -- the extraction must not have dropped them."""
        body = {
            "name": "Renamed Agent 027",
            "email": "renamed027@example.com",
            "phone": "1133334444",
            "mobile": "11988887777",
            "hire_date": "2026-02-01",
        }

        written = self.controller._sync_profile_update_to_agent(self.agent, body)

        self.assertEqual(set(written), set(body))
        self.assertEqual(self.agent.name, "Renamed Agent 027")
        self.assertEqual(self.agent.email, "renamed027@example.com")
        self.assertEqual(self.agent.phone, "1133334444")
        self.assertEqual(self.agent.mobile, "11988887777")

    def test_sync_ignores_fields_outside_the_allowlist(self):
        """Only AGENT_SYNC_FIELDS is mirrored -- an unrelated (or
        profile-only) key in the body must never reach the agent write."""
        original_cpf = self.agent.cpf

        written = self.controller._sync_profile_update_to_agent(
            self.agent,
            {"creci": "CRECI-SP 22222", "cpf": "11122233396", "occupation": "hacker"},
        )

        self.assertEqual(set(written), {"creci"})
        self.assertEqual(self.agent.cpf, original_cpf)

    def test_sync_with_no_syncable_fields_is_a_noop(self):
        written = self.controller._sync_profile_update_to_agent(
            self.agent, {"occupation": "irrelevant", "birthdate": "1991-01-01"}
        )

        self.assertEqual(written, {})

    def test_sync_propagates_duplicate_creci_validation_error(self):
        """FR5.4: the helper must NOT swallow the constraint -- update_profile
        needs the exception to roll back and map it to 409."""
        with self.assertRaises(ValidationError):
            self.controller._sync_profile_update_to_agent(
                self.agent, {"creci": "CRECI-SP 99999"}
            )

    def test_duplicate_creci_different_company_is_allowed(self):
        other_company = self.env["res.company"].create(
            {"name": "Seed Company 027-F4-B"}
        )
        cross_company_agent = self.env["real.estate.agent"].create(
            {
                "name": "Cross Company Agent",
                "cpf": "53876122325",
                "email": "cross027@example.com",
                "company_id": other_company.id,
            }
        )

        written = self.controller._sync_profile_update_to_agent(
            cross_company_agent, {"creci": "CRECI-SP 99999"}
        )

        self.assertEqual(set(written), {"creci"})
        self.assertEqual(cross_company_agent.creci_normalized, "CRECI/SP 99999")

    # ----- FR5.4: the 409-vs-400 mapping -----

    def test_duplicate_creci_error_maps_to_409(self):
        """The real ValidationError text raised by
        real.estate.agent._check_creci_format must select 409, not 400."""
        with self.assertRaises(ValidationError) as ctx:
            self.controller._sync_profile_update_to_agent(
                self.agent, {"creci": "CRECI-SP 99999"}
            )

        self.assertIn("já cadastrado", str(ctx.exception))
        self.assertEqual(
            ProfileApiController._agent_conflict_status(ctx.exception), 409
        )

    def test_malformed_creci_error_maps_to_400(self):
        """A format failure (not a uniqueness clash) is a client validation
        error, not a conflict."""
        with self.assertRaises(ValidationError) as ctx:
            self.controller._sync_profile_update_to_agent(self.agent, {"creci": "ab"})

        self.assertNotIn("já cadastrado", str(ctx.exception))
        self.assertEqual(
            ProfileApiController._agent_conflict_status(ctx.exception), 400
        )
