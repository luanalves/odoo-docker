# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request, Response
from odoo.exceptions import ValidationError, UserError
from psycopg2.errors import UniqueViolation
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

# PR #31 review: the search-then-create in _create_company_template_copy is
# not atomic on its own — two concurrent copy requests can both see a name as
# free before either commits. This bounds how many times we re-check +
# re-attempt the create when we actually hit that race (UNIQUE(name,
# company_id) violation on insert), as opposed to _COPY_NAME_MAX_ATTEMPTS,
# which bounds how many *candidate names* _unique_company_template_name will
# try within a single attempt. A real race is rare and self-resolving within
# a couple of retries; this is not meant to survive sustained contention on
# the exact same name.
_COPY_CREATE_RETRY_ATTEMPTS = 3


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


def _create_company_template_copy(env, generic, base_name, company_id, source_content):
    """Create the company-scoped copy of a generic template, closing the
    check-then-create race on PR #31 review: if a concurrent request creates
    the winning candidate name between our availability check
    (_unique_company_template_name) and our INSERT, the UNIQUE(name,
    company_id) constraint on thedevkitchen.cms.template raises
    psycopg2.errors.UniqueViolation on create() — caught here specifically
    (not swallowed as a generic 500) and retried with a freshly re-checked
    name, up to _COPY_CREATE_RETRY_ATTEMPTS times. Each attempt runs inside
    its own savepoint so a collision rolls back only that attempt.

    Returns the new thedevkitchen.cms.template record, or None if no free
    name could be found/created (caller returns 409 generic_copy_conflict)."""
    Template = env["thedevkitchen.cms.template"].sudo()
    Content = env["thedevkitchen.cms.template.content"].sudo()

    for _attempt in range(_COPY_CREATE_RETRY_ATTEMPTS):
        name = _unique_company_template_name(env, base_name, company_id)
        if name is None:
            return None

        create_vals = _build_copy_create_vals(generic, name, company_id)
        try:
            with env.cr.savepoint():
                new_template = Template.create(create_vals)
                Content.create({"template_id": new_template.id, "content": source_content})
            return new_template
        except UniqueViolation:
            continue  # a concurrent request won the race for `name` — re-check and retry

    return None


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

        raw_name = data.get("name")
        if raw_name is not None and not isinstance(raw_name, str):
            return _cms_error(400, "validation_error", "'name' must be a string")

        company_id = request.env.company.id
        requested_name = (raw_name or "").strip() or generic.name
        source_content = generic.content_ids[0].content if generic.content_ids else None

        try:
            new_template = _create_company_template_copy(
                request.env, generic, requested_name, company_id, source_content
            )
        except (ValidationError, UserError) as exc:
            return _cms_error(422, "validation_error", str(exc.args[0]) if exc.args else "Validation failed")
        except Exception:
            _logger.exception("CMS copy_generic_template error")
            return _cms_error(500, "server_error", "An unexpected error occurred")

        if new_template is None:
            return _cms_error(409, "generic_copy_conflict", "Could not find a free name for the copy")

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
