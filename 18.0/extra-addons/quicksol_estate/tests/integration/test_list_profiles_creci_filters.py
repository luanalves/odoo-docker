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
                "document": "27448487434",
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
