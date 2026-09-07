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

_TEMPLATE_LIST_LIMIT = 50

TEMPLATE_MANAGEMENT_ROLES = ("owner", "director", "manager")


def _serialize_template(template, include_content=False):
    data = {
        "id": template.id,
        "name": template.name,
        "category": template.category,
        "active": template.active,
        "company_id": template.company_id.id,
        "source_generic_template_id": (
            template.source_generic_template_id.id if template.source_generic_template_id else None
        ),
        "created_at": template.create_date.isoformat() if template.create_date else None,
        "updated_at": template.write_date.isoformat() if template.write_date else None,
    }
    if include_content:
        data["content"] = template.content_ids[0].content if template.content_ids else None
    return data


class CmsTemplateController(http.Controller):

    # ==================== CREATE ====================

    @http.route(
        "/api/v1/cms/templates",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def create_template(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _cms_error(400, "validation_error", "Invalid JSON in request body")

        company_id = request.env.company.id
        role = resolve_role(request.env.user) or ""

        if role not in TEMPLATE_MANAGEMENT_ROLES:
            return _cms_error(403, "forbidden", "Insufficient permissions")

        content = data.pop("content", None)
        data["company_id"] = company_id

        try:
            template = request.env["thedevkitchen.cms.template"].sudo().create(data)
            request.env["thedevkitchen.cms.template.content"].sudo().create(
                {"template_id": template.id, "content": content}
            )
        except ValueError as exc:
            return _cms_error(422, "validation_error", str(exc))
        except (ValidationError, UserError) as exc:
            return _cms_error(422, "validation_error", str(exc.args[0]) if exc.args else "Validation failed")
        except Exception:
            _logger.exception("CMS create_template error")
            return _cms_error(500, "server_error", "An unexpected error occurred")

        return Response(
            json.dumps(_serialize_template(template, include_content=True)),
            status=201,
            content_type="application/json",
        )

    # ==================== LIST ====================

    @http.route(
        "/api/v1/cms/templates",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def list_templates(self, **kwargs):
        company_id = request.env.company.id
        role = resolve_role(request.env.user) or ""

        if role not in TEMPLATE_MANAGEMENT_ROLES:
            return _cms_error(403, "forbidden", "Insufficient permissions to list templates")

        try:
            offset = int(request.httprequest.args.get("offset", 0))
            limit = min(int(request.httprequest.args.get("limit", _TEMPLATE_LIST_LIMIT)), _TEMPLATE_LIST_LIMIT)
        except (ValueError, TypeError):
            return _cms_error(400, "validation_error", "Invalid pagination parameters")

        domain = [("company_id", "=", company_id)]
        templates = request.env["thedevkitchen.cms.template"].sudo().search(
            domain, limit=limit, offset=offset, order="name"
        )
        total = request.env["thedevkitchen.cms.template"].sudo().search_count(domain)
        payload = {
            "items": [_serialize_template(t, include_content=False) for t in templates],
            "total": total,
            "offset": offset,
            "limit": limit,
        }
        return Response(json.dumps(payload), status=200, content_type="application/json")

    # ==================== GET BY ID ====================

    @http.route(
        "/api/v1/cms/templates/<int:template_id>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def get_template(self, template_id, **kwargs):
        company_id = request.env.company.id
        role = resolve_role(request.env.user) or ""

        if role not in TEMPLATE_MANAGEMENT_ROLES:
            return _cms_error(403, "forbidden", "Insufficient permissions")

        template = request.env["thedevkitchen.cms.template"].sudo().search(
            [("id", "=", template_id), ("company_id", "=", company_id)], limit=1
        )
        if not template:
            return _cms_error(404, "not_found", f"Template {template_id} not found")

        return Response(
            json.dumps(_serialize_template(template, include_content=True)),
            status=200,
            content_type="application/json",
        )

    # ==================== UPDATE ====================

    @http.route(
        "/api/v1/cms/templates/<int:template_id>",
        type="http",
        auth="none",
        methods=["PUT"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def update_template(self, template_id, **kwargs):
        try:
            data = json.loads(request.httprequest.data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _cms_error(400, "validation_error", "Invalid JSON in request body")

        company_id = request.env.company.id
        role = resolve_role(request.env.user) or ""

        if role not in TEMPLATE_MANAGEMENT_ROLES:
            return _cms_error(403, "forbidden", "Insufficient permissions")

        template = request.env["thedevkitchen.cms.template"].sudo().search(
            [("id", "=", template_id), ("company_id", "=", company_id)], limit=1
        )
        if not template:
            return _cms_error(404, "not_found", f"Template {template_id} not found")

        content = data.pop("content", None)
        try:
            if data:
                template.write(data)
            if content is not None:
                if template.content_ids:
                    template.content_ids[0].write({"content": content})
                else:
                    request.env["thedevkitchen.cms.template.content"].sudo().create(
                        {"template_id": template.id, "content": content}
                    )
        except (ValidationError, UserError) as exc:
            return _cms_error(422, "validation_error", str(exc.args[0]) if exc.args else "Validation failed")
        except Exception:
            _logger.exception("CMS update_template error")
            return _cms_error(500, "server_error", "An unexpected error occurred")

        return Response(
            json.dumps(_serialize_template(template, include_content=True)),
            status=200,
            content_type="application/json",
        )

    # ==================== DELETE (soft) ====================

    @http.route(
        "/api/v1/cms/templates/<int:template_id>",
        type="http",
        auth="none",
        methods=["DELETE"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def delete_template(self, template_id, **kwargs):
        company_id = request.env.company.id
        role = resolve_role(request.env.user) or ""

        if role not in TEMPLATE_MANAGEMENT_ROLES:
            return _cms_error(403, "forbidden", "Insufficient permissions")

        template = request.env["thedevkitchen.cms.template"].sudo().search(
            [("id", "=", template_id), ("company_id", "=", company_id)], limit=1
        )
        if not template:
            return _cms_error(404, "not_found", f"Template {template_id} not found")

        template.write({"active": False})
        return Response(
            json.dumps({"success": True, "id": template_id}),
            status=200,
            content_type="application/json",
        )
