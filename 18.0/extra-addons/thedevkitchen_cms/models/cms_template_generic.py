# -*- coding: utf-8 -*-
from odoo import models, fields


class CmsTemplateGeneric(models.Model):
    _name = "thedevkitchen.cms.template.generic"
    _description = "CMS Generic Template (Platform Catalog)"
    _order = "name"

    # ==================== CORE FIELDS ====================

    name = fields.Char(string="Template Name", required=True)
    category = fields.Selection(
        selection=[
            ("landing", "Landing Page"),
            ("property", "Property Page"),
            ("about", "About Page"),
        ],
        string="Category",
        required=True,
        index=True,
    )
    active = fields.Boolean(default=True)

    # ==================== BACK-REFERENCES ====================

    content_ids = fields.One2many(
        comodel_name="thedevkitchen.cms.template.generic.content",
        inverse_name="template_id",
        string="Template Content",
    )

    # ==================== SQL CONSTRAINTS ====================

    _sql_constraints = [
        (
            "unique_name",
            "UNIQUE(name)",
            "A generic template with this name already exists.",
        ),
    ]
