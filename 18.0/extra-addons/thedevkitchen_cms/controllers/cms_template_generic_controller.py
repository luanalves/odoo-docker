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
from .cms_template_controller import TEMPLATE_MANAGEMENT_ROLES

_logger = logging.getLogger(__name__)

_GENERIC_TEMPLATE_LIST_LIMIT = 50

# Genuine alias of cms_template_controller.TEMPLATE_MANAGEMENT_ROLES — imported,
# never redigitized, to avoid authorization drift between sibling controllers
# (ADR-019). Kept under this name since other code/tests already reference it.
GENERIC_TEMPLATE_MANAGEMENT_ROLES = TEMPLATE_MANAGEMENT_ROLES

_COPY_NAME_MAX_ATTEMPTS = 100


def _clamp_pagination_params(limit, offset):
    """Validate and clamp pagination parameters.

    Args:
        limit: Requested limit (must be >= 1)
        offset: Requested offset (must be >= 0)

    Returns:
        tuple: (clamped_limit, clamped_offset)

    Raises:
        ValueError: if limit <= 0 or offset < 0

    Constraint: limit is floored at 1 and capped at _GENERIC_TEMPLATE_LIST_LIMIT.
    This prevents Odoo's ORM from treating limit=0 as "no limit" (which would
    omit the SQL LIMIT clause and return all rows).
    """
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")
    if offset < 0:
        raise ValueError(f"offset must be non-negative, got {offset}")

    clamped_limit = min(limit, _GENERIC_TEMPLATE_LIST_LIMIT)
    return clamped_limit, offset


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


def _unique_company_template_name(env, base_name, company_id):
    """Return a name unique for (name, company_id) in thedevkitchen.cms.template,
    applying an incrementing ' (N)' suffix on conflict (same pattern as
    CmsPageService._unique_slug). Returns None if no free name is found
    within _COPY_NAME_MAX_ATTEMPTS additional attempts (caller returns 409)."""
    Template = env["thedevkitchen.cms.template"].sudo()
    candidate = base_name
    if not Template.search_count([("name", "=", candidate), ("company_id", "=", company_id)]):
        return candidate
    for suffix in range(2, _COPY_NAME_MAX_ATTEMPTS + 2):
        candidate = f"{base_name} ({suffix})"
        if not Template.search_count([("name", "=", candidate), ("company_id", "=", company_id)]):
            return candidate
    return None


def _build_copy_create_vals(generic, name, company_id):
    """Build the create() vals for the company-scoped copy of a generic
    template. Only whitelisted fields are included — company_id always comes
    from the caller's already-resolved session company (ADR-008), never from
    a raw request payload (this function doesn't even accept one)."""
    return {
        "name": name,
        "category": generic.category,
        "company_id": company_id,
        "source_generic_template_id": generic.id,
    }


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
            limit = int(request.httprequest.args.get("limit", _GENERIC_TEMPLATE_LIST_LIMIT))
            limit, offset = _clamp_pagination_params(limit, offset)
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

    # ==================== COPY ====================

    @http.route(
        "/api/v1/cms/templates/generic/<int:template_id>/copy",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def copy_generic_template(self, template_id, **kwargs):
        role = resolve_role(request.env.user) or ""
        if role not in GENERIC_TEMPLATE_MANAGEMENT_ROLES:
            return _cms_error(403, "forbidden", "Insufficient permissions")

        generic = request.env["thedevkitchen.cms.template.generic"].sudo().search(
            [("id", "=", template_id), ("active", "=", True)], limit=1
        )
        if not generic:
            return _cms_error(404, "not_found", f"Generic template {template_id} not found")

        try:
            raw_body = request.httprequest.data
            data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (ValueError, UnicodeDecodeError):
            return _cms_error(400, "validation_error", "Invalid JSON in request body")

        if not isinstance(data, dict):
            return _cms_error(400, "validation_error", "Request body must be a JSON object")

        company_id = request.env.company.id
        requested_name = (data.get("name") or "").strip() or generic.name
        name = _unique_company_template_name(request.env, requested_name, company_id)
        if name is None:
            return _cms_error(409, "generic_copy_conflict", "Could not find a free name for the copy")

        source_content = generic.content_ids[0].content if generic.content_ids else None
        create_vals = _build_copy_create_vals(generic, name, company_id)

        try:
            with request.env.cr.savepoint():
                new_template = request.env["thedevkitchen.cms.template"].sudo().create(create_vals)
                request.env["thedevkitchen.cms.template.content"].sudo().create(
                    {"template_id": new_template.id, "content": source_content}
                )
        except (ValidationError, UserError) as exc:
            return _cms_error(422, "validation_error", str(exc.args[0]) if exc.args else "Validation failed")
        except Exception:
            _logger.exception("CMS copy_generic_template error")
            return _cms_error(500, "server_error", "An unexpected error occurred")

        payload = {
            "id": new_template.id,
            "name": new_template.name,
            "category": new_template.category,
            "active": new_template.active,
            "company_id": new_template.company_id.id,
            "source_generic_template_id": generic.id,
            "content": source_content,
            "created_at": new_template.create_date.isoformat() if new_template.create_date else None,
            "updated_at": new_template.write_date.isoformat() if new_template.write_date else None,
        }
        return Response(json.dumps(payload), status=201, content_type="application/json")
