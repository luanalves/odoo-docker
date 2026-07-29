# -*- coding: utf-8 -*-

import json
import logging
from datetime import datetime
from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError
from .utils.auth import require_jwt
from .utils.response import error_response, success_response
from .utils.schema import SchemaValidator
from odoo.addons.thedevkitchen_apigateway.middleware import (
    require_session,
    require_company,
)
from ..utils import validators

_logger = logging.getLogger(__name__)


# RBAC Authorization Matrix (FR1.10, ADR-019, Feature 010)
# Maps creator role → list of profile types they can create
PROFILE_CREATION_MATRIX = {
    "quicksol_estate.group_real_estate_owner": [
        "owner",
        "director",
        "manager",
        "agent",
        "prospector",
        "receptionist",
        "financial",
        "legal",
        "tenant",
        "property_owner",
    ],
    "quicksol_estate.group_real_estate_director": [
        "agent",
        "prospector",
        "receptionist",
        "financial",
        "legal",
    ],
    "quicksol_estate.group_real_estate_manager": [
        "agent",
        "prospector",
        "receptionist",
        "financial",
        "legal",
    ],
    "quicksol_estate.group_real_estate_agent": [
        "tenant",
        "property_owner",  # Agent can create external profiles (tenant/property_owner)
    ],
}


class ProfileApiController(http.Controller):

    def _get_user_allowed_profile_type_ids(self, user):
        """Get list of profile type IDs the user is authorized to create"""
        allowed_codes = []

        for group_xml_id, types in PROFILE_CREATION_MATRIX.items():
            if user.has_group(group_xml_id):
                # Return the most permissive role (owner has all)
                if len(types) > len(allowed_codes):
                    allowed_codes = types

        # Convert codes to IDs
        if not allowed_codes:
            return []

        ProfileType = request.env["thedevkitchen.profile.type"]
        profile_types = ProfileType.sudo().search(
            [("code", "in", allowed_codes), ("is_active", "=", True)]
        )
        return profile_types.ids

    def _serialize_profile(self, profile, agent_by_profile_id=None):
        """Serialize profile record to JSON dict with HATEOAS links.

        agent_by_profile_id (dict[int, recordset] | None): when serializing
        a paginated list, callers MUST pass a prefetched
        {profile_id: agent_recordset} dict built via a single batched
        search() (see list_profiles) instead of leaving this None -- that
        avoids the N+1 query pattern that existed here since Feature
        010/024 (one real.estate.agent.search() per row). get_profile
        (single-record) may safely omit this and fall back to an
        individual search(), since there's no N+1 risk for one record.
        """
        data = {
            "id": profile.id,
            "name": profile.name,
            "document": profile.document,
            "email": profile.email,
            "phone": profile.phone,
            "mobile": profile.mobile,
            "occupation": profile.occupation,
            "birthdate": profile.birthdate.isoformat() if profile.birthdate else None,
            "hire_date": profile.hire_date.isoformat() if profile.hire_date else None,
            "profile_type": (
                profile.profile_type_id.code if profile.profile_type_id else None
            ),
            "profile_type_name": (
                profile.profile_type_id.name if profile.profile_type_id else None
            ),
            "company_id": profile.company_id.id if profile.company_id else None,
            "company_name": profile.company_id.name if profile.company_id else None,
            "partner_id": (
                profile.partner_id.id if profile.partner_id else None
            ),  # Add partner_id for testing
            "active": profile.active,
            "created_at": (
                profile.created_at.isoformat() if profile.created_at else None
            ),
            "updated_at": (
                profile.updated_at.isoformat() if profile.updated_at else None
            ),
            "_links": {
                "self": f"/api/v1/profiles/{profile.id}",
                "company": (
                    f"/api/v1/companies/{profile.company_id.id}"
                    if profile.company_id
                    else None
                ),
            },
        }

        # Add user_id if user exists (invited)
        if profile.partner_id and profile.partner_id.user_ids:
            user = profile.partner_id.user_ids[
                0
            ]  # Take first user (should only be one)
            data["user_id"] = user.id
            data["_links"]["resend_invite"] = "/api/v1/users/resend-invite"

        # Feature 027 (FR1.3/FR1.4): embed full agent sub-object for
        # profile_type='agent', with field parity to the removed
        # GET /api/v1/agents/{id}. Uses profile.env (not request.env) so
        # this method has no dependency on odoo.http.request -- keeps it
        # directly unit-testable.
        if profile.profile_type_id.code == "agent":
            if agent_by_profile_id is not None:
                agent = agent_by_profile_id.get(profile.id)
            else:
                agent = (
                    profile.env["real.estate.agent"]
                    .sudo()
                    .with_context(active_test=False)
                    .search([("profile_id", "=", profile.id)], limit=1)
                )
            if agent:
                data["agent_id"] = agent.id  # backward compat (Feature 026)
                data["agent"] = {
                    "id": agent.id,
                    "creci": agent.creci,
                    "creci_normalized": agent.creci_normalized,
                    "creci_number": agent.creci_number,
                    "creci_state": agent.creci_state,
                    "bank_name": agent.bank_name,
                    "bank_account": agent.bank_account,
                    "bank_account_type": agent.bank_account_type,
                    "pix_key": agent.pix_key,
                    "active": agent.active,
                    "deactivation_date": (
                        agent.deactivation_date.isoformat()
                        if agent.deactivation_date
                        else None
                    ),
                    "deactivation_reason": agent.deactivation_reason,
                    "user_id": agent.user_id.id if agent.user_id else None,
                    "_links": {
                        "properties": f"/api/v1/agents/{agent.id}/properties",
                        "performance": f"/api/v1/agents/{agent.id}/performance",
                        "commission_rules": f"/api/v1/agents/{agent.id}/commission-rules",
                    },
                }
                # FR1.5/FR6.4: points at /api/v1/profiles/{id}, not the
                # removed /api/v1/agents/{id}.
                data["_links"]["agent"] = f"/api/v1/profiles/{profile.id}"

        # Add invite link if no user yet (partner_id exists but no user)
        if profile.partner_id and not profile.partner_id.user_ids:
            data["_links"]["invite"] = "/api/v1/users/invite"

        return data

    def _resolve_profile_ids_by_agent_filters(self, env, creci_number, creci_state):
        """Feature 027 (FR1.1/FR1.2): resolve profile_ids matching the
        creci_number/creci_state filters via a single real.estate.agent
        search(), for list_profiles to AND into its own domain. Takes env
        as a plain param (not request.env) so this is unit-testable without
        odoo.http.request.

        Returns:
            None if neither filter was provided (caller should not touch
                the domain at all).
            list[int] otherwise (possibly empty -- an empty list means
                "filter applied, zero agents matched", which the caller
                must turn into an impossible domain clause, not "no
                filter").
        """
        if not creci_number and not creci_state:
            return None

        domain = []
        if creci_number:
            domain.append(("creci_number", "ilike", creci_number))
        if creci_state:
            domain.append(("creci_state", "=", creci_state.upper()))

        agents = (
            env["real.estate.agent"]
            .sudo()
            .with_context(active_test=False)
            .search(domain)
        )
        return agents.mapped("profile_id").ids

    @http.route(
        "/api/v1/profiles",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def create_profile(self, **kwargs):

        try:
            user = request.env.user

            # Parse and validate JSON body
            body = json.loads(request.httprequest.data.decode("utf-8"))

            is_valid, errors = SchemaValidator.validate_request(
                body, SchemaValidator.PROFILE_CREATE_SCHEMA
            )
            if not is_valid:
                return error_response(400, f"Validation error: {errors}")

            # Validate company_id from body against user's companies (D5.1)
            company_id = body["company_id"]
            if request.user_company_ids and company_id not in request.user_company_ids:
                return error_response(403, f"Access denied to company {company_id}")

            # Get profile_type_id from body (integer FK)
            profile_type_id = body["profile_type_id"]

            # Validate profile_type_id exists and is active
            ProfileType = request.env["thedevkitchen.profile.type"]
            profile_type = ProfileType.sudo().browse(profile_type_id)
            if not profile_type.exists() or not profile_type.is_active:
                return error_response(
                    400, f"Invalid or inactive profile_type_id: {profile_type_id}"
                )

            # Check RBAC authorization matrix (FR1.10)
            allowed_type_ids = self._get_user_allowed_profile_type_ids(user)
            if profile_type_id not in allowed_type_ids:
                return error_response(
                    403,
                    f"Your role cannot create profile_type_id: {profile_type_id} ({profile_type.name})",
                )

            # Feature 026 (corrigido, 2026-07-23, segunda correção): validar
            # creci/bank_name/bank_account/pix_key SÓ quando o profile_type
            # realmente for 'agent' -- validar isso incondicionalmente (via
            # PROFILE_CREATE_SCHEMA) rejeitaria, por exemplo, um perfil
            # 'tenant' só porque um creci mal formatado foi enviado, mesmo
            # esse campo sendo irrelevante para esse profile_type.
            if profile_type.code == "agent":
                is_valid, agent_field_errors = (
                    SchemaValidator.validate_profile_agent_fields(body)
                )
                if not is_valid:
                    return error_response(
                        400, f"Validation error: {agent_field_errors}"
                    )

            # Normalize document (D11)
            document_raw = body["document"]
            document_normalized = validators.normalize_document(document_raw)

            if not validators.validate_document(document_normalized):
                return error_response(
                    400, f"Invalid document (CPF/CNPJ): {document_raw}"
                )

            # Check for duplicate (document, company_id, profile_type_id)
            Profile = request.env["thedevkitchen.estate.profile"]
            existing = Profile.sudo().search(
                [
                    ("document", "=", document_normalized),
                    ("company_id", "=", company_id),
                    ("profile_type_id", "=", profile_type_id),
                ],
                limit=1,
            )

            if existing:
                return error_response(
                    409,
                    f"Profile already exists with this document ({document_raw}) for profile_type_id {profile_type_id} ({profile_type.name}) in company {company_id}",
                )

            # Build profile vals
            profile_vals = {
                "name": body["name"],
                "company_id": company_id,
                "profile_type_id": profile_type_id,
                "document": document_normalized,
                "email": body["email"],
                "birthdate": body["birthdate"],
                "phone": body.get("phone"),
                "mobile": body.get("mobile"),
                "occupation": body.get("occupation"),
                "hire_date": body.get("hire_date"),
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }

            # Create profile
            profile = Profile.sudo().create(profile_vals)

            # If profile_type code is 'agent', auto-create agent extension (FR1.4)
            if profile.profile_type_id.code == "agent":
                Agent = request.env["real.estate.agent"]
                from datetime import date

                agent_vals = {
                    "profile_id": profile.id,
                    "name": profile.name,
                    "cpf": profile.document,
                    "email": profile.email,
                    "phone": profile.phone,
                    "mobile": profile.mobile,
                    "company_id": company_id,
                    "hire_date": profile.hire_date
                    or date.today(),  # Default to today if not provided
                }
                # Feature 026 (corrigido, 2026-07-23): campos exclusivos de
                # agente (sem equivalente em nenhum outro profile_type) agora
                # são aceitos aqui, no cadastro, em vez de esperar o convite
                # (POST /api/v1/users/invite) para existirem -- o agente já
                # nasce completo, não precisa aguardar o login ser criado.
                for agent_field in ("creci", "bank_name", "bank_account", "pix_key"):
                    if body.get(agent_field) is not None:
                        agent_vals[agent_field] = body[agent_field]
                agent = Agent.sudo().create(agent_vals)
                _logger.info(f"Auto-created agent {agent.id} for profile {profile.id}")

            # Serialize response with HATEOAS (FR1.9)
            response_data = self._serialize_profile(profile)

            return success_response(response_data, status_code=201)

        except ValidationError as e:
            _logger.warning(f"Validation error creating profile: {str(e)}")
            # Feature 026: a duplicate agent.creci (_check_creci_format,
            # models/agent.py) can now raise here too, AFTER profile.sudo()
            # .create() already succeeded earlier in this same method -- an
            # uncaught-but-handled exception like this one does NOT roll back
            # Odoo's cursor on its own; the request would otherwise still
            # commit the already-created profile row at the end of this HTTP
            # request despite returning an error, leaving a profile with no
            # agent record for a type that requires one. Roll back explicitly
            # before responding, matching the same pattern already used in
            # invite_controller.py for the equivalent atomicity guarantee.
            request.env.cr.rollback()
            # Map the duplicate-creci case to 409 Conflict, matching this
            # project's convention for "already exists" errors (see the
            # document-uniqueness check earlier in this same method), instead
            # of a generic 400.
            if "já cadastrado" in str(e):
                return error_response(409, str(e))
            return error_response(400, str(e))
        except json.JSONDecodeError:
            return error_response(400, "Invalid JSON body")
        except Exception as e:
            _logger.exception("Error creating profile")
            return error_response(500, f"Internal server error: {str(e)}")

    @http.route(
        "/api/v1/profiles",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def list_profiles(self, **kwargs):

        try:

            # Validate required company_ids parameter (D5.2)
            company_ids_param = kwargs.get("company_ids")
            if not company_ids_param:
                return error_response(400, "company_ids parameter is required")

            # Parse company_ids
            try:
                requested_company_ids = [
                    int(cid.strip()) for cid in company_ids_param.split(",")
                ]
            except ValueError:
                return error_response(
                    400, "Invalid company_ids format. Use comma-separated integers."
                )

            # Validate user access to requested companies
            if request.user_company_ids:  # Not admin
                unauthorized = [
                    cid
                    for cid in requested_company_ids
                    if cid not in request.user_company_ids
                ]
                if unauthorized:
                    return error_response(
                        403, f"Access denied to company IDs: {unauthorized}"
                    )

            # Build domain
            domain = []

            # Company filter
            if len(requested_company_ids) == 1:
                domain.append(("company_id", "=", requested_company_ids[0]))
            else:
                domain.append(("company_id", "in", requested_company_ids))

            # Optional filters
            profile_type = kwargs.get("profile_type")
            if profile_type:
                ProfileType = request.env["thedevkitchen.profile.type"]
                ptype = ProfileType.sudo().search(
                    [("code", "=", profile_type)], limit=1
                )
                if ptype:
                    domain.append(("profile_type_id", "=", ptype.id))
                else:
                    return error_response(400, f"Invalid profile_type: {profile_type}")

            document = kwargs.get("document")
            if document:
                normalized = validators.normalize_document(document)
                domain.append(("document", "=", normalized))

            name = kwargs.get("name")
            if name:
                domain.append(("name", "ilike", name))

            # Active filter (ADR-015)
            is_active = kwargs.get("active")
            if is_active is not None:
                if is_active.lower() == "true":
                    domain.append(("active", "=", True))
                elif is_active.lower() == "false":
                    domain.append(("active", "=", False))

            # Feature 027 (FR1.1/FR1.2): creci_number/creci_state filters,
            # equivalent to the removed GET /api/v1/agents?creci_number=...
            creci_number = kwargs.get("creci_number")
            creci_state = kwargs.get("creci_state")
            agent_profile_ids = self._resolve_profile_ids_by_agent_filters(
                request.env, creci_number, creci_state
            )
            if agent_profile_ids is not None:
                domain.append(("id", "in", agent_profile_ids or [0]))

            # Pagination
            limit = min(int(kwargs.get("limit", 20)), 100)
            offset = int(kwargs.get("offset", 0))

            # Query profiles
            Profile = request.env["thedevkitchen.estate.profile"]
            total = Profile.with_context(active_test=False).sudo().search_count(domain)
            profiles = (
                Profile.with_context(active_test=False)
                .sudo()
                .search(domain, limit=limit, offset=offset, order="name asc")
            )

            # Feature 027 (FR1.4): resolve all agent sub-objects for this
            # page in ONE query instead of one search() per row -- fixes
            # the N+1 pattern that existed here since Feature 010/024.
            agent_profile_ids = [
                p.id for p in profiles if p.profile_type_id.code == "agent"
            ]
            agents = (
                request.env["real.estate.agent"]
                .sudo()
                .with_context(active_test=False)
                .search([("profile_id", "in", agent_profile_ids)])
            )
            agent_by_profile_id = {a.profile_id.id: a for a in agents}

            # Serialize profiles
            profile_list = [
                self._serialize_profile(p, agent_by_profile_id=agent_by_profile_id)
                for p in profiles
            ]

            # HATEOAS pagination links (FR2.4)
            company_ids_str = ",".join(str(cid) for cid in requested_company_ids)
            response_data = {
                "success": True,
                "data": profile_list,
                "count": len(profile_list),
                "total": total,
                "limit": limit,
                "offset": offset,
                "_links": {
                    "self": f"/api/v1/profiles?company_ids={company_ids_str}&limit={limit}&offset={offset}",
                },
            }

            # Next/prev links
            if offset + limit < total:
                response_data["_links"][
                    "next"
                ] = f"/api/v1/profiles?company_ids={company_ids_str}&limit={limit}&offset={offset + limit}"
            if offset > 0:
                prev_offset = max(0, offset - limit)
                response_data["_links"][
                    "prev"
                ] = f"/api/v1/profiles?company_ids={company_ids_str}&limit={limit}&offset={prev_offset}"

            return success_response(response_data)

        except ValueError as e:
            return error_response(400, f"Invalid parameter: {str(e)}")
        except Exception as e:
            _logger.exception("Error listing profiles")
            return error_response(500, f"Internal server error: {str(e)}")

    @http.route(
        "/api/v1/profiles/<int:profile_id>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def get_profile(self, profile_id, **kwargs):

        try:

            Profile = request.env["thedevkitchen.estate.profile"]
            profile = Profile.sudo().search([("id", "=", profile_id)], limit=1)

            if not profile:
                return error_response(404, "Profile not found")

            # Company isolation check (FR1.12, anti-enumeration)
            if (
                request.user_company_ids
                and profile.company_id.id not in request.user_company_ids
            ):
                return error_response(
                    404, "Profile not found"
                )  # Don't reveal existence

            # Serialize with HATEOAS
            response_data = self._serialize_profile(profile)

            return success_response(response_data)

        except Exception as e:
            _logger.exception(f"Error fetching profile {profile_id}")
            return error_response(500, f"Internal server error: {str(e)}")

    @http.route(
        "/api/v1/profiles/<int:profile_id>",
        type="http",
        auth="none",
        methods=["PUT"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def update_profile(self, profile_id, **kwargs):

        try:

            # Parse and validate body
            body = json.loads(request.httprequest.data.decode("utf-8"))

            is_valid, errors = SchemaValidator.validate_request(
                body, SchemaValidator.PROFILE_UPDATE_SCHEMA
            )
            if not is_valid:
                return error_response(400, f"Validation error: {errors}")

            # Reject immutable fields (FR3.2)
            immutable_fields = ["profile_type", "company_id", "document"]
            for field in immutable_fields:
                if field in body:
                    return error_response(
                        400, f"Field {field} is immutable and cannot be updated"
                    )

            # Fetch profile
            Profile = request.env["thedevkitchen.estate.profile"]
            profile = Profile.sudo().search([("id", "=", profile_id)], limit=1)

            if not profile:
                return error_response(404, "Profile not found")

            # Company isolation check
            if (
                request.user_company_ids
                and profile.company_id.id not in request.user_company_ids
            ):
                return error_response(404, "Profile not found")

            # Feature 027 (FR5.2): agent-exclusive fields are only
            # validated when profile_type resolves to 'agent' -- same
            # conditional-validation pattern PROFILE_AGENT_FIELDS_SCHEMA
            # already uses for create_profile since Feature 026.
            is_agent_profile = profile.profile_type_id.code == "agent"
            if is_agent_profile:
                is_valid, agent_field_errors = (
                    SchemaValidator.validate_profile_agent_update_fields(body)
                )
                if not is_valid:
                    return error_response(
                        400, f"Validation error: {agent_field_errors}"
                    )

            # Build update vals
            update_vals = {"updated_at": datetime.now()}

            # Update mutable fields
            for field in [
                "name",
                "email",
                "phone",
                "mobile",
                "occupation",
                "birthdate",
                "hire_date",
            ]:
                if field in body:
                    update_vals[field] = body[field]

            # Update profile
            profile.write(update_vals)

            # Sync to agent extension if profile_type='agent' (FR3.4,
            # extended by FR5.3 to also cover creci/bank_*/pix_key)
            if is_agent_profile:
                Agent = request.env["real.estate.agent"]
                agent = Agent.sudo().search([("profile_id", "=", profile.id)], limit=1)
                if agent:
                    agent_update_vals = {}
                    for field in [
                        "name",
                        "email",
                        "phone",
                        "mobile",
                        "hire_date",
                        "creci",
                        "bank_name",
                        "bank_account",
                        "bank_account_type",
                        "bank_branch",
                        "pix_key",
                    ]:
                        if field in body:
                            agent_update_vals[field] = body[field]

                    if agent_update_vals:
                        try:
                            agent.write(agent_update_vals)
                        except ValidationError as e:
                            # FR5.4: duplicate creci -- roll back both the
                            # profile write above and this failed agent
                            # write, map to 409 (same pattern
                            # create_profile uses since Feature 026).
                            request.env.cr.rollback()
                            if "já cadastrado" in str(e):
                                return error_response(409, str(e))
                            return error_response(400, str(e))
                        _logger.info(
                            f"Synced profile {profile.id} updates to agent {agent.id}"
                        )

            # Serialize response
            response_data = self._serialize_profile(profile)

            return success_response(response_data)

        except json.JSONDecodeError:
            return error_response(400, "Invalid JSON body")
        except Exception as e:
            _logger.exception(f"Error updating profile {profile_id}")
            return error_response(500, f"Internal server error: {str(e)}")

    @http.route(
        "/api/v1/profiles/<int:profile_id>",
        type="http",
        auth="none",
        methods=["DELETE"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    @require_company
    def delete_profile(self, profile_id, **kwargs):

        try:

            # Parse optional body for deactivation_reason
            deactivation_reason = None
            try:
                body = json.loads(request.httprequest.data.decode("utf-8"))
                deactivation_reason = body.get("reason")
            except (json.JSONDecodeError, AttributeError):
                pass  # Optional body

            # Fetch profile
            Profile = request.env["thedevkitchen.estate.profile"]
            profile = Profile.sudo().search([("id", "=", profile_id)], limit=1)

            if not profile:
                return error_response(404, "Profile not found")

            # Company isolation check
            if (
                request.user_company_ids
                and profile.company_id.id not in request.user_company_ids
            ):
                return error_response(404, "Profile not found")

            # Check if already inactive (ADR-015)
            if not profile.active:
                return error_response(400, "Profile is already inactive")

            # Soft delete profile
            profile.write(
                {
                    "active": False,
                    "deactivation_date": datetime.now(),
                    "deactivation_reason": deactivation_reason or "Deactivated via API",
                }
            )

            # Cascade to agent extension if profile_type='agent' (FR4.2)
            if profile.profile_type_id.code == "agent":
                Agent = request.env["real.estate.agent"]
                agent = Agent.sudo().search([("profile_id", "=", profile.id)], limit=1)
                if agent and agent.active:
                    agent.write(
                        {
                            "active": False,
                            "deactivation_date": datetime.now(),
                            "deactivation_reason": deactivation_reason
                            or "Profile deactivated",
                        }
                    )
                    _logger.info(f"Cascaded deactivation to agent {agent.id}")

            # Cascade to linked res.users (FR4.2)
            if profile.partner_id:
                User = request.env["res.users"]
                users = User.sudo().search([("partner_id", "=", profile.partner_id.id)])
                for user_record in users:
                    if user_record.active:
                        user_record.write({"active": False})
                        _logger.info(
                            f"Deactivated user {user_record.id} linked to profile {profile.id}"
                        )
                        # Proactive session invalidation (T017: US2)
                        # APISession.write({'is_active': False}) triggers the Redis override
                        try:
                            APISession = request.env["thedevkitchen.api.session"]
                            active_sessions = APISession.sudo().search(
                                [
                                    ("user_id", "=", user_record.id),
                                    ("is_active", "=", True),
                                ]
                            )
                            if active_sessions:
                                active_sessions.write({"is_active": False})
                                _logger.info(
                                    "[CACHE] invalidated %d session(s) for user %d",
                                    len(active_sessions),
                                    user_record.id,
                                )
                        except Exception as exc:
                            _logger.warning(
                                "[CACHE] session invalidation during profile delete failed: %s",
                                exc,
                            )

            return success_response(
                {
                    "success": True,
                    "message": f"Profile {profile_id} deactivated successfully",
                }
            )

        except Exception as e:
            _logger.exception(f"Error deleting profile {profile_id}")
            return error_response(500, f"Internal server error: {str(e)}")

    @http.route(
        "/api/v1/profile-types",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    @require_jwt
    @require_session
    def list_profile_types(self, **kwargs):

        try:
            ProfileType = request.env["thedevkitchen.profile.type"]
            types = ProfileType.sudo().search(
                [("is_active", "=", True)], order="id asc"
            )

            type_list = []
            for ptype in types:
                type_list.append(
                    {
                        "id": ptype.id,
                        "code": ptype.code,
                        "name": ptype.name,
                        "level": ptype.level,
                        "group_xml_id": ptype.group_xml_id,
                    }
                )

            return success_response(
                {
                    "success": True,
                    "data": type_list,
                    "count": len(type_list),
                }
            )

        except Exception as e:
            _logger.exception("Error listing profile types")
            return error_response(500, f"Internal server error: {str(e)}")
