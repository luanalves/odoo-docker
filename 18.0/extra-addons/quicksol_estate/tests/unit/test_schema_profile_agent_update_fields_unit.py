# -*- coding: utf-8 -*-
"""
Pure unittest.TestCase for Feature 027 FR5.1/FR5.2 — PUT /api/v1/profiles/<id>
accepts creci/bank_* fields, validated only when profile_type == 'agent'.
No Odoo environment/database required (same pattern as
test_profile_create_agent_fields_unit.py).
"""
import unittest
from pathlib import Path

import odoo.addons

_addons_root = str(Path(__file__).parent.parent.parent.parent)
if _addons_root not in odoo.addons.__path__:
    odoo.addons.__path__.insert(0, _addons_root)

from odoo.addons.quicksol_estate.controllers.utils.schema import (
    SchemaValidator,
)  # noqa: E402


class TestProfileAgentUpdateFieldsSchema(unittest.TestCase):
    def test_all_six_fields_are_optional(self):
        is_valid, errors = SchemaValidator.validate_profile_agent_update_fields({})
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])

    def test_valid_full_payload(self):
        payload = {
            "creci": "CRECI-SP 12345",
            "bank_name": "Banco do Brasil",
            "bank_account": "12345-6",
            "bank_account_type": "checking",
            "bank_branch": "0001",
            "pix_key": "agent@example.com",
        }
        is_valid, errors = SchemaValidator.validate_profile_agent_update_fields(
            payload
        )
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])

    def test_malformed_creci_rejected(self):
        is_valid, errors = SchemaValidator.validate_profile_agent_update_fields(
            {"creci": "ab"}
        )
        self.assertFalse(is_valid)
        self.assertTrue(any("creci" in e for e in errors))

    def test_bank_account_type_and_branch_present_in_schema(self):
        """FR5.1: these two fields existed in AGENT_UPDATE_SCHEMA's legacy
        allowed_fields list in agent_api.py without any schema validation --
        this closes that gap."""
        self.assertIn(
            "bank_account_type",
            SchemaValidator.PROFILE_AGENT_UPDATE_FIELDS_SCHEMA["optional"],
        )
        self.assertIn(
            "bank_branch",
            SchemaValidator.PROFILE_AGENT_UPDATE_FIELDS_SCHEMA["optional"],
        )


if __name__ == "__main__":
    unittest.main()
