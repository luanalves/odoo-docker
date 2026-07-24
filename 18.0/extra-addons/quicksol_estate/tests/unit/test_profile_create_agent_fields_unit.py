# -*- coding: utf-8 -*-
"""
Pure unittest.TestCase for Feature 026 (corrigido, 2026-07-23, segunda
correção) — creci/bank_name/bank_account/pix_key foram movidos para um
schema SEPARADO (PROFILE_AGENT_FIELDS_SCHEMA / validate_profile_agent_fields),
já que PROFILE_CREATE_SCHEMA valida ANTES de profile_type_id ser resolvido
para seu code ('agent', 'tenant', etc.) -- deixar essas regras dentro do
schema genérico rejeitaria, por exemplo, um perfil 'tenant' só por causa de
um creci mal formatado, mesmo esse campo sendo irrelevante para esse
profile_type. profile_api.py::create_profile só invoca
validate_profile_agent_fields quando profile_type.code == "agent".

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

from odoo.addons.quicksol_estate.controllers.utils.schema import (
    SchemaValidator,
)  # noqa: E402


def _valid_profile_payload(**overrides):
    payload = {
        "name": "Jane Agent",
        "company_id": 5,
        "document": "12345678909",
        "email": "jane@example.com",
        "birthdate": "1990-01-01",
        "profile_type_id": 4,
    }
    payload.update(overrides)
    return payload


class TestProfileCreateSchemaHasNoAgentFields(unittest.TestCase):
    """PROFILE_CREATE_SCHEMA (o schema genérico, validado antes de
    profile_type ser resolvido) NÃO deve conter creci/bank_*/pix_key --
    essas regras vivem em PROFILE_AGENT_FIELDS_SCHEMA agora."""

    def test_agent_fields_absent_from_optional_and_types_and_constraints(self):
        for field in ("creci", "bank_name", "bank_account", "pix_key"):
            self.assertNotIn(field, SchemaValidator.PROFILE_CREATE_SCHEMA["optional"])
            self.assertNotIn(field, SchemaValidator.PROFILE_CREATE_SCHEMA["types"])
            self.assertNotIn(
                field, SchemaValidator.PROFILE_CREATE_SCHEMA["constraints"]
            )

    def test_malformed_creci_does_not_fail_base_schema_alone(self):
        """Prova que, isoladamente, PROFILE_CREATE_SCHEMA ignora um creci
        mal formatado -- a rejeição correta só acontece via o novo schema
        condicional, não pelo schema genérico."""
        payload = _valid_profile_payload(creci="ab")
        is_valid, errors = SchemaValidator.validate_request(
            payload, SchemaValidator.PROFILE_CREATE_SCHEMA
        )
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])

    def test_base_payload_without_agent_fields_is_valid(self):
        """Campos de agente são opcionais -- um perfil de qualquer tipo,
        sem eles, continua válido (comportamento inalterado)."""
        is_valid, errors = SchemaValidator.validate_request(
            _valid_profile_payload(), SchemaValidator.PROFILE_CREATE_SCHEMA
        )
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])


class TestProfileAgentFieldsSchema(unittest.TestCase):
    """PROFILE_AGENT_FIELDS_SCHEMA / validate_profile_agent_fields -- o
    schema condicional que profile_api.py::create_profile só invoca quando
    profile_type.code == "agent"."""

    def test_empty_payload_is_valid(self):
        """Todos os 4 campos são opcionais mesmo dentro deste schema --
        um agent pode ser registrado sem creci ainda (fluxo pré-existente
        de PUT /api/v1/agents/{id})."""
        is_valid, errors = SchemaValidator.validate_profile_agent_fields({})
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])

    def test_payload_with_all_agent_exclusive_fields_is_valid(self):
        payload = {
            "creci": "CRECI-SP 12345",
            "bank_name": "Banco do Brasil",
            "bank_account": "12345-6",
            "pix_key": "jane@example.com",
        }
        is_valid, errors = SchemaValidator.validate_profile_agent_fields(payload)
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])

    def test_creci_length_constraint_rejects_short_creci(self):
        """agent.creci com menos de 4 chars -> inválido, mesma regra de create_agent"""
        is_valid, errors = SchemaValidator.validate_profile_agent_fields(
            {"creci": "ab"}
        )
        self.assertFalse(is_valid)
        self.assertTrue(any("creci" in e for e in errors))

    def test_creci_constraint_is_the_same_function_as_agent_create_schema(self):
        """Reaproveitamento por referência (não cópia) -- evita divergência
        silenciosa entre as regras de creci de PROFILE_AGENT_FIELDS_SCHEMA e
        AGENT_CREATE_SCHEMA."""
        self.assertIs(
            SchemaValidator.PROFILE_AGENT_FIELDS_SCHEMA["constraints"]["creci"],
            SchemaValidator.AGENT_CREATE_SCHEMA["constraints"]["creci"],
        )

    def test_agent_fields_present_in_optional_and_types(self):
        for field in ("creci", "bank_name", "bank_account", "pix_key"):
            self.assertIn(
                field, SchemaValidator.PROFILE_AGENT_FIELDS_SCHEMA["optional"]
            )
            self.assertIn(field, SchemaValidator.PROFILE_AGENT_FIELDS_SCHEMA["types"])
            self.assertNotIn(
                field, SchemaValidator.PROFILE_AGENT_FIELDS_SCHEMA["required"]
            )


if __name__ == "__main__":
    unittest.main()
