# -*- coding: utf-8 -*-
import base64
import json
import logging

import magic

from odoo import http
from odoo.http import request, Response
from odoo.addons.thedevkitchen_apigateway.middleware import require_jwt

from ..services.cms_error_helpers import _cms_error
from ..services.cms_public_property_serializer import serialize_public_property
from ..services.cms_public_property_service import (
    PUBLIC_PROPERTY_STATUSES,
    build_public_property_domain,
    parse_ids_filter,
    parse_limit,
    parse_sort,
    parse_status_filter,
)
from ..services.cms_slug_service import resolve_company_by_slug

_logger = logging.getLogger(__name__)


class CmsPublicPropertyController(http.Controller):

    # public endpoint
    # JWT-authenticated endpoint — requires Bearer token from the frontend
    # application. auth='none' + @require_jwt enforces token validation at
    # the middleware level. Not unauthenticated: intended for
    # server-to-server or SSR clients with a service token, same pattern
    # as CmsPublicController.get_public_page.
    @http.route(
        "/api/v1/public/properties/<string:company_slug>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    def list_public_properties(self, company_slug, **kwargs):
        try:
            company_id = resolve_company_by_slug(request.env, company_slug)
            if not company_id:
                return _cms_error(
                    404, "not_found", f"Company '{company_slug}' not found"
                )

            raw_status = kwargs.get("status")
            status_values, status_ok = parse_status_filter(raw_status)
            if not status_ok:
                return _cms_error(
                    400,
                    "validation_error",
                    "Invalid status value(s)",
                    allowed=sorted(PUBLIC_PROPERTY_STATUSES),
                )

            raw_ids = kwargs.get("ids")
            ids, ids_ok = parse_ids_filter(raw_ids)
            if not ids_ok:
                return _cms_error(
                    400,
                    "validation_error",
                    "ids must be a comma-separated list of integers",
                )

            raw_sort = kwargs.get("sort")
            order, sort_ok = parse_sort(raw_sort)
            if not sort_ok:
                return _cms_error(
                    400, "validation_error", "sort must be 'newest' or 'oldest'"
                )

            raw_limit = kwargs.get("limit")
            limit, limit_ok = parse_limit(raw_limit)
            if not limit_ok:
                return _cms_error(
                    400, "validation_error", "limit must be a positive integer"
                )

            domain = build_public_property_domain(company_id, status_values, ids)
            properties = (
                request.env["real.estate.property"]
                .sudo()
                .with_context(bin_size=True)
                .search(domain, limit=limit, order=order)
            )

            data = [
                serialize_public_property(prop, company_slug) for prop in properties
            ]

            self_link = (
                f"/api/v1/public/properties/{company_slug}"
                f"?sort={raw_sort or 'newest'}&limit={limit}"
            )
            if raw_status:
                self_link += f"&status={raw_status}"
            if raw_ids:
                self_link += f"&ids={raw_ids}"

            payload = {
                "company_slug": company_slug,
                "count": len(data),
                "limit": limit,
                "filters": {
                    "status": status_values,
                    "ids": ids,
                    "sort": raw_sort or "newest",
                },
                "data": data,
                "_links": {"self": self_link},
            }

            return Response(
                json.dumps(payload), status=200, content_type="application/json"
            )
        except Exception:
            _logger.exception("CMS list_public_properties unexpected error")
            return _cms_error(500, "internal_error", "An unexpected error occurred.")

    # public endpoint
    # Same auth model as list_public_properties — see comment above that
    # route. No Content-Disposition header: inline rendering for <img>
    # tags, unlike the authenticated attachment-download endpoint which
    # forces `attachment;` disposition (property_attachments_controller.py).
    @http.route(
        "/api/v1/public/properties/<string:company_slug>/<int:property_id>/image",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    def get_public_property_image(self, company_slug, property_id, **kwargs):
        try:
            company_id = resolve_company_by_slug(request.env, company_slug)
            if not company_id:
                return _cms_error(404, "not_found", "Image not found")

            domain = build_public_property_domain(company_id) + [
                ("id", "=", property_id)
            ]

            prop = request.env["real.estate.property"].sudo().search(domain, limit=1)
            if not prop or not prop.image:
                return _cms_error(404, "not_found", "Image not found")

            content = base64.b64decode(prop.image)
            mimetype = magic.from_buffer(content[:2048], mime=True)

            return Response(
                content,
                status=200,
                headers={
                    "Content-Type": mimetype,
                    "Content-Security-Policy": "default-src 'none'",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        except Exception:
            _logger.exception("CMS get_public_property_image unexpected error")
            return _cms_error(500, "internal_error", "An unexpected error occurred.")
