# -*- coding: utf-8 -*-
"""Feature 027 (FR6.4) -- the surviving agent HATEOAS links must point at
/api/v1/profiles/{profile_id}, not the removed /api/v1/agents/{id}.

These tests call the REAL controller code (SaleApiController._serialize_sale
and AgentApiController._agent_hateoas_link), not a re-implementation of the
link expression: reverting either fix makes them fail. Neither method touches
odoo.http.request, so both are callable straight from a TransactionCase with
real recordsets.
"""
from odoo.addons.quicksol_estate.controllers.agent_api import AgentApiController
from odoo.addons.quicksol_estate.controllers.sale_api import SaleApiController
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
        self.property = self._create_property()

    def _create_property(self):
        property_type = self.env["real.estate.property.type"].search([], limit=1)
        if not property_type:
            property_type = self.env["real.estate.property.type"].create(
                {"name": "Apartment 027-F8"}
            )
        location_type = self.env["real.estate.location.type"].search([], limit=1)
        if not location_type:
            location_type = self.env["real.estate.location.type"].create(
                {"name": "Urban 027-F8"}
            )
        country = self.env.ref("base.br")
        state = self.env["res.country.state"].search(
            [("country_id", "=", country.id)], limit=1
        )
        return self.env["real.estate.property"].create(
            {
                "name": "Property 027-F8",
                "property_purpose": "residential",
                "property_type_id": property_type.id,
                "location_type_id": location_type.id,
                "company_id": self.company.id,
                "origin_media": "website",
                "country_id": country.id,
                "state_id": state.id if state else False,
                "city": "São Paulo",
                "zip_code": "01310-100",
                "street": "Avenida Paulista",
                "street_number": "1000",
                "area": 100.0,
            }
        )

    def _create_sale(self, agent):
        return self.env["real.estate.sale"].create(
            {
                "property_id": self.property.id,
                "buyer_name": "Buyer 027-F8",
                "company_id": self.company.id,
                "agent_id": agent.id,
                "sale_date": "2026-01-15",
                "sale_price": 250000.00,
            }
        )

    # ----- sale_api.py::_serialize_sale (the real serializer) -----

    def test_serialize_sale_agent_link_points_to_profile(self):
        sale = self._create_sale(self.agent_with_profile)

        data = SaleApiController()._serialize_sale(sale)

        self.assertEqual(data["_links"]["agent"], f"/api/v1/profiles/{self.profile.id}")
        # Regression guard: the removed legacy route must not reappear.
        self.assertNotIn("/api/v1/agents/", data["_links"]["agent"])

    def test_serialize_sale_agent_link_omitted_when_no_profile_id(self):
        """Legacy agent created before Feature 010 (no profile_id) -- omit
        the link entirely rather than emit a URL that 404s."""
        sale = self._create_sale(self.agent_without_profile)

        data = SaleApiController()._serialize_sale(sale)

        self.assertNotIn("agent", data["_links"])
        # The scalar agent_id field is unrelated to the link and stays.
        self.assertEqual(data["agent_id"], self.agent_without_profile.id)

    def test_serialize_sale_without_agent_has_no_agent_link(self):
        sale = self._create_sale(self.agent_with_profile)
        sale.agent_id = False

        data = SaleApiController()._serialize_sale(sale)

        self.assertNotIn("agent", data["_links"])

    # ----- agent_api.py::_agent_hateoas_link (get_assignment's link) -----

    def test_assignment_agent_link_points_to_profile(self):
        link = AgentApiController._agent_hateoas_link(self.agent_with_profile)

        self.assertEqual(link["href"], f"/api/v1/profiles/{self.profile.id}")
        self.assertEqual(link["rel"], "agent")
        self.assertEqual(link["type"], "GET")

    def test_assignment_agent_link_omitted_when_no_profile_id(self):
        self.assertIsNone(
            AgentApiController._agent_hateoas_link(self.agent_without_profile)
        )

    def test_assignment_agent_link_omitted_when_no_agent(self):
        empty_agent = self.env["real.estate.agent"]

        self.assertIsNone(AgentApiController._agent_hateoas_link(empty_agent))
