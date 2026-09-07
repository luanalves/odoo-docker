# -*- coding: utf-8 -*-
"""
Unit tests for validate_generic_content() — the pure-function JSON/size
validator backing thedevkitchen.cms.template.generic.content's
@api.constrains('content'). Extracted as a standalone function (same
rationale as CmsPageService._update_content) so it can be unit-tested
without an Odoo environment.
"""
import json
import unittest

from odoo.addons.thedevkitchen_cms.models.cms_template_generic_content import (
    MAX_GENERIC_CONTENT_BYTES,
    validate_generic_content,
)

try:
    from odoo.exceptions import ValidationError
except (ImportError, ModuleNotFoundError, AttributeError):
    class ValidationError(Exception):  # noqa: N818
        pass


class TestValidateGenericContent(unittest.TestCase):

    def test_none_is_allowed(self):
        validate_generic_content(None)  # must not raise

    def test_empty_string_is_allowed(self):
        validate_generic_content("")  # must not raise

    def test_valid_json_is_allowed(self):
        content = json.dumps({"root": {}, "content": []})
        validate_generic_content(content)  # must not raise

    def test_invalid_json_raises(self):
        with self.assertRaises(ValidationError):
            validate_generic_content("not-a-json-string")

    def test_content_within_limit_is_allowed(self):
        payload = json.dumps({"content": ["x" * 100]})
        self.assertLessEqual(len(payload.encode("utf-8")), MAX_GENERIC_CONTENT_BYTES)
        validate_generic_content(payload)  # must not raise

    def test_content_over_limit_raises(self):
        oversized = json.dumps({"content": "x" * (MAX_GENERIC_CONTENT_BYTES + 1)})
        with self.assertRaises(ValidationError):
            validate_generic_content(oversized)

    def test_limit_is_512kb(self):
        self.assertEqual(MAX_GENERIC_CONTENT_BYTES, 512 * 1024)


if __name__ == "__main__":
    unittest.main()
