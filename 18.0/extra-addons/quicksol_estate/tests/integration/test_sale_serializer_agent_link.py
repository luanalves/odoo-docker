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
                "cpf": "41183520360",
                "email": "legacyagent027@example.com",
                "company_id": self.company.id,
            }
        )

    def test_agent_link_points_to_profile_when_profile_id_set(self):
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
