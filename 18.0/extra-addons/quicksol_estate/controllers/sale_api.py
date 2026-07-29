# -*- coding: utf-8 -*-

import json
import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError
from .utils.auth import require_jwt
from .utils.response import error_response
from .utils.schema import SchemaValidator
from odoo.addons.thedevkitchen_apigateway.middleware import (
    require_session,
    require_company,
)
from ..utils.responses import (
    success_response as util_success,
    error_response as util_error,
    paginated_response,
    build_hateoas_links,
    build_pagination_links,
)
from ..utils.validators import validate_email_format

_logger = logging.getLogger(__name__)


class SaleApiController(http.Controller):

    # ========== HELPERS ==========

    def _get_company_ids(self):
        """Get company IDs from current session context."""
        user = request.env.user
        if user.has_group("base.group_system"):
            return None
        return user.company_ids.ids

    def _get_agent_property_ids(self, user, company_ids):
        """Get property IDs assigned to agent (transitive RBAC per R3)."""
        agent = (
            request.env["real.estate.agent"]
            .sudo()
            .search(
                [
                    ("user_id", "=", user.id),
                    ("company_id", "in", company_ids),
                ],
                limit=1,
            )
        )
        if not agent:
            return []
        assignments = (
            request.env["real.estate.agent.property.assignment"]
            .sudo()
            .search(
                [
                    ("agent_id", "=", agent.id),
                ]
            )
        )
        return assignments.mapped("property_id").ids

    def _is_agent_role(self, user):
        """Check if user has only agent role (not manager/owner)."""
        return (
            user.has_group("quicksol_estate.group_real_estate_agent")
            and not user.has_group("quicksol_estate.group_real_estate_manager")
            and not user.has_group("quicksol_estate.group_real_estate_owner")
            and not user.has_group("base.group_system")
        )

    def _serialize_sale(self, sale):
        """Serialize a sale record to dict with HATEOAS links."""
        relations = {}
        if sale.status != "cancelled":
            relations["cancel"] = "/cancel"

        links = build_hateoas_links(
            base_url="/api/v1/sales",
            resource_id=sale.id,
            relations=relations,
        )
        # Related resource links
        if sale.property_id:
            links["property"] = f"/api/v1/properties/{sale.property_id.id}"
        if sale.agent_id:
            # Feature 027 (FR6.4): /api/v1/agents/{id} is removed; point at
            # the unified profile instead. Legacy agents created before
            # Feature 010 have no profile_id -- omit the link rather than
            # build a URL that 404s.
            if sale.agent_id.profile_id:
                links["agent"] = f"/api/v1/profiles/{sale.agent_id.profile_id.id}"

        return {
            "id": sale.id,
            "property_id": sale.property_id.id,
            "property_name": sale.property_id.name if sale.property_id else None,
            "buyer_name": sale.buyer_name,
            "buyer_phone": sale.buyer_phone or None,
            "buyer_email": sale.buyer_email or None,
            "company_id": sale.company_id.id if sale.company_id else None,
            "agent_id": sale.agent_id.id if sale.agent_id else None,
            "agent_name": sale.agent_id.name if sale.agent_id else None,
            "lead_id": sale.lead_id.id if sale.lead_id else None,
            "sale_date": str(sale.sale_date) if sale.sale_date else None,
            "sale_price": sale.sale_price,
            "status": sale.status,
            "active": sale.active,
            "cancellation_date": (
                str(sale.cancellation_date) if sale.cancellation_date else None
            ),
            "cancellation_reason": sale.cancellation_reason or None,
            "_links": links,
        }

    # ========== LIST SALES (FR-021, FR-030, FR-033) ==========

    @http.route(
        "/api/v1/sales", type="http", auth="none", methods=["GET"], csrf=False, cors="*"
    )
    @require_jwt
    @require_session
    @require_company
    def list_sales(self, page=1, page_size=20, **kwargs):
        """List sales with pagination, filters, and company isolation."""
        try:
            user = request.env.user
            company_ids = self._get_company_ids()

            # Pagination
            try:
                page = int(page)
                page_size = min(int(page_size), 100)
            except (ValueError, TypeError):
                resp, code = util_error(
                    "Invalid pagination parameters", status_code=400
                )
                return request.make_json_response(resp, status=code)

            if page < 1 or page_size < 1:
                resp, code = util_error(
                    "Page and page_size must be positive integers", status_code=400
                )
                return request.make_json_response(resp, status=code)

            # Base domain
            domain = [("active", "=", True)]

            # is_active filter (US5)
            is_active = kwargs.get("is_active")
            if is_active is not None and is_active.lower() == "false":
                domain = [("active", "=", False)]

            # Company isolation (FR-030)
            if company_ids is not None:
                domain.append(("company_id", "in", company_ids))

            # Optional filters
            if kwargs.get("property_id"):
                try:
                    domain.append(("property_id", "=", int(kwargs["property_id"])))
                except ValueError:
                    pass
            if kwargs.get("agent_id"):
                try:
                    domain.append(("agent_id", "=", int(kwargs["agent_id"])))
                except ValueError:
                    pass
            if kwargs.get("status"):
                domain.append(("status", "=", kwargs["status"]))
            if kwargs.get("min_price"):
                try:
                    domain.append(("sale_price", ">=", float(kwargs["min_price"])))
                except ValueError:
                    pass
            if kwargs.get("max_price"):
                try:
                    domain.append(("sale_price", "<=", float(kwargs["max_price"])))
                except ValueError:
                    pass

            # Agent RBAC: agent sees own sales only (R3)
            if self._is_agent_role(user):
                assigned_prop_ids = self._get_agent_property_ids(
                    user, company_ids or []
                )
                if assigned_prop_ids:
                    domain.append(("property_id", "in", assigned_prop_ids))
                else:
                    resp, code = paginated_response(
                        items=[], total=0, page=page, page_size=page_size
                    )
                    return request.make_json_response(resp, status=code)

            # Search
            Sale = request.env["real.estate.sale"].sudo()
            if is_active is not None and is_active.lower() == "false":
                Sale = Sale.with_context(active_test=False)

            total = Sale.search_count(domain)
            offset = (page - 1) * page_size
            sales = Sale.search(
                domain, limit=page_size, offset=offset, order="sale_date desc"
            )

            items = [self._serialize_sale(s) for s in sales]

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1
            links = build_pagination_links("/api/v1/sales", page, total_pages)

            resp, code = paginated_response(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
                links=links,
            )
            return request.make_json_response(resp, status=code)

        except Exception as e:
            _logger.error(f"Error listing sales: {str(e)}", exc_info=True)
            return error_response(500, "Internal server error")

    # ========== CREATE SALE (FR-022, FR-023, FR-028, FR-029) ==========

    @http.route(
        "/api/v1/sales",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def create_sale(self, **kwargs):
        """Create a new sale with validation."""
        try:
            # Parse body
            try:
                data = json.loads(request.httprequest.data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return error_response(400, "Invalid JSON in request body")

            # Validate schema
            is_valid, errors = SchemaValidator.validate_request(
                data, SchemaValidator.SALE_CREATE_SCHEMA
            )
            if not is_valid:
                resp, code = util_error(
                    "Validation failed", errors={"validation": errors}, status_code=400
                )
                return request.make_json_response(resp, status=code)

            company_ids = self._get_company_ids()
            if not company_ids:
                return error_response(400, "No company context available")

            # Validate email format
            if data.get("buyer_email") and not validate_email_format(
                data["buyer_email"]
            ):
                resp, code = util_error(
                    f"Invalid email format: {data['buyer_email']}", status_code=400
                )
                return request.make_json_response(resp, status=code)

            # Validate property exists and belongs to company
            prop = (
                request.env["real.estate.property"].sudo().browse(data["property_id"])
            )
            if not prop.exists():
                return error_response(404, "Property not found")
            if company_ids is not None:
                if prop.company_id.id not in company_ids:
                    return error_response(404, "Property not found")

            # Validate company_id is accessible
            company = request.env["res.company"].sudo().browse(data["company_id"])
            if not company.exists() or not company.active:
                return error_response(404, "Company not found")
            if company_ids is not None and data["company_id"] not in company_ids:
                return error_response(403, "Access denied to specified company")

            # Validate agent belongs to same company (FR-023)
            if data.get("agent_id"):
                agent = request.env["real.estate.agent"].sudo().browse(data["agent_id"])
                if not agent.exists():
                    return error_response(404, "Agent not found")
                if agent.company_id.id != data["company_id"]:
                    resp, code = util_error(
                        "Agent does not belong to the specified company",
                        status_code=400,
                    )
                    return request.make_json_response(resp, status=code)

            # Prepare vals
            sale_vals = {
                "property_id": data["property_id"],
                "company_id": data["company_id"],
                "buyer_name": data["buyer_name"].strip(),
                "sale_date": data["sale_date"],
                "sale_price": data["sale_price"],
            }

            # Optional fields
            for field in ["buyer_phone", "buyer_email", "agent_id", "lead_id"]:
                if field in data and data[field] is not None:
                    sale_vals[field] = data[field]

            # Create (model's create() override handles property→sold + event emission)
            try:
                sale = request.env["real.estate.sale"].sudo().create(sale_vals)
            except ValidationError as ve:
                resp, code = util_error(str(ve), status_code=400)
                return request.make_json_response(resp, status=code)

            sale_data = self._serialize_sale(sale)
            links = build_hateoas_links("/api/v1/sales", sale.id, {"cancel": "/cancel"})

            resp, code = util_success(
                data=sale_data,
                message="Sale created successfully",
                links=links,
                status_code=201,
            )
            return request.make_json_response(resp, status=code)

        except ValidationError as e:
            _logger.warning(f"Validation error creating sale: {str(e)}")
            return error_response(400, str(e))
        except Exception as e:
            _logger.error(f"Error creating sale: {str(e)}", exc_info=True)
            return error_response(500, "Internal server error")

    # ========== GET SALE (FR-024) ==========

    @http.route(
        "/api/v1/sales/<int:sale_id>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def get_sale(self, sale_id, **kwargs):
        """Get sale by ID with property, agent, and lead info."""
        try:
            user = request.env.user
            company_ids = self._get_company_ids()

            sale = request.env["real.estate.sale"].sudo().browse(sale_id)
            if not sale.exists() or not sale.active:
                return error_response(404, "Sale not found")

            # Company isolation
            if company_ids is not None:
                if sale.company_id.id not in company_ids:
                    return error_response(404, "Sale not found")

            # Agent RBAC
            if self._is_agent_role(user):
                assigned_prop_ids = self._get_agent_property_ids(
                    user, company_ids or []
                )
                if sale.property_id.id not in assigned_prop_ids:
                    return error_response(404, "Sale not found")

            sale_data = self._serialize_sale(sale)

            # Enrich with related info
            if sale.lead_id:
                sale_data["lead"] = {
                    "id": sale.lead_id.id,
                    "name": (
                        sale.lead_id.name if hasattr(sale.lead_id, "name") else None
                    ),
                }

            links = build_hateoas_links("/api/v1/sales", sale.id, {"cancel": "/cancel"})
            resp, code = util_success(data=sale_data, links=links)
            return request.make_json_response(resp, status=code)

        except Exception as e:
            _logger.error(f"Error getting sale {sale_id}: {str(e)}", exc_info=True)
            return error_response(500, "Internal server error")

    # ========== UPDATE SALE (FR-025, FR-026) ==========

    @http.route(
        "/api/v1/sales/<int:sale_id>",
        type="http",
        auth="none",
        methods=["PUT"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def update_sale(self, sale_id, **kwargs):
        """Update sale (non-cancelled only). Supports reactivation via active=true (US5 / FR-007)."""
        try:
            company_ids = self._get_company_ids()

            # Browse with active_test=False to allow reactivation of archived records
            sale = (
                request.env["real.estate.sale"]
                .sudo()
                .with_context(active_test=False)
                .browse(sale_id)
            )
            if not sale.exists():
                return error_response(404, "Sale not found")

            # Company isolation
            if company_ids is not None:
                if sale.company_id.id not in company_ids:
                    return error_response(404, "Sale not found")

            # Parse body first (needed to check reactivation intent)
            try:
                data = json.loads(request.httprequest.data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return error_response(400, "Invalid JSON in request body")

            # If record is inactive and no reactivation requested, reject
            if not sale.active and data.get("active") is not True:
                return error_response(404, "Sale not found")

            # Cannot update cancelled sales (FR-026) unless reactivating
            if sale.status == "cancelled" and data.get("active") is not True:
                resp, code = util_error(
                    "Cannot update a cancelled sale", status_code=400
                )
                return request.make_json_response(resp, status=code)

            # Validate schema
            is_valid, errors = SchemaValidator.validate_request(
                data, SchemaValidator.SALE_UPDATE_SCHEMA
            )
            if not is_valid:
                resp, code = util_error(
                    "Validation failed", errors={"validation": errors}, status_code=400
                )
                return request.make_json_response(resp, status=code)

            # Validate email if provided
            if data.get("buyer_email") and not validate_email_format(
                data["buyer_email"]
            ):
                resp, code = util_error(
                    f"Invalid email format: {data['buyer_email']}", status_code=400
                )
                return request.make_json_response(resp, status=code)

            # Build update vals
            update_vals = {}
            for field in [
                "buyer_name",
                "buyer_phone",
                "buyer_email",
                "sale_date",
                "sale_price",
            ]:
                if field in data:
                    update_vals[field] = (
                        data[field].strip()
                        if isinstance(data[field], str)
                        else data[field]
                    )

            # Reactivation support (US5 / FR-007)
            if data.get("active") is True and not sale.active:
                update_vals["active"] = True
                update_vals["cancellation_date"] = False
                update_vals["cancellation_reason"] = False

            if not update_vals:
                resp, code = util_error("No fields to update", status_code=400)
                return request.make_json_response(resp, status=code)

            try:
                sale.write(update_vals)
            except ValidationError as ve:
                resp, code = util_error(str(ve), status_code=400)
                return request.make_json_response(resp, status=code)

            sale_data = self._serialize_sale(sale)
            links = build_hateoas_links("/api/v1/sales", sale.id, {"cancel": "/cancel"})

            resp, code = util_success(
                data=sale_data,
                message="Sale updated successfully",
                links=links,
            )
            return request.make_json_response(resp, status=code)

        except ValidationError as e:
            _logger.warning(f"Validation error updating sale {sale_id}: {str(e)}")
            return error_response(400, str(e))
        except Exception as e:
            _logger.error(f"Error updating sale {sale_id}: {str(e)}", exc_info=True)
            return error_response(500, "Internal server error")

    # ========== CANCEL SALE (FR-027, FR-029 — revert property status) ==========

    @http.route(
        "/api/v1/sales/<int:sale_id>/cancel",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def cancel_sale(self, sale_id, **kwargs):
        """Cancel a sale with reason and revert property status."""
        try:
            company_ids = self._get_company_ids()

            sale = request.env["real.estate.sale"].sudo().browse(sale_id)
            if not sale.exists() or not sale.active:
                return error_response(404, "Sale not found")

            # Company isolation
            if company_ids is not None:
                if sale.company_id.id not in company_ids:
                    return error_response(404, "Sale not found")

            # Already cancelled
            if sale.status == "cancelled":
                resp, code = util_error("Sale is already cancelled", status_code=400)
                return request.make_json_response(resp, status=code)

            # Parse body
            try:
                data = json.loads(request.httprequest.data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return error_response(400, "Invalid JSON in request body")

            # Validate schema
            is_valid, errors = SchemaValidator.validate_request(
                data, SchemaValidator.SALE_CANCEL_SCHEMA
            )
            if not is_valid:
                resp, code = util_error(
                    "Validation failed", errors={"validation": errors}, status_code=400
                )
                return request.make_json_response(resp, status=code)

            # Cancel using model method (handles property status revert)
            try:
                sale.action_cancel(data["reason"])
            except ValidationError as ve:
                resp, code = util_error(str(ve), status_code=400)
                return request.make_json_response(resp, status=code)

            sale_data = self._serialize_sale(sale)
            links = build_hateoas_links("/api/v1/sales", sale.id)

            resp, code = util_success(
                data=sale_data,
                message="Sale cancelled successfully",
                links=links,
            )
            return request.make_json_response(resp, status=code)

        except ValidationError as e:
            _logger.warning(f"Validation error cancelling sale {sale_id}: {str(e)}")
            return error_response(400, str(e))
        except Exception as e:
            _logger.error(f"Error cancelling sale {sale_id}: {str(e)}", exc_info=True)
            return error_response(500, "Internal server error")
