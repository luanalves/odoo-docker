# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestAgentCreateFromProfileAndUser(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company_a = self.env["res.company"].create({"name": "Seed Company A 026"})
        self.company_b = self.env["res.company"].create({"name": "Seed Company B 026"})
        self.profile_type_agent = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "agent")], limit=1
        )
        self.profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "Profile Name",
                "company_id": self.company_a.id,
                "profile_type_id": self.profile_type_agent.id,
                "document": "11122233396",
                "email": "profile@example.com",
                "phone": "1130000000",
                "mobile": "11999998888",
                "birthdate": "1990-01-01",
            }
        )
        self.user_in_company_b = self.env["res.users"].create(
            {
                "name": "User In Company B",
                "login": "user_company_b_026@example.com",
                "company_id": self.company_b.id,
                "company_ids": [(6, 0, [self.company_b.id])],
            }
        )

    def test_omitted_identity_fields_fall_back_to_profile(self):
        """FR1.4c: name/cpf/email/phone/mobile ausentes -> usam o valor do profile"""
        agent = self.env["real.estate.agent"].create(
            {
                "profile_id": self.profile.id,
                "user_id": self.user_in_company_b.id,
            }
        )
        self.assertEqual(agent.name, "Profile Name")
        self.assertEqual(agent.cpf, "11122233396")  # document -> cpf
        self.assertEqual(agent.email, "profile@example.com")
        self.assertEqual(agent.phone, "1130000000")
        self.assertEqual(agent.mobile, "11999998888")

    def test_explicit_identity_fields_override_profile(self):
        """FR1.4: valores explícitos vencem o fallback do perfil"""
        agent = self.env["real.estate.agent"].create(
            {
                "profile_id": self.profile.id,
                "user_id": self.user_in_company_b.id,
                "name": "Explicit Override Name",
                "email": "override@example.com",
            }
        )
        self.assertEqual(agent.name, "Explicit Override Name")
        self.assertEqual(agent.email, "override@example.com")
        self.assertEqual(
            agent.cpf, "11122233396"
        )  # não sobrescrito -> ainda vem do profile

    def test_user_id_is_set_on_created_agent(self):
        """FR2.1b: o registro criado deve ter user_id, não só profile_id"""
        agent = self.env["real.estate.agent"].create(
            {
                "profile_id": self.profile.id,
                "user_id": self.user_in_company_b.id,
            }
        )
        self.assertEqual(agent.user_id.id, self.user_in_company_b.id)
        self.assertEqual(agent.profile_id.id, self.profile.id)

    def test_company_id_derives_from_profile_not_from_user(self):
        """FR1.4b/spec 'Achado': quando profile_id e user_id são passados juntos,
        company_id deve refletir profile.company_id (empresa A), NÃO
        user.company_ids[0] (empresa B) — confirma a ordem de precedência
        entre os dois blocos de sincronização em agent.py:436-470."""
        agent = self.env["real.estate.agent"].create(
            {
                "profile_id": self.profile.id,
                "user_id": self.user_in_company_b.id,
            }
        )
        self.assertEqual(
            agent.company_id.id,
            self.company_a.id,
            "company_id deveria vir do profile (empresa A), não do user (empresa B)",
        )
