# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request, Response
from odoo.exceptions import ValidationError, UserError
from odoo.addons.quicksol_estate.services.role_resolver import resolve_role
from odoo.addons.thedevkitchen_apigateway.middleware import (
    require_jwt,
    require_session,
    require_company,
)
from ..services.cms_error_helpers import _cms_error

_logger = logging.getLogger(__name__)

_GENERIC_TEMPLATE_LIST_LIMIT = 50

# Same literal tuple as cms_template_controller.py — reused, never redigitized,
# to avoid authorization drift between sibling controllers (ADR-019).
GENERIC_TEMPLATE_MANAGEMENT_ROLES = ("owner", "director", "manager")


def _serialize_generic_template(template, include_content=False):
    data = {
        "id": template.id,
        "name": template.name,
        "category": template.category,
        "active": template.active,
        "created_at": template.create_date.isoformat() if template.create_date else None,
        "updated_at": template.write_date.isoformat() if template.write_date else None,
    }
    if include_content:
        data["content"] = template.content_ids[0].content if template.content_ids else None
    return data


class CmsTemplateGenericController(http.Controller):

    # ==================== LIST ====================

    @http.route(
        "/api/v1/cms/templates/generic",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def list_generic_templates(self, **kwargs):
        role = resolve_role(request.env.user) or ""
        if role not in GENERIC_TEMPLATE_MANAGEMENT_ROLES:
            return _cms_error(403, "forbidden", "Insufficient permissions")

        try:
            offset = int(request.httprequest.args.get("offset", 0))
            limit = min(
                int(request.httprequest.args.get("limit", _GENERIC_TEMPLATE_LIST_LIMIT)),
                _GENERIC_TEMPLATE_LIST_LIMIT,
            )
        except (ValueError, TypeError):
            return _cms_error(400, "validation_error", "Invalid pagination parameters")

        domain = [("active", "=", True)]
        category = request.httprequest.args.get("category")
        if category:
            domain.append(("category", "=", category))

        Generic = request.env["thedevkitchen.cms.template.generic"].sudo()
        templates = Generic.search(domain, limit=limit, offset=offset, order="name")
        total = Generic.search_count(domain)
        payload = {
            "items": [_serialize_generic_template(t) for t in templates],
            "total": total,
            "offset": offset,
            "limit": limit,
        }
        return Response(json.dumps(payload), status=200, content_type="application/json")

    # ==================== GET BY ID ====================

    @http.route(
        "/api/v1/cms/templates/generic/<int:template_id>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def get_generic_template(self, template_id, **kwargs):
        role = resolve_role(request.env.user) or ""
        if role not in GENERIC_TEMPLATE_MANAGEMENT_ROLES:
            return _cms_error(403, "forbidden", "Insufficient permissions")

        template = request.env["thedevkitchen.cms.template.generic"].sudo().search(
            [("id", "=", template_id), ("active", "=", True)], limit=1
        )
        if not template:
            return _cms_error(404, "not_found", f"Generic template {template_id} not found")

        return Response(
            json.dumps(_serialize_generic_template(template, include_content=True)),
            status=200,
            content_type="application/json",
        )
