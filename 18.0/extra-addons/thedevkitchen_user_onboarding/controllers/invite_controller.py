# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request, Response
from odoo.exceptions import UserError, ValidationError
from odoo.addons.thedevkitchen_apigateway.middleware import (
    require_jwt,
    require_session,
    require_company,
)
from odoo.addons.quicksol_estate.controllers.utils.schema import SchemaValidator
from odoo.addons.quicksol_estate.services.role_resolver import resolve_role
from odoo.addons.thedevkitchen_observability.services.tracer import trace_http_request
from ..services.invite_service import InviteService
from ..services.token_service import PasswordTokenService

_logger = logging.getLogger(__name__)


class InviteController(http.Controller):
    @http.route(
        "/api/v1/users/invite",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    @trace_http_request
    def invite_user(self, **kwargs):
        try:
            # Parse request body
            try:
                data = json.loads(request.httprequest.data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._error_response(
                    400, "validation_error", "Invalid JSON in request body"
                )

            # Feature 010: Unified profile flow requires ONLY profile_id + session_id
            profile_id = data.get("profile_id")

            if not profile_id:
                return self._error_response(
                    400,
                    "validation_error",
                    "Missing required field: profile_id",
                    {"missing_fields": ["profile_id"]},
                )

            # Load profile record (optimized: search instead of browse+exists)
            ProfileModel = request.env["thedevkitchen.estate.profile"]
            profile_record = ProfileModel.sudo().search([("id", "=", int(profile_id))], limit=1)

            if not profile_record:
                return self._error_response(
                    404, "not_found", f"Profile {profile_id} not found"
                )

            # Check if profile already has a user (via partner_id)
            if profile_record.partner_id:
                existing_user = (
                    request.env["res.users"]
                    .sudo()
                    .search([("partner_id", "=", profile_record.partner_id.id)], limit=1)
                )
                if existing_user:
                    return self._error_response(
                        409,
                        "conflict",
                        f"Profile {profile_id} already has a linked user account",
                        {"user_id": existing_user.id},
                    )

            # Extract company and profile data
            company = profile_record.company_id
            profile_type = profile_record.profile_type_id.code
            email = profile_record.email

            # Feature 026: read optional 'agent' object, validate BEFORE any res.users is created
            agent_payload = data.get("agent")
            if profile_type == "agent" and agent_payload:
                is_valid, errors = SchemaValidator.validate_agent_invite(agent_payload)
                if not is_valid:
                    return self._error_response(
                        400, "validation_error", ", ".join(errors)
                    )

            # Get authenticated user
            current_user = request.env.user

            # Initialize services
            invite_service = InviteService(request.env)
            token_service = PasswordTokenService(request.env)

            # Check authorization
            try:
                invite_service.check_authorization(current_user, profile_type)
            except UserError as e:
                _logger.warning(f"[INVITE] Authorization denied: {e}")
                return self._error_response(403, "forbidden", str(e))

            # Feature 010: Create user from profile (unified flow - no dual records)
            try:
                user = invite_service.create_user_from_profile(
                    profile_record=profile_record,
                    created_by=current_user
                )
            except ValidationError as e:
                if "already exists" in str(e):
                    field = "cpf" if "CPF" in str(e) else "email"
                    return self._error_response(
                        409, "conflict", str(e), {"field": field}
                    )
                return self._error_response(400, "validation_error", str(e))

            # Feature 026: link (or, defensively, create) real.estate.agent atomically,
            # linked to BOTH profile and login (FR2.1, FR2.1b).
            # Upsert semantics: profile_api.py (Feature 010) already auto-creates a
            # real.estate.agent (without user_id) whenever the profile is type 'agent' --
            # a blind create() here would collide on UNIQUE(cpf, company_id).
            agent_id = None
            if profile_type == "agent":
                allowed_agent_keys = {
                    "name", "cpf", "email", "phone", "mobile",
                    "creci", "hire_date", "bank_name", "bank_account", "pix_key",
                }
                explicit_fields = {
                    k: v for k, v in (agent_payload or {}).items()
                    if k in allowed_agent_keys and v is not None
                }
                Agent = request.env["real.estate.agent"].sudo()
                existing_agent = Agent.search(
                    [("profile_id", "=", profile_record.id)], limit=1
                )
                try:
                    if existing_agent:
                        existing_agent.write({"user_id": user.id, **explicit_fields})
                        agent_record = existing_agent
                    else:
                        agent_record = Agent.create({
                            "profile_id": profile_record.id,
                            "user_id": user.id,
                            **explicit_fields,
                        })
                except ValidationError as e:
                    return self._error_response(409, "conflict", str(e))
                agent_id = agent_record.id

            # Generate invite token
            raw_token, token_record = token_service.generate_token(
                user=user, token_type="invite", company=company, created_by=current_user
            )

            # Get settings for TTL and frontend URL
            settings = request.env["thedevkitchen.email.link.settings"].get_settings()

            # Send invite email
            email_sent = invite_service.send_invite_email(
                user=user,
                raw_token=raw_token,
                expires_hours=settings.invite_link_ttl_hours,
                frontend_base_url=settings.frontend_base_url,
            )

            # Build response data (Feature 010: no dual records, just user + profile link)
            response_data = {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "document": profile_record.document,
                "profile": profile_type,
                "profile_id": profile_id,
                "signup_pending": user.signup_pending,
                "invite_sent_at": (
                    token_record.create_date.isoformat()
                    if token_record.create_date
                    else None
                ),
                "invite_expires_at": (
                    token_record.expires_at.isoformat()
                    if token_record.expires_at
                    else None
                ),
            }

            # Add email status if failed
            if not email_sent:
                response_data["email_status"] = "failed"

            # Feature 026: include agent_id when a real.estate.agent was linked/created
            if agent_id:
                response_data["agent_id"] = agent_id

            # Build HATEOAS links (as dict for easier access in tests)
            links = {
                "self": f"/api/v1/users/{user.id}",
                "resend_invite": f"/api/v1/users/{user.id}/resend-invite",
                "collection": "/api/v1/users",
                "profile": f"/api/v1/profiles/{profile_id}",
            }

            # Feature 026: HATEOAS link to the linked/created agent record
            if agent_id:
                links["agent"] = f"/api/v1/agents/{agent_id}"

            return self._success_response(
                201,
                response_data,
                f"User invited successfully. Email sent to {email}",
                links,
            )

        except Exception as e:
            _logger.exception("[INVITE ERROR] Unexpected error in invite_user")
            return self._error_response(
                500, "internal_error", f"An unexpected error occurred: {str(e)}"
            )

    # Helper methods

    def _success_response(self, status_code, data, message, links=None):
        """Build success response"""
        response_body = {
            "success": True,
            "data": data,
            "message": message,
        }
        if links:
            response_body["links"] = links

        return Response(
            json.dumps(response_body, default=str),
            status=status_code,
            content_type="application/json",
        )

    def _error_response(self, status_code, error_type, message, details=None):
        """Build error response"""
        response_body = {
            "success": False,
            "error": error_type,
            "message": message,
        }
        if details:
            response_body["details"] = details

        return Response(
            json.dumps(response_body),
            status=status_code,
            content_type="application/json",
        )

    @http.route(
        "/api/v1/users/resend-invite",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    @trace_http_request
    def resend_invite(self, **kwargs):
        try:
            # Parse request body
            try:
                data = json.loads(request.httprequest.data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._error_response(
                    400, "validation_error", "Invalid JSON in request body"
                )

            # Get user_id from body
            user_id = data.get("user_id")

            if not user_id:
                return self._error_response(
                    400,
                    "validation_error",
                    "Missing required field: user_id",
                    {"missing_fields": ["user_id"]},
                )

            try:
                user_id = int(user_id)
            except (TypeError, ValueError):
                return self._error_response(
                    400, "validation_error", "Invalid user_id: must be an integer"
                )

            # Context validated by decorators:
            # - @require_session sets request.env user
            # - @require_company enforces company access
            requester = request.env.user
            company_id = request.httprequest.headers.get("X-Company-ID")

            if not requester or not requester.id or not company_id:
                return self._error_response(
                    401, "ERR_UNAUTHORIZED", "Missing session context"
                )

            try:
                company_id = int(company_id)
            except (TypeError, ValueError):
                return self._error_response(
                    400, "validation_error", "Invalid X-Company-ID header"
                )

            # Get user record
            user = (
                request.env["res.users"]
                .sudo()
                .search(
                    [("id", "=", user_id), ("company_ids", "in", [company_id])],
                    limit=1,
                )
            )

            if not user:
                return self._error_response(
                    404,
                    "ERR_NOT_FOUND",
                    f"User with ID {user_id} not found in your company",
                )

            # Check if user already active
            if not user.signup_pending:
                return self._error_response(
                    400,
                    "ERR_USER_ALREADY_ACTIVE",
                    "User has already set their password. Use forgot-password flow instead.",
                    details={
                        "user_id": user_id,
                        "suggestion": "Use POST /api/v1/auth/forgot-password",
                    },
                )

            # Check authorization using InviteService
            invite_service = InviteService(request.env)

            # Determine target profile from user's groups
            profile = self._get_user_profile(user)

            try:
                invite_service.check_authorization(requester, profile)
            except UserError as e:
                return self._error_response(403, "ERR_FORBIDDEN", str(e))

            # Invalidate previous invite tokens
            token_service = PasswordTokenService(request.env)
            token_service.invalidate_previous_tokens(user.id, "invite")

            # Generate new token
            settings = (
                request.env["thedevkitchen.email.link.settings"].sudo().get_settings()
            )
            company = (
                request.env["res.company"].sudo().browse(company_id)
            )
            raw_token, token_record = token_service.generate_token(
                user=user,
                token_type="invite",
                company=company,
                created_by=requester,
            )

            # Resend invite email
            try:
                invite_service.send_invite_email(
                    user, raw_token, settings.invite_link_ttl_hours, settings.frontend_base_url
                )
                email_status = "sent"
            except Exception as email_error:
                _logger.error(
                    f"Failed to send resend invite email to {user.email}: {email_error}"
                )
                email_status = "failed"

            _logger.info(
                f"Invite resent to user {user.id} ({user.email}) by {requester.login}"
            )

            # Return success response
            response_body = {
                "message": "Invite email resent successfully",
                "invite_expires_at": (
                    token_record.expires_at.isoformat()
                    if token_record.expires_at
                    else None
                ),
                "email_status": email_status,
            }

            return Response(
                json.dumps(response_body), status=200, content_type="application/json"
            )

        except Exception as e:
            _logger.exception("Unexpected error in resend_invite: %s", e)
            return self._error_response(
                500, "ERR_INTERNAL_SERVER_ERROR", "An unexpected error occurred"
            )

    def _get_user_profile(self, user):
        """
        Feature 010: Get user profile type.
        Prioritizes unified profile lookup (partner_id), falls back to group mapping.
        """
        # Primary method: lookup profile via partner_id (Feature 010 unified profile)
        if user.partner_id:
            profile_record = (
                request.env["thedevkitchen.estate.profile"]
                .sudo()
                .search([("partner_id", "=", user.partner_id.id)], limit=1)
            )
            if profile_record and profile_record.profile_type_id:
                return profile_record.profile_type_id.code

        return resolve_role(user) or "unknown"
