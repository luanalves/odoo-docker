# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime
from odoo import http
from odoo.http import request, Response
from odoo.exceptions import UserError, ValidationError
from .utils.auth import require_jwt
from .utils.response import error_response, success_response
from .utils.schema import SchemaValidator
from odoo.addons.thedevkitchen_apigateway.middleware import (
    require_session,
    require_company,
)

_logger = logging.getLogger(__name__)


class AgentApiController(http.Controller):
    # ==================== ASSIGNMENT ENDPOINTS ====================

    @http.route(
        "/api/v1/assignments",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def create_assignment(
        self, **kwargs
    ):  # noqa: C901 - legacy endpoint, keep behavior stable

        try:
            # Parse JSON body
            try:
                data = json.loads(request.httprequest.data)
            except json.JSONDecodeError:
                return error_response(400, "Invalid JSON in request body")

            # Validate against schema
            is_valid, errors = SchemaValidator.validate_assignment_create(data)
            if not is_valid:
                return error_response(400, "Validation failed", ", ".join(errors))

            agent_id = data.get("agent_id")
            property_id = data.get("property_id")
            responsibility_type = data.get("responsibility_type", "primary")
            notes = data.get("notes", "")

            # Validate agent and property exist
            Agent = request.env["real.estate.agent"].sudo()
            Property = request.env["real.estate.property"].sudo()

            agent = Agent.browse(agent_id)
            property_obj = Property.browse(property_id)

            if not agent.exists():
                return error_response(404, f"Agent with ID {agent_id} not found")
            if not property_obj.exists():
                return error_response(404, f"Property with ID {property_id} not found")

            # Check company access
            user = request.env.user
            if hasattr(user, "company_id") and user.company_id:
                if agent.company_id != user.company_id:
                    return error_response(
                        403, "Cannot assign agent from different company"
                    )
                if user.company_id != property_obj.company_id:
                    return error_response(
                        403, "Cannot assign to property from different company"
                    )

            # Create assignment
            Assignment = request.env["real.estate.agent.property.assignment"].sudo()
            assignment = Assignment.create(
                {
                    "agent_id": agent_id,
                    "property_id": property_id,
                    "responsibility_type": responsibility_type,
                    "notes": notes,
                }
            )

            return success_response(
                {
                    "message": "Assignment created successfully",
                    "assignment": {
                        "id": assignment.id,
                        "agent_id": assignment.agent_id.id,
                        "agent_name": assignment.agent_id.name,
                        "property_id": assignment.property_id.id,
                        "property_name": assignment.property_id.name,
                        "company_id": assignment.company_id.id,
                        "company_name": assignment.company_id.name,
                        "responsibility_type": assignment.responsibility_type,
                        "assignment_date": (
                            assignment.assignment_date.isoformat()
                            if assignment.assignment_date
                            else None
                        ),
                        "active": assignment.active,
                        "notes": assignment.notes,
                    },
                },
                status_code=201,
            )

        except ValidationError as e:
            return error_response(400, str(e))
        except Exception as e:
            _logger.exception("Error creating assignment")
            return error_response(500, f"Internal server error: {str(e)}")

    @http.route(
        "/api/v1/agents/<int:agent_id>/properties",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def get_agent_properties(self, agent_id, **kwargs):
        try:
            # Get agent
            Agent = request.env["real.estate.agent"].sudo()
            agent = Agent.browse(agent_id)

            if not agent.exists():
                return error_response(404, f"Agent with ID {agent_id} not found")

            # Check company access
            user = request.env.user
            if hasattr(user, "company_id") and user.company_id:
                if agent.company_id != user.company_id:
                    return error_response(
                        403, "Cannot access agent from different company"
                    )

            # Get active_only parameter
            active_only = kwargs.get("active_only", "true").lower() == "true"

            # Get assignments
            Assignment = request.env["real.estate.agent.property.assignment"].sudo()
            domain = [("agent_id", "=", agent_id)]
            if active_only:
                domain.append(("active", "=", True))

            assignments = Assignment.search(domain)

            # Build response
            properties_data = []
            for assignment in assignments:
                property_obj = assignment.property_id
                properties_data.append(
                    {
                        "assignment_id": assignment.id,
                        "property_id": property_obj.id,
                        "property_name": property_obj.name,
                        "property_reference": property_obj.reference_code,
                        "property_type": (
                            property_obj.property_type_id.name
                            if property_obj.property_type_id
                            else None
                        ),
                        "price": (
                            float(property_obj.price) if property_obj.price else 0.0
                        ),
                        "responsibility_type": assignment.responsibility_type,
                        "assignment_date": (
                            assignment.assignment_date.isoformat()
                            if assignment.assignment_date
                            else None
                        ),
                        "active": assignment.active,
                    }
                )

            return success_response(
                {
                    "agent_id": agent_id,
                    "agent_name": agent.name,
                    "total_assignments": len(properties_data),
                    "properties": properties_data,
                }
            )

        except Exception as e:
            _logger.exception(f"Error getting properties for agent {agent_id}")
            return error_response(500, f"Internal server error: {str(e)}")

    @http.route(
        "/api/v1/assignments/<int:assignment_id>",
        type="http",
        auth="none",
        methods=["DELETE"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def delete_assignment(self, assignment_id, **kwargs):
        try:
            # Get assignment
            Assignment = request.env["real.estate.agent.property.assignment"].sudo()
            assignment = Assignment.browse(assignment_id)

            if not assignment.exists():
                return error_response(
                    404, f"Assignment with ID {assignment_id} not found"
                )

            # Check company access
            user = request.env.user
            if hasattr(user, "company_id") and user.company_id:
                if assignment.company_id != user.company_id:
                    return error_response(
                        403, "Cannot delete assignment from different company"
                    )

            # Deactivate assignment
            if hasattr(assignment, "action_deactivate"):
                assignment.action_deactivate()
            else:
                assignment.write({"active": False})

            return success_response(
                {
                    "message": "Assignment deactivated successfully",
                    "assignment_id": assignment_id,
                    "active": assignment.active,
                }
            )

        except Exception as e:
            _logger.exception(f"Error deleting assignment {assignment_id}")
            return error_response(500, f"Internal server error: {str(e)}")

    @http.route(
        "/api/v1/assignments",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def list_assignments(
        self,
        page=1,
        page_size=20,
        agent_id=None,
        property_id=None,
        company_ids=None,
        active_only="true",
        **kwargs,
    ):  # noqa: C901 - legacy endpoint, keep behavior stable

        try:
            user = request.env.user

            # Convert pagination parameters
            try:
                page = int(page)
                page_size = min(int(page_size), 100)
            except (ValueError, TypeError):
                return error_response(400, "Invalid pagination parameters")

            if page < 1 or page_size < 1:
                return error_response(
                    400, "Page and page_size must be positive integers"
                )

            # Validate company_ids parameter (REQUIRED)
            if not company_ids:
                return error_response(400, "company_ids parameter is required")

            # Parse company_ids (can be comma-separated: "1,2,3")
            try:
                requested_company_ids = [
                    int(cid.strip()) for cid in company_ids.split(",")
                ]
            except ValueError:
                return error_response(
                    400,
                    'Invalid company_ids format. Use comma-separated integers (e.g., "1,2,3")',
                )

            # Validate user has access to all requested companies (multi-tenancy security)
            if request.user_company_ids:  # Not admin
                unauthorized_companies = [
                    cid
                    for cid in requested_company_ids
                    if cid not in request.user_company_ids
                ]
                if unauthorized_companies:
                    return error_response(
                        403,
                        f"Access denied to company IDs: {unauthorized_companies}. You can only access companies: {request.user_company_ids}",
                    )

            # Build base domain
            domain = []

            # Active filter
            if active_only.lower() == "true":
                domain.append(("active", "=", True))

            # Company filter using validated company_ids (REQUIRED)
            domain.append(("company_id", "in", requested_company_ids))

            # RBAC filter (ADR-019)
            is_admin = user.has_group("base.group_system")
            is_manager = user.has_group("quicksol_estate.group_real_estate_manager")
            is_agent = user.has_group("quicksol_estate.group_real_estate_agent")

            if not is_admin:
                # Agent: only own assignments
                if is_agent and not is_manager:
                    agent_record = request.env["real.estate.agent"].search(
                        [("user_id", "=", user.id)], limit=1
                    )

                    if agent_record:
                        domain.append(("agent_id", "=", agent_record.id))
                    else:
                        # Agent without agent record sees nothing
                        domain.append(("id", "=", False))

            # Optional filters
            if agent_id:
                try:
                    domain.append(("agent_id", "=", int(agent_id)))
                except (ValueError, TypeError):
                    return error_response(400, "Invalid agent_id")

            if property_id:
                try:
                    domain.append(("property_id", "=", int(property_id)))
                except (ValueError, TypeError):
                    return error_response(400, "Invalid property_id")

            # Use sudo() because company access was already validated above
            # ir.rule fails with legacy ir.rule reference
            Assignment = request.env["real.estate.agent.property.assignment"].sudo()

            # Count total
            total = Assignment.search_count(domain)

            # Get paginated results
            offset = (page - 1) * page_size
            assignments = Assignment.search(
                domain,
                limit=page_size,
                offset=offset,
                order="assignment_date DESC, id DESC",
            )

            # Serialize assignments
            assignment_list = []
            for assignment in assignments:
                assignment_data = {
                    "id": assignment.id,
                    "agent": (
                        {
                            "id": assignment.agent_id.id,
                            "name": assignment.agent_id.name,
                            "creci": assignment.agent_id.creci,
                        }
                        if assignment.agent_id
                        else None
                    ),
                    "property": (
                        {
                            "id": assignment.property_id.id,
                            "name": assignment.property_id.name,
                            "city": assignment.property_id.city,
                            "price": assignment.property_id.price,
                        }
                        if assignment.property_id
                        else None
                    ),
                    "company": (
                        {
                            "id": assignment.company_id.id,
                            "name": assignment.company_id.name,
                        }
                        if assignment.company_id
                        else None
                    ),
                    "responsibility_type": assignment.responsibility_type,
                    "notes": assignment.notes or "",
                    "assignment_date": (
                        assignment.assignment_date.isoformat()
                        if assignment.assignment_date
                        else None
                    ),
                    "active": assignment.active,
                }

                # HATEOAS links (ADR-007)
                assignment_data["links"] = [
                    {
                        "href": f"/api/v1/assignments/{assignment.id}",
                        "rel": "self",
                        "type": "GET",
                        "title": "Get assignment details",
                    }
                ]

                assignment_list.append(assignment_data)

            # Build pagination links
            base_url = "/api/v1/assignments"

            # Preserve query parameters
            company_ids_str = ",".join(str(cid) for cid in requested_company_ids)
            query_params = [f"company_ids={company_ids_str}"]
            for key in ["agent_id", "property_id", "active_only"]:
                if key in kwargs:
                    query_params.append(f"{key}={kwargs[key]}")

            query_string = "&".join(query_params)
            if query_string:
                base_url += f"?{query_string}"
                separator = "&"
            else:
                separator = "?"

            links = []

            # Self link
            links.append(
                {
                    "href": f"{base_url}{separator}page={page}&page_size={page_size}",
                    "rel": "self",
                    "type": "GET",
                }
            )

            # Previous page
            if page > 1:
                links.append(
                    {
                        "href": f"{base_url}{separator}page={page-1}&page_size={page_size}",
                        "rel": "prev",
                        "type": "GET",
                    }
                )

            # Next page
            total_pages = (total + page_size - 1) // page_size
            if page < total_pages:
                links.append(
                    {
                        "href": f"{base_url}{separator}page={page+1}&page_size={page_size}",
                        "rel": "next",
                        "type": "GET",
                    }
                )

            from ..utils.responses import paginated_response

            response, status = paginated_response(
                items=assignment_list,
                total=total,
                page=page,
                page_size=page_size,
                links=links,
            )

            return request.make_json_response(response, status=status)

        except Exception as e:
            _logger.error(f"Error listing assignments: {str(e)}", exc_info=True)
            return error_response(500, "Internal server error")

    @http.route(
        "/api/v1/assignments/<int:assignment_id>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def get_assignment(self, assignment_id, **kwargs):

        try:
            user = request.env.user

            # Use sudo() because ir.rule fails with legacy ir.rule reference
            # RBAC is enforced via domain filters below
            Assignment = request.env["real.estate.agent.property.assignment"].sudo()

            # Build domain with multi-tenancy filter
            domain = [("id", "=", assignment_id)]

            # RBAC filter (ADR-019)
            is_admin = user.has_group("base.group_system")
            is_manager = user.has_group("quicksol_estate.group_real_estate_manager")
            is_agent = user.has_group("quicksol_estate.group_real_estate_agent")

            if not is_admin:
                # Multi-tenancy
                domain.append(("company_id", "in", user.company_ids.ids))

                # Agent: only own assignments
                if is_agent and not is_manager:
                    agent_record = request.env["real.estate.agent"].search(
                        [("user_id", "=", user.id)], limit=1
                    )

                    if agent_record:
                        domain.append(("agent_id", "=", agent_record.id))
                    else:
                        # Agent without agent record sees nothing
                        return error_response(404, "Assignment not found")

            assignment = Assignment.search(domain, limit=1)

            if not assignment:
                return error_response(404, "Assignment not found")

            # Serialize assignment
            assignment_data = {
                "id": assignment.id,
                "agent": (
                    {
                        "id": assignment.agent_id.id,
                        "name": assignment.agent_id.name,
                        "creci": assignment.agent_id.creci,
                        "email": assignment.agent_id.email,
                        "phone": assignment.agent_id.phone,
                    }
                    if assignment.agent_id
                    else None
                ),
                "property": (
                    {
                        "id": assignment.property_id.id,
                        "name": assignment.property_id.name,
                        "property_type": (
                            assignment.property_id.property_type_id.name
                            if assignment.property_id.property_type_id
                            else None
                        ),
                        "city": assignment.property_id.city,
                        "state": (
                            assignment.property_id.state_id.name
                            if assignment.property_id.state_id
                            else None
                        ),
                        "price": assignment.property_id.price,
                        "area": assignment.property_id.area,
                    }
                    if assignment.property_id
                    else None
                ),
                "company": (
                    {
                        "id": assignment.company_id.id,
                        "name": assignment.company_id.name,
                        "cnpj": assignment.company_id.cnpj,
                    }
                    if assignment.company_id
                    else None
                ),
                "responsibility_type": assignment.responsibility_type,
                "assignment_date": (
                    assignment.assignment_date.isoformat()
                    if assignment.assignment_date
                    else None
                ),
                "notes": assignment.notes or "",
                "active": assignment.active,
                "create_date": (
                    assignment.create_date.isoformat()
                    if assignment.create_date
                    else None
                ),
                "write_date": (
                    assignment.write_date.isoformat() if assignment.write_date else None
                ),
            }

            # HATEOAS links (ADR-007)
            assignment_data["links"] = [
                {
                    "href": f"/api/v1/assignments/{assignment.id}",
                    "rel": "self",
                    "type": "GET",
                    "title": "Get assignment details",
                },
                {
                    "href": f"/api/v1/assignments/{assignment.id}",
                    "rel": "update",
                    "type": "PATCH",
                    "title": "Update assignment",
                },
                {
                    "href": f"/api/v1/assignments/{assignment.id}",
                    "rel": "delete",
                    "type": "DELETE",
                    "title": "Deactivate assignment",
                },
                {
                    "href": "/api/v1/assignments",
                    "rel": "collection",
                    "type": "GET",
                    "title": "List all assignments",
                },
            ]

            if assignment.agent_id:
                assignment_data["links"].append(
                    {
                        "href": f"/api/v1/agents/{assignment.agent_id.id}",
                        "rel": "agent",
                        "type": "GET",
                        "title": "Get agent details",
                    }
                )

            if assignment.property_id:
                assignment_data["links"].append(
                    {
                        "href": f"/api/v1/properties/{assignment.property_id.id}",
                        "rel": "property",
                        "type": "GET",
                        "title": "Get property details",
                    }
                )

            if assignment.company_id:
                assignment_data["links"].append(
                    {
                        "href": f"/api/v1/companies/{assignment.company_id.id}",
                        "rel": "company",
                        "type": "GET",
                        "title": "Get company details",
                    }
                )

            return success_response(assignment_data)

        except Exception as e:
            _logger.error(
                f"Error getting assignment {assignment_id}: {str(e)}", exc_info=True
            )
            return error_response(500, "Internal server error")

    @http.route(
        "/api/v1/assignments/<int:assignment_id>",
        type="http",
        auth="none",
        methods=["PATCH"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def update_assignment(
        self, assignment_id, **kwargs
    ):  # noqa: C901 - legacy endpoint, keep behavior stable

        try:
            user = request.env.user

            # Parse request body
            try:
                data = json.loads(request.httprequest.data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return error_response(400, "Invalid JSON in request body")

            # Use sudo() because ir.rule fails with legacy ir.rule reference
            # RBAC is enforced via domain filters below
            Assignment = request.env["real.estate.agent.property.assignment"].sudo()

            # Build domain with multi-tenancy filter
            domain = [("id", "=", assignment_id)]

            # RBAC filter
            is_admin = user.has_group("base.group_system")
            is_manager = user.has_group("quicksol_estate.group_real_estate_manager")
            is_owner = user.has_group("quicksol_estate.group_real_estate_owner")
            is_agent = user.has_group("quicksol_estate.group_real_estate_agent")

            if not is_admin:
                # Multi-tenancy
                domain.append(("company_id", "in", user.company_ids.ids))

                # Agent: only own assignments
                if is_agent and not (is_manager or is_owner):
                    agent_record = request.env["real.estate.agent"].search(
                        [("user_id", "=", user.id)], limit=1
                    )

                    if agent_record:
                        domain.append(("agent_id", "=", agent_record.id))
                    else:
                        return error_response(404, "Assignment not found")

            assignment = Assignment.search(domain, limit=1)

            if not assignment:
                return error_response(404, "Assignment not found")

            # Build update values
            update_vals = {}

            # Validate immutable fields
            immutable_fields = ["agent_id", "property_id", "company_id"]
            for field in immutable_fields:
                if field in data:
                    return error_response(
                        400,
                        f"Field {field} is immutable. Delete and recreate assignment instead.",
                    )

            # responsibility_type (Manager/Owner/Admin only)
            if "responsibility_type" in data:
                if not (is_admin or is_manager or is_owner):
                    return error_response(
                        403, "Only Managers or Owners can update responsibility_type"
                    )

                if data["responsibility_type"] not in [
                    "primary",
                    "secondary",
                    "support",
                ]:
                    return error_response(
                        400,
                        "Invalid responsibility_type. Must be: primary, secondary, support",
                    )

                update_vals["responsibility_type"] = data["responsibility_type"]

            # notes (all authenticated users can update)
            if "notes" in data:
                update_vals["notes"] = data["notes"]

            if not update_vals:
                return error_response(400, "No valid fields to update")

            # Update assignment
            assignment.write(update_vals)

            # Return updated assignment
            assignment_data = {
                "id": assignment.id,
                "agent": (
                    {"id": assignment.agent_id.id, "name": assignment.agent_id.name}
                    if assignment.agent_id
                    else None
                ),
                "property": (
                    {
                        "id": assignment.property_id.id,
                        "name": assignment.property_id.name,
                    }
                    if assignment.property_id
                    else None
                ),
                "company": (
                    {"id": assignment.company_id.id, "name": assignment.company_id.name}
                    if assignment.company_id
                    else None
                ),
                "responsibility_type": assignment.responsibility_type,
                "assignment_date": (
                    assignment.assignment_date.isoformat()
                    if assignment.assignment_date
                    else None
                ),
                "notes": assignment.notes or "",
                "active": assignment.active,
                "write_date": (
                    assignment.write_date.isoformat() if assignment.write_date else None
                ),
            }

            # HATEOAS links
            assignment_data["links"] = [
                {
                    "href": f"/api/v1/assignments/{assignment.id}",
                    "rel": "self",
                    "type": "GET",
                    "title": "Get assignment details",
                }
            ]

            return success_response(assignment_data)

        except Exception as e:
            _logger.error(
                f"Error updating assignment {assignment_id}: {str(e)}", exc_info=True
            )
            return error_response(500, "Internal server error")

    # ==================== COMMISSION RULE ENDPOINTS (US4) ====================

    @http.route(
        "/api/v1/agents/<int:agent_id>/commission-rules",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def create_commission_rule(self, agent_id, **kwargs):

        try:
            # Parse request body
            body = json.loads(request.httprequest.data.decode("utf-8"))

            # Validate agent exists and belongs to user's company
            agent = request.env["real.estate.agent"].sudo().browse(agent_id)
            if not agent.exists():
                return error_response(404, f"Agent {agent_id} not found")

            # Company isolation check
            user = request.env.user
            if hasattr(user, "company_ids"):
                if agent.company_id.id not in user.company_ids.ids:
                    return error_response(
                        403,
                        "Cannot create commission rule for agent in different company",
                    )

            # Validate required fields
            required_fields = ["transaction_type", "structure_type", "valid_from"]
            missing = [f for f in required_fields if f not in body]
            if missing:
                return error_response(
                    400, f'Missing required fields: {", ".join(missing)}'
                )

            # Prepare rule data
            rule_data = {
                "agent_id": agent_id,
                "company_id": agent.company_id.id,
                "transaction_type": body["transaction_type"],
                "structure_type": body["structure_type"],
                "percentage": body.get("percentage", 0.0),
                "fixed_amount": body.get("fixed_amount", 0.0),
                "min_value": body.get("min_value", 0.0),
                "max_value": body.get("max_value", 999999999.99),
                "valid_from": body["valid_from"],
                "valid_until": body.get("valid_until"),
            }

            # Create commission rule
            rule = request.env["real.estate.commission.rule"].sudo().create(rule_data)

            # Return created rule
            return success_response(
                {
                    "id": rule.id,
                    "agent_id": rule.agent_id.id,
                    "agent_name": rule.agent_id.name,
                    "company_id": rule.company_id.id,
                    "company_name": rule.company_id.name,
                    "transaction_type": rule.transaction_type,
                    "structure_type": rule.structure_type,
                    "percentage": rule.percentage,
                    "fixed_amount": rule.fixed_amount,
                    "min_value": rule.min_value,
                    "max_value": rule.max_value,
                    "valid_from": str(rule.valid_from),
                    "valid_until": str(rule.valid_until) if rule.valid_until else None,
                    "is_active": rule.is_active,
                    "active": rule.active,
                },
                status_code=201,
            )

        except json.JSONDecodeError:
            return error_response(400, "Invalid JSON in request body")
        except ValidationError as e:
            return error_response(400, str(e))
        except Exception as e:
            _logger.exception(f"Error creating commission rule for agent {agent_id}")
            return error_response(500, f"Internal server error: {str(e)}")

    @http.route(
        "/api/v1/agents/<int:agent_id>/commission-rules",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def list_commission_rules(self, agent_id, **kwargs):

        try:
            # Validate agent exists and belongs to user's company
            agent = request.env["real.estate.agent"].sudo().browse(agent_id)
            if not agent.exists():
                return error_response(404, f"Agent {agent_id} not found")

            # Company isolation check
            user = request.env.user
            if hasattr(user, "company_ids"):
                if agent.company_id.id not in user.company_ids.ids:
                    return error_response(
                        403,
                        "Cannot access commission rules for agent in different company",
                    )

            # Build search domain
            domain = [("agent_id", "=", agent_id)]

            # Filter by active status
            active_only = kwargs.get("active_only", "false").lower() == "true"
            if active_only:
                domain.append(("active", "=", True))

            # Search commission rules
            rules = (
                request.env["real.estate.commission.rule"]
                .sudo()
                .search(domain, order="valid_from desc")
            )

            # Serialize rules
            rules_data = []
            for rule in rules:
                rules_data.append(
                    {
                        "id": rule.id,
                        "agent_id": rule.agent_id.id,
                        "agent_name": rule.agent_id.name,
                        "company_id": rule.company_id.id,
                        "transaction_type": rule.transaction_type,
                        "structure_type": rule.structure_type,
                        "percentage": rule.percentage,
                        "fixed_amount": rule.fixed_amount,
                        "min_value": rule.min_value,
                        "max_value": rule.max_value,
                        "valid_from": str(rule.valid_from),
                        "valid_until": (
                            str(rule.valid_until) if rule.valid_until else None
                        ),
                        "is_active": rule.is_active,
                        "active": rule.active,
                        "transaction_count": rule.transaction_count,
                    }
                )

            return success_response(
                {
                    "data": rules_data,
                    "count": len(rules_data),
                }
            )

        except Exception as e:
            _logger.exception(f"Error listing commission rules for agent {agent_id}")
            return error_response(500, f"Internal server error: {str(e)}")

    @http.route(
        "/api/v1/commission-rules/<int:rule_id>",
        type="http",
        auth="none",
        methods=["PUT"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def update_commission_rule(
        self, rule_id, **kwargs
    ):  # noqa: C901 - legacy endpoint, keep behavior stable

        try:
            # Parse request body
            body = json.loads(request.httprequest.data.decode("utf-8"))

            # Find commission rule
            rule = request.env["real.estate.commission.rule"].sudo().browse(rule_id)
            if not rule.exists():
                return error_response(404, f"Commission rule {rule_id} not found")

            # Company isolation check
            user = request.env.user
            if hasattr(user, "company_ids"):
                if rule.company_id.id not in user.company_ids.ids:
                    return error_response(
                        403, "Cannot update commission rule from different company"
                    )

            # Only allow updating valid_until and active
            update_data = {}
            if "valid_until" in body:
                update_data["valid_until"] = body["valid_until"]
            if "active" in body:
                update_data["active"] = body["active"]

            if not update_data:
                return error_response(
                    400,
                    "No valid fields to update (only valid_until and active allowed)",
                )

            # Update rule
            rule.write(update_data)

            return success_response(
                {
                    "id": rule.id,
                    "valid_until": str(rule.valid_until) if rule.valid_until else None,
                    "active": rule.active,
                    "is_active": rule.is_active,
                }
            )

        except json.JSONDecodeError:
            return error_response(400, "Invalid JSON in request body")
        except ValidationError as e:
            return error_response(400, str(e))
        except Exception as e:
            _logger.exception(f"Error updating commission rule {rule_id}")
            return error_response(500, f"Internal server error: {str(e)}")

    @http.route(
        "/api/v1/commission-transactions",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def create_commission_transaction(
        self, **kwargs
    ):  # noqa: C901 - legacy endpoint, keep behavior stable

        try:
            # Parse request body
            body = json.loads(request.httprequest.data.decode("utf-8"))

            # Validate required fields
            required_fields = [
                "agent_id",
                "company_id",
                "transaction_type",
                "transaction_amount",
            ]
            missing = [f for f in required_fields if f not in body]
            if missing:
                return error_response(
                    400, f'Missing required fields: {", ".join(missing)}'
                )

            # Validate agent exists
            agent_id = body["agent_id"]
            company_id = body["company_id"]
            agent = request.env["real.estate.agent"].sudo().browse(agent_id)
            if not agent.exists():
                return error_response(404, f"Agent {agent_id} not found")

            # Validate agent belongs to the specified company
            agent_company_id = agent.company_id.id if agent.company_id else None
            if company_id != agent_company_id:
                return error_response(
                    400, f"Agent {agent_id} does not belong to company {company_id}"
                )

            # Company isolation check - user must have access to the company
            user = request.env.user
            if hasattr(user, "company_ids"):
                if company_id not in user.company_ids.ids:
                    return error_response(403, "You do not have access to this company")

            # Use CommissionService to create transaction
            from ..services.commission_service import CommissionService

            commission_service = CommissionService(request.env)

            transaction = commission_service.create_commission_transaction(
                agent_id=agent_id,
                company_id=company_id,
                transaction_type=body["transaction_type"],
                transaction_amount=body["transaction_amount"],
                transaction_date=body.get("transaction_date"),
                transaction_reference=body.get("transaction_reference"),
            )

            # Return created transaction
            return success_response(
                {
                    "id": transaction.id,
                    "agent_id": transaction.agent_id.id,
                    "agent_name": transaction.agent_id.name,
                    "company_id": transaction.company_id.id,
                    "transaction_type": transaction.transaction_type,
                    "transaction_amount": transaction.transaction_amount,
                    "commission_amount": transaction.commission_amount,
                    "rule_id": transaction.rule_id.id,
                    "rule_percentage": transaction.rule_percentage,
                    "rule_fixed_amount": transaction.rule_fixed_amount,
                    "rule_structure_type": transaction.rule_structure_type,
                    "payment_status": transaction.payment_status,
                    "transaction_date": str(transaction.transaction_date),
                    "transaction_reference": transaction.transaction_reference,
                    "calculated_at": transaction.calculated_at.isoformat(),
                },
                status_code=201,
            )

        except json.JSONDecodeError:
            return error_response(400, "Invalid JSON in request body")
        except ValidationError as e:
            return error_response(400, str(e))
        except UserError as e:
            return error_response(400, str(e))
        except Exception as e:
            _logger.exception("Error creating commission transaction")
            return error_response(500, f"Internal server error: {str(e)}")

    @http.route(
        "/api/v1/agents/<int:agent_id>/performance",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def get_agent_performance(
        self, agent_id, **kwargs
    ):  # noqa: C901 - legacy endpoint, keep behavior stable

        try:
            # Parse query parameters
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")

            # Validate date formats
            date_from = None
            date_to = None

            if start_date:
                try:
                    date_from = datetime.strptime(start_date, "%Y-%m-%d").date()
                except ValueError:
                    return error_response(
                        400, f"Invalid start_date format: {start_date}. Use YYYY-MM-DD"
                    )

            if end_date:
                try:
                    date_to = datetime.strptime(end_date, "%Y-%m-%d").date()
                except ValueError:
                    return error_response(
                        400, f"Invalid end_date format: {end_date}. Use YYYY-MM-DD"
                    )

            # Validate date range
            if date_from and date_to and date_from > date_to:
                return error_response(400, "start_date cannot be after end_date")

            # Get performance data from service
            from odoo.addons.quicksol_estate.services.performance_service import (
                PerformanceService,
            )

            service = PerformanceService(request.env)

            performance_data = service.get_agent_performance(
                agent_id=agent_id, date_from=date_from, date_to=date_to
            )

            return success_response(performance_data)

        except UserError as e:
            # Handle not found / access denied from service
            error_msg = str(e)
            if "not found" in error_msg.lower():
                return error_response(404, error_msg)
            elif (
                "access denied" in error_msg.lower()
                or "different company" in error_msg.lower()
            ):
                return error_response(403, error_msg)
            else:
                return error_response(400, error_msg)
        except ValidationError as e:
            return error_response(400, str(e))
        except Exception as e:
            _logger.exception("Error getting agent performance")
            return error_response(500, f"Internal server error: {str(e)}")

    @http.route(
        "/api/v1/agents/ranking",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def get_agents_ranking(
        self, **kwargs
    ):  # noqa: C901 - legacy endpoint, keep behavior stable
        try:
            # Parse query parameters
            company_id = kwargs.get("company_id")
            metric = kwargs.get("metric", "total_commissions")
            limit = kwargs.get("limit", "10")
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")

            # Validate company_id (required)
            if not company_id:
                return error_response(400, "Missing required parameter: company_id")

            try:
                company_id = int(company_id)
            except ValueError:
                return error_response(
                    400, f"Invalid company_id: {company_id}. Must be an integer"
                )

            # Validate limit
            try:
                limit = int(limit)
                if limit < 1:
                    return error_response(400, "limit must be at least 1")
                if limit > 100:
                    limit = 100  # Cap at 100
            except ValueError:
                return error_response(
                    400, f"Invalid limit: {limit}. Must be an integer"
                )

            # Validate metric
            valid_metrics = ["total_commissions", "total_sales", "average_commission"]
            if metric not in valid_metrics:
                return error_response(
                    400,
                    f'Invalid metric: {metric}. Must be one of {", ".join(valid_metrics)}',
                )

            # Validate date formats
            date_from = None
            date_to = None

            if start_date:
                try:
                    date_from = datetime.strptime(start_date, "%Y-%m-%d").date()
                except ValueError:
                    return error_response(
                        400, f"Invalid start_date format: {start_date}. Use YYYY-MM-DD"
                    )

            if end_date:
                try:
                    date_to = datetime.strptime(end_date, "%Y-%m-%d").date()
                except ValueError:
                    return error_response(
                        400, f"Invalid end_date format: {end_date}. Use YYYY-MM-DD"
                    )

            # Validate date range
            if date_from and date_to and date_from > date_to:
                return error_response(400, "start_date cannot be after end_date")

            # Get ranking data from service
            from odoo.addons.quicksol_estate.services.performance_service import (
                PerformanceService,
            )

            service = PerformanceService(request.env)

            ranking_data = service.get_top_agents_ranking(
                company_id=company_id,
                metric=metric,
                limit=limit,
                date_from=date_from,
                date_to=date_to,
            )

            return success_response(ranking_data)

        except UserError as e:
            # Handle not found / access denied from service
            error_msg = str(e)
            if "not found" in error_msg.lower():
                return error_response(404, error_msg)
            elif (
                "access denied" in error_msg.lower()
                or "different company" in error_msg.lower()
            ):
                return error_response(403, error_msg)
            else:
                return error_response(400, error_msg)
        except ValidationError as e:
            return error_response(400, str(e))
        except Exception as e:
            _logger.exception("Error getting agents ranking")
            return error_response(500, f"Internal server error: {str(e)}")
