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

    # NOTE (Feature 028, Task 1): content_ids (One2many to
    # thedevkitchen.cms.template.generic.content, inverse template_id) is
    # deliberately NOT defined here yet. That comodel does not exist until
    # Task 2 creates it — declaring the One2many against a not-yet-existing
    # comodel makes Odoo's registry fail to load entirely (KeyError in
    # fields.py:setup_nonrelated, confirmed empirically), which breaks the
    # whole Odoo instance, not just this module's tests. None of Task 1's
    # own tests reference content_ids. Add this field back when Task 2 lands
    # (thedevkitchen.cms.template.generic.content + its template_id M2one).

    # ==================== SQL CONSTRAINTS ====================

    _sql_constraints = [
        (
            "unique_name",
            "UNIQUE(name)",
            "A generic template with this name already exists.",
        ),
    ]
