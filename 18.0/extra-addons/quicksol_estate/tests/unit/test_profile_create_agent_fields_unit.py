# -*- coding: utf-8 -*-
"""
Pure unittest.TestCase for Feature 026 (corrigido, 2026-07-23) —
PROFILE_CREATE_SCHEMA's agent-exclusive optional fields (creci/bank_name/
bank_account/pix_key), moved here from the (removed) `agent` node of
POST /api/v1/users/invite. These fields have no equivalent on
thedevkitchen.estate.profile for any OTHER profile_type, so they're
optional and only meaningful when profile_type_id resolves to 'agent'
(profile_api.py's create_profile already auto-creates the real.estate.agent
record in that case).

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


class TestProfileCreateAgentFields(unittest.TestCase):
    def test_base_payload_without_agent_fields_is_valid(self):
        """Campos de agente são opcionais -- um perfil de qualquer tipo,
        sem eles, continua válido (comportamento inalterado)."""
        is_valid, errors = SchemaValidator.validate_request(
            _valid_profile_payload(), SchemaValidator.PROFILE_CREATE_SCHEMA
        )
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])

    def test_payload_with_all_agent_exclusive_fields_is_valid(self):
        payload = _valid_profile_payload(
            creci="CRECI-SP 12345",
            bank_name="Banco do Brasil",
            bank_account="12345-6",
            pix_key="jane@example.com",
        )
        is_valid, errors = SchemaValidator.validate_request(
            payload, SchemaValidator.PROFILE_CREATE_SCHEMA
        )
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])

    def test_creci_length_constraint_rejects_short_creci(self):
        """agent.creci com menos de 4 chars -> inválido, mesma regra de create_agent"""
        payload = _valid_profile_payload(creci="ab")
        is_valid, errors = SchemaValidator.validate_request(
            payload, SchemaValidator.PROFILE_CREATE_SCHEMA
        )
        self.assertFalse(is_valid)
        self.assertTrue(any("creci" in e for e in errors))

    def test_creci_constraint_is_the_same_function_as_agent_create_schema(self):
        """Reaproveitamento por referência (não cópia) -- evita divergência silenciosa
        entre as regras de creci de PROFILE_CREATE_SCHEMA e AGENT_CREATE_SCHEMA."""
        self.assertIs(
            SchemaValidator.PROFILE_CREATE_SCHEMA["constraints"]["creci"],
            SchemaValidator.AGENT_CREATE_SCHEMA["constraints"]["creci"],
        )

    def test_agent_fields_present_in_optional_and_types(self):
        for field in ("creci", "bank_name", "bank_account", "pix_key"):
            self.assertIn(field, SchemaValidator.PROFILE_CREATE_SCHEMA["optional"])
            self.assertIn(field, SchemaValidator.PROFILE_CREATE_SCHEMA["types"])
            # None of these should ever be required -- they're only
            # meaningful for the 'agent' profile_type, and even then they
            # remain optional (an agent can be registered without a CRECI
            # yet, per the pre-existing PUT /api/v1/agents/{id} update path).
            self.assertNotIn(field, SchemaValidator.PROFILE_CREATE_SCHEMA["required"])


if __name__ == "__main__":
    unittest.main()
