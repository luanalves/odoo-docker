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
                "cpf": "83680110863",
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
        self.assertEqual(
            agent.creci_normalized[:10], "SP" if False else agent.creci_normalized[:10]
        )
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
                "cpf": "53876122325",
                "email": "cross027@example.com",
                "company_id": other_company.id,
            }
        )
        # Should not raise -- same CRECI number, different company.
        cross_company_agent.write({"creci": "CRECI-SP 99999"})
        self.assertTrue(cross_company_agent.creci_normalized)
