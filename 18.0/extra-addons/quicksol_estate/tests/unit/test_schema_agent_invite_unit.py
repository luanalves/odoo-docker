# -*- coding: utf-8 -*-
"""
Pure unittest.TestCase for Feature 026 — SchemaValidator.validate_agent_invite.

No Odoo environment/database required: SchemaValidator is a pure static
validator, imported directly via the same odoo.addons.__path__ extension
trick used by run_unit_tests.py.
"""
import unittest
from pathlib import Path

import odoo.addons

_addons_root = str(Path(__file__).parent.parent.parent.parent)  # /mnt/extra-addons
if _addons_root not in odoo.addons.__path__:
    odoo.addons.__path__.insert(0, _addons_root)

from odoo.addons.quicksol_estate.controllers.utils.schema import SchemaValidator  # noqa: E402


class TestSchemaAgentInvite(unittest.TestCase):
    def test_agent_exclusive_fields_payload_is_valid(self):
        """Apenas os campos EXCLUSIVOS de agente (sem equivalente no perfil) são aceitos"""
        payload = {
            "creci": "CRECI-SP 12345",
            "bank_name": "Banco do Brasil",
            "bank_account": "12345-6",
            "pix_key": "jane@example.com",
        }
        is_valid, errors = SchemaValidator.validate_agent_invite(payload)
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])

    def test_empty_payload_is_valid(self):
        """Nada é obrigatório — o registro de agente usa o perfil vinculado (FR1.4c)"""
        is_valid, errors = SchemaValidator.validate_agent_invite({})
        self.assertTrue(is_valid, errors)

    def test_identity_fields_are_not_validated_here(self):
        """name/cpf/email/phone/mobile/hire_date não fazem mais parte deste nó (já vêm
        do perfil, compartilhado por todo profile_type convidado por este endpoint) —
        mesmo valores mal formados nessas chaves não geram erro de schema aqui, porque
        o schema simplesmente não as reconhece/valida mais (o controller as ignora)."""
        is_valid, errors = SchemaValidator.validate_agent_invite(
            {
                "name": "Jo",  # curto demais para AGENT_CREATE_SCHEMA, mas irrelevante aqui
                "cpf": "123",  # inválido para AGENT_CREATE_SCHEMA, mas irrelevante aqui
                "email": "not-an-email",  # inválido, mas irrelevante aqui
                "hire_date": "2026-01-01",
            }
        )
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])

    def test_creci_length_constraint_rejects_short_creci(self):
        """agent.creci com menos de 4 chars -> inválido, mesma regra de create_agent"""
        is_valid, errors = SchemaValidator.validate_agent_invite({"creci": "ab"})
        self.assertFalse(is_valid)
        self.assertTrue(any("creci" in e for e in errors))

    def test_company_id_and_user_id_keys_do_not_cause_validation_failure(self):
        """FR1.4b: se o cliente enviar company_id/user_id, o schema NÃO rejeita
        (a barreira real é o filtro allowed_keys no controller) —
        aqui confirmamos apenas que a presença dessas chaves não gera 400."""
        is_valid, errors = SchemaValidator.validate_agent_invite(
            {"creci": "CRECI-SP 12345", "company_id": 999, "user_id": 5}
        )
        self.assertTrue(is_valid, errors)

    def test_creci_constraint_is_the_same_function_as_agent_create_schema(self):
        """Reaproveitamento por referência (não cópia) da regra de creci especificamente
        -- evita divergência silenciosa entre os dois schemas. name/cpf/email não são
        mais compartilhados aqui, já que este nó não os aceita."""
        self.assertIs(
            SchemaValidator.AGENT_INVITE_SCHEMA["constraints"]["creci"],
            SchemaValidator.AGENT_CREATE_SCHEMA["constraints"]["creci"],
        )
        self.assertNotIn("name", SchemaValidator.AGENT_INVITE_SCHEMA["constraints"])
        self.assertNotIn("cpf", SchemaValidator.AGENT_INVITE_SCHEMA["constraints"])
        self.assertNotIn("email", SchemaValidator.AGENT_INVITE_SCHEMA["constraints"])


if __name__ == "__main__":
    unittest.main()
