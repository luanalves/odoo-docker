# -*- coding: utf-8 -*-
from odoo import models, fields


class CmsTemplate(models.Model):
    _name = "thedevkitchen.cms.template"
    _description = "CMS Template"
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
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )

    # ==================== BACK-REFERENCES ====================

    content_ids = fields.One2many(
        comodel_name="thedevkitchen.cms.template.content",
        inverse_name="template_id",
        string="Template Content",
    )
    html_content = fields.Html(
        string="HTML Content",
        sanitize=False,
        help="Rich text content for editing in the Odoo admin UI. The API uses the Puck JSON (content_ids).",
    )
    source_generic_template_id = fields.Many2one(
        comodel_name="thedevkitchen.cms.template.generic",
        string="Source Generic Template",
        ondelete="set null",
        readonly=True,
        help="Generic (platform-level) template this record was copied from, if any. "
        "Null when created manually. Deactivating/deleting the source never affects this copy.",
    )

    # ==================== SQL CONSTRAINTS ====================

    _sql_constraints = [
        (
            "unique_name_company",
            "UNIQUE(name, company_id)",
            "A template with this name already exists for this company.",
        ),
    ]
