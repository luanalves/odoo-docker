# -*- coding: utf-8 -*-


def resolve_company_by_slug(env, company_slug):
    """Resolve a res.company id from its CMS-settings company_slug.

    Returns the company_id (int) or None if no matching settings record
    exists. Uses sudo() — there is no Odoo user/session on the public
    routes that call this, so record rules cannot be evaluated anyway.
    """
    settings = (
        env["thedevkitchen.cms.settings"]
        .sudo()
        .search([("company_slug", "=", company_slug)], limit=1)
    )
    return settings.company_id.id if settings else None
