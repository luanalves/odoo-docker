# -*- coding: utf-8 -*-
"""
Unit tests for the pure helpers backing cms_template_generic_controller.py.
The HTTP route methods themselves (list_generic_templates, get_generic_template,
copy_generic_template) require a live Odoo request/env and are exercised by
integration_tests/test_us028_cms_generic_templates.sh instead — consistent
with how cms_template_controller.py's routes have never carried their own
unit tests in this module.
"""
import unittest
from unittest.mock import MagicMock

from odoo.addons.thedevkitchen_cms.controllers.cms_template_generic_controller import (
    GENERIC_TEMPLATE_MANAGEMENT_ROLES,
    _serialize_generic_template,
)


class TestGenericTemplateManagementRoles(unittest.TestCase):

    def test_roles_match_cms_template_controller_exactly(self):
        """Must be the literal same tuple as cms_template_controller.py's
        role check, to avoid authorization drift between sibling controllers
        (spec Non-Goal: 'não redigitar a lista')."""
        self.assertEqual(GENERIC_TEMPLATE_MANAGEMENT_ROLES, ("owner", "director", "manager"))

    def test_agent_role_not_authorized(self):
        self.assertNotIn("agent", GENERIC_TEMPLATE_MANAGEMENT_ROLES)

    def test_tenant_role_not_authorized(self):
        self.assertNotIn("tenant", GENERIC_TEMPLATE_MANAGEMENT_ROLES)


class TestSerializeGenericTemplate(unittest.TestCase):

    def _make_template(self, content=None):
        tpl = MagicMock()
        tpl.id = 1
        tpl.name = "seed_generic_landing"
        tpl.category = "landing"
        tpl.active = True
        tpl.create_date.isoformat.return_value = "2026-09-01T10:00:00"
        tpl.write_date.isoformat.return_value = "2026-09-01T10:00:00"
        if content is not None:
            content_record = MagicMock()
            content_record.content = content
            tpl.content_ids = [content_record]
        else:
            tpl.content_ids = []
        return tpl

    def test_list_serialization_excludes_content(self):
        """Listing must never include 'content' — avoids N+1 and heavy payloads."""
        tpl = self._make_template(content='{"content": []}')
        data = _serialize_generic_template(tpl, include_content=False)
        self.assertNotIn("content", data)

    def test_list_serialization_excludes_company_id(self):
        """Generic templates have no company_id — must never appear in the payload."""
        tpl = self._make_template()
        data = _serialize_generic_template(tpl, include_content=False)
        self.assertNotIn("company_id", data)

    def test_detail_serialization_includes_content(self):
        tpl = self._make_template(content='{"content": []}')
        data = _serialize_generic_template(tpl, include_content=True)
        self.assertEqual(data["content"], '{"content": []}')

    def test_detail_serialization_content_none_when_no_content_record(self):
        tpl = self._make_template(content=None)
        data = _serialize_generic_template(tpl, include_content=True)
        self.assertIsNone(data["content"])

    def test_serialization_includes_core_fields(self):
        tpl = self._make_template()
        data = _serialize_generic_template(tpl)
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["name"], "seed_generic_landing")
        self.assertEqual(data["category"], "landing")
        self.assertTrue(data["active"])


if __name__ == "__main__":
    unittest.main()
