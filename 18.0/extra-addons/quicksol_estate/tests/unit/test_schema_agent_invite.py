# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.addons.quicksol_estate.controllers.utils.schema import SchemaValidator


class TestSchemaAgentInvite(TransactionCase):
    def test_full_field_parity_payload_is_valid(self):
        """Paridade total: todos os 10 campos de AGENT_CREATE_SCHEMA (menos company_id) são aceitos"""
        payload = {
            "name": "Jane Agent",
            "cpf": "12345678901",
            "email": "jane@example.com",
            "phone": "1130000000",
            "mobile": "11999998888",
            "creci": "CRECI-SP 12345",
            "hire_date": "2026-01-01",
            "bank_name": "Banco do Brasil",
            "bank_account": "12345-6",
            "pix_key": "jane@example.com",
        }
        is_valid, errors = SchemaValidator.validate_agent_invite(payload)
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])

    def test_empty_payload_is_valid(self):
        """Nada é obrigatório — todos os campos de identidade caem no fallback do perfil (FR1.4c)"""
        is_valid, errors = SchemaValidator.validate_agent_invite({})
        self.assertTrue(is_valid, errors)

    def test_name_length_constraint_rejects_short_name(self):
        """agent.name fora de 3-255 chars -> inválido, mesma regra de create_agent"""
        is_valid, errors = SchemaValidator.validate_agent_invite({"name": "Jo"})
        self.assertFalse(is_valid)
        self.assertTrue(any("name" in e for e in errors))

    def test_cpf_digit_count_constraint_rejects_invalid_cpf(self):
        """agent.cpf sem 11 dígitos -> inválido, mesma regra de create_agent"""
        is_valid, errors = SchemaValidator.validate_agent_invite({"cpf": "123"})
        self.assertFalse(is_valid)
        self.assertTrue(any("cpf" in e for e in errors))

    def test_email_format_constraint_rejects_invalid_email(self):
        """agent.email sem @/. -> inválido, mesma regra de create_agent"""
        is_valid, errors = SchemaValidator.validate_agent_invite({"email": "not-an-email"})
        self.assertFalse(is_valid)
        self.assertTrue(any("email" in e for e in errors))

    def test_creci_length_constraint_rejects_short_creci(self):
        """agent.creci com menos de 4 chars -> inválido, mesma regra de create_agent"""
        is_valid, errors = SchemaValidator.validate_agent_invite({"creci": "ab"})
        self.assertFalse(is_valid)
        self.assertTrue(any("creci" in e for e in errors))

    def test_company_id_and_user_id_keys_do_not_cause_validation_failure(self):
        """FR1.4b: se o cliente enviar company_id/user_id, o schema NÃO rejeita
        (a barreira real é o filtro allowed_keys no controller, Task 4) —
        aqui confirmamos apenas que a presença dessas chaves não gera 400."""
        is_valid, errors = SchemaValidator.validate_agent_invite(
            {"name": "Valid Name", "company_id": 999, "user_id": 5}
        )
        self.assertTrue(is_valid, errors)

    def test_constraints_are_the_same_object_as_agent_create_schema(self):
        """Reaproveitamento por referência (não cópia) — evita divergência silenciosa"""
        self.assertIs(
            SchemaValidator.AGENT_INVITE_SCHEMA["constraints"],
            SchemaValidator.AGENT_CREATE_SCHEMA["constraints"],
        )
