# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestAgentUserIdIndex(TransactionCase):
    def test_user_id_field_has_index(self):
        """Feature 026: user_id deve ter index=True (hot-path de RBAC após esta feature)"""
        field = self.env["real.estate.agent"]._fields["user_id"]
        self.assertTrue(
            field.index,
            "real.estate.agent.user_id deve ter index=True — "
            "campo lido em toda listagem de imóveis/leads por usuário 'agent'",
        )
