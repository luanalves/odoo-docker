# -*- coding: utf-8 -*-
"""
Pure unittest.TestCase for Feature 026 — real.estate.agent.user_id index.

No Odoo environment/database required: imports the model class directly
via the same odoo.addons.__path__ extension trick used by run_unit_tests.py,
and inspects the field descriptor at the class level.
"""
import unittest
from pathlib import Path

import odoo.addons

_addons_root = str(Path(__file__).parent.parent.parent.parent)  # /mnt/extra-addons
if _addons_root not in odoo.addons.__path__:
    odoo.addons.__path__.insert(0, _addons_root)

from odoo.addons.quicksol_estate.models.agent import RealEstateAgent  # noqa: E402


class TestAgentUserIdIndex(unittest.TestCase):
    def test_user_id_field_has_index(self):
        """Feature 026: user_id deve ter index=True (hot-path de RBAC após esta feature)"""
        field = RealEstateAgent.user_id
        self.assertTrue(
            field.index,
            "real.estate.agent.user_id deve ter index=True — "
            "campo lido em toda listagem de imóveis/leads por usuário 'agent'",
        )


if __name__ == "__main__":
    unittest.main()
