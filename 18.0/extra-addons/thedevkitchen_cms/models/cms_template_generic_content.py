# -*- coding: utf-8 -*-
import json
from odoo import models, fields, api
from odoo.exceptions import ValidationError

MAX_GENERIC_CONTENT_BYTES = 512 * 1024  # 512 KB — same limit as thedevkitchen.cms.page.content


def validate_generic_content(content):
    """Raise ValidationError if content is set but is not valid JSON, or
    exceeds MAX_GENERIC_CONTENT_BYTES. Pure function (no Odoo env required)
    so it is directly unit-testable — see
    tests/unit/test_cms_template_generic_content_validations.py."""
    if not content:
        return
    if len(content.encode("utf-8")) > MAX_GENERIC_CONTENT_BYTES:
        raise ValidationError("Generic template content exceeds the 512KB limit.")
    try:
        json.loads(content)
    except (ValueError, TypeError):
        raise ValidationError("Generic template content must be valid JSON.")


class CmsTemplateGenericContent(models.Model):
    _name = "thedevkitchen.cms.template.generic.content"
    _description = "CMS Generic Template Content"

    # ==================== CORE FIELDS ====================

    template_id = fields.Many2one(
        comodel_name="thedevkitchen.cms.template.generic",
        string="Generic Template",
        required=True,
        ondelete="cascade",
        index=True,
    )
    content = fields.Text(
        string="Content (Puck JSON)",
        help="Puck editor JSON payload for this generic template. Validated for JSON validity and size (≤512KB).",
    )

    # ==================== SQL CONSTRAINTS ====================

    _sql_constraints = [
        (
            "unique_template",
            "UNIQUE(template_id)",
            "A generic template can have only one content record (1:1 relationship).",
        ),
    ]

    # ==================== VALIDATION ====================

    @api.constrains("content")
    def _check_content(self):
        for record in self:
            validate_generic_content(record.content)
