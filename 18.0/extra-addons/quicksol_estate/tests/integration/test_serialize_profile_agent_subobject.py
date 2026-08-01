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
                "document": "27448487434",
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
            agent_data["_links"]["properties"],
            f"/api/v1/agents/{self.agent.id}/properties",
        )
        self.assertEqual(
            agent_data["_links"]["performance"],
            f"/api/v1/agents/{self.agent.id}/performance",
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
        must use it instead of issuing its own real.estate.agent.search().

        fake_agent is deliberately keyed to self.agent_profile.id -- the
        SAME profile being serialized, and the same profile_id a fresh
        search() would independently resolve to self.agent. If
        _serialize_profile ignored the passed-in dict and fell back to
        search([("profile_id", "=", profile.id)]), it would find
        self.agent (created first, real profile_id match) and this test
        would fail -- only reading agent_by_profile_id itself yields
        fake_agent.
        """
        fake_agent = self.env["real.estate.agent"].create(
            {
                "profile_id": self.agent_profile.id,
                "name": "Should Be Used Instead Of Search",
                "creci": "CRECI-SP 99999",
                "cpf": "41183520360",
                "email": "unused027@example.com",
                "company_id": self.company.id,
            }
        )
        agent_by_profile_id = {self.agent_profile.id: fake_agent}
        data = self.controller._serialize_profile(
            self.agent_profile, agent_by_profile_id=agent_by_profile_id
        )
        self.assertEqual(data["agent"]["id"], fake_agent.id)
        self.assertNotEqual(data["agent"]["id"], self.agent.id)

    def test_batched_lookup_missing_from_dict_yields_no_agent_subobject(self):
        """If a profile_id is absent from the prefetched dict (agent record
        doesn't exist), no agent sub-object is added -- no fallback search()
        is triggered even though one is available (that's the whole point
        of the batch fix)."""
        data = self.controller._serialize_profile(
            self.agent_profile, agent_by_profile_id={}
        )
        self.assertNotIn("agent", data)
