# -*- coding: utf-8 -*-
import json
import logging
import psycopg2
from odoo import http
from odoo.http import request, Response
from odoo.exceptions import UserError, ValidationError
from odoo.addons.thedevkitchen_apigateway.middleware import (
    require_jwt,
    require_session,
    require_company,
)
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
    def invite_user(self, **kwargs):  # noqa: C901
        # Pre-existing complexity debt, predates this file joining .flake8's
        # per-file C901 exemptions.
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
            profile_record = ProfileModel.sudo().search(
                [("id", "=", int(profile_id))], limit=1
            )

            if not profile_record:
                return self._error_response(
                    404, "not_found", f"Profile {profile_id} not found"
                )

            # Check if profile already has a user (via partner_id)
            if profile_record.partner_id:
                existing_user = (
                    request.env["res.users"]
                    .sudo()
                    .search(
                        [("partner_id", "=", profile_record.partner_id.id)], limit=1
                    )
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
                    profile_record=profile_record, created_by=current_user
                )
            except ValidationError as e:
                if "already exists" in str(e):
                    field = "cpf" if "CPF" in str(e) else "email"
                    return self._error_response(
                        409, "conflict", str(e), {"field": field}
                    )
                return self._error_response(400, "validation_error", str(e))

            # Feature 026 (corrigido, 2026-07-23): link real.estate.agent to
            # the new login. Agent-exclusive fields (creci/bank/pix) are no
            # longer accepted here at all -- they're set at profile-creation
            # time (POST /api/v1/profiles) instead, since they don't depend
            # on the login existing. This step ONLY sets user_id on the
            # record profile_api.py already auto-created (FR2.1b).
            agent_id = None
            if profile_type == "agent":
                try:
                    agent_record = self._link_agent_to_invited_user(
                        profile_record, user
                    )
                except ValidationError as e:
                    # FR2.2: res.users (and the profile's partner_id link) were already
                    # created/written earlier in this same request's cursor and are not yet
                    # committed. Returning a response here without rolling back would leave
                    # them durably committed despite the client seeing a 409 -- roll back the
                    # whole transaction so a failed agent link never leaves a partial state.
                    request.env.cr.rollback()
                    return self._error_response(409, "conflict", str(e))
                except psycopg2.IntegrityError as e:
                    # Defense in depth: the defensive create() branch (no bare
                    # agent found for this profile_id -- legacy/unusual state,
                    # since profile_api.py normally auto-creates one) pulls cpf
                    # from profile.document via the model's setdefault(), which
                    # could in principle collide with a DIFFERENT agent's cpf
                    # in the same company (real_estate_agent_cpf_company_unique).
                    # That's a raw psycopg2 IntegrityError/UniqueViolation, not
                    # odoo.exceptions.ValidationError -- without this except
                    # clause it would fall through to the generic `except
                    # Exception` below and surface as a 500.
                    request.env.cr.rollback()
                    error_msg = str(e)
                    if "real_estate_agent_cpf_company_unique" in error_msg:
                        message = (
                            "An agent with this CPF already exists in this company"
                        )
                    else:
                        message = "Data integrity error while linking agent"
                    return self._error_response(409, "conflict", message)
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
                "resend_invite": "/api/v1/users/resend-invite",
                "collection": "/api/v1/users",
                "profile": f"/api/v1/profiles/{profile_id}",
            }

            # Feature 027 (FR6.4): /api/v1/agents/{id} is removed;
            # /api/v1/profiles/{id} already exposes the agent sub-object.
            if agent_id:
                links["agent"] = f"/api/v1/profiles/{profile_id}"

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

    def _link_agent_to_invited_user(self, profile_record, user):
        """Feature 026 (corrigido, 2026-07-23): link the real.estate.agent that
        profile_api.py already auto-created for this profile (Feature 010,
        now including any creci/bank/pix fields supplied at profile-creation
        time) to the new login, by setting user_id -- the field every RBAC/
        notification consumer (property_api.py, lead_api.py, serializers.py,
        proposal.py, record_rules.xml) actually reads (FR2.1b). Creates one
        defensively if none exists (legacy/unusual state -- profile_api.py
        normally auto-creates it). Raises ValidationError on a user_id
        conflict (_check_user_unique) -- the caller is responsible for
        rolling back the transaction (FR2.2) before returning.

        No agent-specific fields (creci/bank/pix) are read or written here
        anymore -- those are set once, at profile-creation time, and this
        step never touches them.
        """
        Agent = request.env["real.estate.agent"].sudo()
        existing_agent = Agent.search([("profile_id", "=", profile_record.id)], limit=1)
        if existing_agent:
            existing_agent.write({"user_id": user.id})
            return existing_agent
        return Agent.create(
            {
                "profile_id": profile_record.id,
                "user_id": user.id,
            }
        )

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
            company_id = request.httprequest.headers.get("X-Company-Id")

            if not requester or not requester.id or not company_id:
                return self._error_response(
                    401, "ERR_UNAUTHORIZED", "Missing session context"
                )

            try:
                company_id = int(company_id)
            except (TypeError, ValueError):
                return self._error_response(
                    400, "validation_error", "Invalid X-Company-Id header"
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
            company = request.env["res.company"].sudo().browse(company_id)
            raw_token, token_record = token_service.generate_token(
                user=user,
                token_type="invite",
                company=company,
                created_by=requester,
            )

            # Resend invite email
            try:
                invite_service.send_invite_email(
                    user,
                    raw_token,
                    settings.invite_link_ttl_hours,
                    settings.frontend_base_url,
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
