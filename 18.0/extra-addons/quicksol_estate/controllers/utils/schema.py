# -*- coding: utf-8 -*-
"""
Schema Validation Utilities

Provides request/response schema validation for API endpoints.
Ensures API contracts are enforced per ADR-005 (OpenAPI 3.0).

Author: Quicksol Technologies
Date: 2026-01-15
"""

import logging
from ...utils import validators

_logger = logging.getLogger(__name__)


class SchemaValidator:
    """
    Validates request and response data against schema definitions.
    Ensures API contracts are maintained and data integrity is preserved.
    """

    # Agent creation schema
    AGENT_CREATE_SCHEMA = {
        "required": ["name", "cpf", "company_id", "email"],
        "optional": [
            "phone",
            "mobile",
            "creci",
            "hire_date",
            "bank_name",
            "bank_account",
            "pix_key",
        ],
        "types": {
            "name": str,
            "cpf": str,
            "email": str,
            "phone": str,
            "mobile": str,
            "creci": str,
            "hire_date": str,
            "bank_name": str,
            "bank_account": str,
            "pix_key": str,
            "company_id": int,
        },
        "constraints": {
            "name": lambda v: len(v) >= 3 and len(v) <= 255,
            "cpf": lambda v: len(v.replace(".", "").replace("-", "")) == 11,
            "email": lambda v: "@" in v and "." in v,
            "creci": lambda v: len(v) >= 4,
        },
    }

    # Agent update schema
    AGENT_UPDATE_SCHEMA = {
        "required": [],
        "optional": [
            "name",
            "email",
            "phone",
            "mobile",
            "creci",
            "bank_name",
            "bank_account",
            "pix_key",
        ],
        "types": {
            "name": str,
            "email": str,
            "phone": str,
            "mobile": str,
            "creci": str,
            "bank_name": str,
            "bank_account": str,
            "pix_key": str,
        },
        "constraints": {
            "name": lambda v: len(v) >= 3 if v else True,
            "cpf": lambda v: (
                len(v.replace(".", "").replace("-", "")) == 11 if v else True
            ),
            "email": lambda v: "@" in v and "." in v if v else True,
        },
    }

    # Assignment schema
    ASSIGNMENT_CREATE_SCHEMA = {
        "required": ["agent_id", "property_id"],
        "optional": ["responsibility_type", "notes"],
        "types": {
            "agent_id": int,
            "property_id": int,
            "responsibility_type": str,
            "notes": str,
        },
        "constraints": {
            "agent_id": lambda v: v > 0,
            "property_id": lambda v: v > 0,
            "responsibility_type": lambda v: (
                v in ["primary", "secondary", "support"] if v else True
            ),
        },
    }

    # Performance metrics schema
    PERFORMANCE_SCHEMA = {
        "required": ["agent_id"],
        "optional": ["start_date", "end_date", "metric"],
        "types": {
            "agent_id": int,
            "start_date": str,
            "end_date": str,
            "metric": str,
        },
        "constraints": {
            "agent_id": lambda v: v > 0,
            "metric": lambda v: (
                v in ["sales", "commission", "properties"] if v else True
            ),
        },
    }

    # ===== PROFILE SCHEMAS (Feature 010) =====

    # Profile creation schema (FR1.1)
    PROFILE_CREATE_SCHEMA = {
        "required": [
            "name",
            "company_id",
            "document",
            "email",
            "birthdate",
            "profile_type_id",
        ],
        "optional": [
            "phone",
            "mobile",
            "occupation",
            "hire_date",
        ],
        "types": {
            "name": str,
            "company_id": int,
            "document": str,
            "email": str,
            "birthdate": str,
            "profile_type_id": int,
            "phone": str,
            "mobile": str,
            "occupation": str,
            "hire_date": str,
        },
        "constraints": {
            "name": lambda v: len(v.strip()) > 0,
            "company_id": lambda v: isinstance(v, int) and v > 0,
            "document": lambda v: (
                validators.validate_document(validators.normalize_document(v))
                if v
                else False
            ),
            "email": lambda v: "@" in v and "." in v.split("@")[-1] if v else False,
            "birthdate": lambda v: len(v.strip()) > 0,
            "profile_type_id": lambda v: isinstance(v, int) and v > 0,
        },
    }

    # Feature 026 (corrigido, 2026-07-23, segunda correção): campos exclusivos
    # de agente aceitos por POST /api/v1/profiles -- sem equivalente em
    # nenhum outro profile_type. Deliberadamente NÃO fazem parte de
    # PROFILE_CREATE_SCHEMA: esse schema genérico valida ANTES de
    # profile_type_id ser resolvido para seu code, então uma constraint de
    # creci ali dispararia mesmo para um profile_type que não é 'agent' (ex:
    # um creci mal formatado rejeitaria a criação de um perfil 'tenant', que
    # nunca vai usar esse campo). Este schema separado só é validado pelo
    # controller (profile_api.py::create_profile) DEPOIS de confirmar
    # profile_type.code == 'agent' -- para qualquer outro tipo, esses campos
    # são simplesmente ignorados, sem nenhuma validação ser tentada.
    PROFILE_AGENT_FIELDS_SCHEMA = {
        "required": [],
        "optional": ["creci", "bank_name", "bank_account", "pix_key"],
        "types": {
            k: v
            for k, v in AGENT_CREATE_SCHEMA["types"].items()
            if k in {"creci", "bank_name", "bank_account", "pix_key"}
        },
        "constraints": {
            k: v
            for k, v in AGENT_CREATE_SCHEMA["constraints"].items()
            if k in {"creci", "bank_name", "bank_account", "pix_key"}
        },
    }

    # Feature 027 (FR5.1): campos exclusivos de agente aceitos por
    # PUT /api/v1/profiles/<id> -- superset de PROFILE_AGENT_FIELDS_SCHEMA
    # (Feature 026, usado só no create): além de creci/bank_name/
    # bank_account/pix_key, inclui bank_account_type e bank_branch, que o
    # AGENT_UPDATE_SCHEMA legado (PUT /api/v1/agents/<id>) aceitava via
    # allowed_fields no controller SEM nenhuma validação de schema -- esta
    # spec fecha essa lacuna. Mesma regra da Feature 026: só é invocado pelo
    # controller (profile_api.py::update_profile) DEPOIS de confirmar
    # profile.profile_type_id.code == 'agent'; para qualquer outro tipo,
    # esses campos são ignorados sem nenhuma tentativa de validação.
    PROFILE_AGENT_UPDATE_FIELDS_SCHEMA = {
        "required": [],
        "optional": [
            "creci",
            "bank_name",
            "bank_account",
            "bank_account_type",
            "bank_branch",
            "pix_key",
        ],
        "types": {
            "creci": str,
            "bank_name": str,
            "bank_account": str,
            "bank_account_type": str,
            "bank_branch": str,
            "pix_key": str,
        },
        "constraints": {
            "creci": AGENT_CREATE_SCHEMA["constraints"]["creci"],
            # PR #30 review (P1): bank_account_type is a real.estate.agent
            # Selection field (checking/savings only, see models/agent.py).
            # Without this constraint an invalid value passed schema
            # validation and blew up as a raw ValueError inside
            # agent.write() -- AFTER profile.write() had already run --
            # instead of a clean 400 raised before any write happens.
            "bank_account_type": lambda v: v in ("checking", "savings") if v else True,
        },
    }

    # Profile update schema (FR3.1)
    PROFILE_UPDATE_SCHEMA = {
        "required": [],
        "optional": [
            "name",
            "phone",
            "mobile",
            "email",
            "occupation",
            "birthdate",
            "hire_date",
        ],
        "types": {
            "name": str,
            "phone": str,
            "mobile": str,
            "email": str,
            "occupation": str,
            "birthdate": str,
            "hire_date": str,
        },
        "constraints": {
            "name": lambda v: len(v.strip()) > 0 if v else True,
            "email": lambda v: "@" in v and "." in v.split("@")[-1] if v else True,
        },
    }

    # Lease creation schema (FR-009, FR-010, FR-011)
    LEASE_CREATE_SCHEMA = {
        "required": [
            "property_id",
            "profile_id",
            "start_date",
            "end_date",
            "rent_amount",
        ],
        "optional": ["status"],
        "types": {
            "property_id": int,
            "profile_id": int,
            "start_date": str,
            "end_date": str,
            "rent_amount": (int, float),
            "status": str,
        },
        "constraints": {
            "property_id": lambda v: v > 0,
            "profile_id": lambda v: v > 0,
            "rent_amount": lambda v: v > 0,
            "status": lambda v: v in ("draft", "active") if v else True,
        },
    }

    # Lease update schema (FR-016)
    LEASE_UPDATE_SCHEMA = {
        "required": [],
        "optional": ["start_date", "end_date", "rent_amount", "status"],
        "types": {
            "start_date": str,
            "end_date": str,
            "rent_amount": (int, float),
            "status": str,
        },
        "constraints": {
            "rent_amount": lambda v: v > 0 if v else True,
            "status": lambda v: v in ("draft", "active") if v else True,
        },
    }

    # Lease renew schema (FR-017)
    LEASE_RENEW_SCHEMA = {
        "required": ["new_end_date"],
        "optional": ["new_rent_amount", "reason"],
        "types": {
            "new_end_date": str,
            "new_rent_amount": (int, float),
            "reason": str,
        },
        "constraints": {
            "new_rent_amount": lambda v: v > 0 if v else True,
        },
    }

    # Lease terminate schema (FR-018)
    LEASE_TERMINATE_SCHEMA = {
        "required": ["termination_date"],
        "optional": ["reason", "penalty_amount"],
        "types": {
            "termination_date": str,
            "reason": str,
            "penalty_amount": (int, float),
        },
        "constraints": {
            "penalty_amount": lambda v: v >= 0 if v is not None else True,
        },
    }

    # Sale creation schema (FR-021, FR-022)
    SALE_CREATE_SCHEMA = {
        "required": [
            "property_id",
            "company_id",
            "buyer_name",
            "sale_date",
            "sale_price",
        ],
        "optional": ["buyer_phone", "buyer_email", "agent_id", "lead_id"],
        "types": {
            "property_id": int,
            "company_id": int,
            "buyer_name": str,
            "sale_date": str,
            "sale_price": (int, float),
            "buyer_phone": str,
            "buyer_email": str,
            "agent_id": int,
            "lead_id": int,
        },
        "constraints": {
            "property_id": lambda v: v > 0,
            "company_id": lambda v: v > 0,
            "buyer_name": lambda v: len(v.strip()) > 0,
            "sale_price": lambda v: v > 0,
            "buyer_email": lambda v: (
                "@" in v and "." in v.split("@")[-1] if v else True
            ),
        },
    }

    # Sale update schema (FR-025)
    SALE_UPDATE_SCHEMA = {
        "required": [],
        "optional": [
            "buyer_name",
            "buyer_phone",
            "buyer_email",
            "sale_date",
            "sale_price",
        ],
        "types": {
            "buyer_name": str,
            "buyer_phone": str,
            "buyer_email": str,
            "sale_date": str,
            "sale_price": (int, float),
        },
        "constraints": {
            "buyer_name": lambda v: len(v.strip()) > 0 if v else True,
            "sale_price": lambda v: v > 0 if v else True,
            "buyer_email": lambda v: (
                "@" in v and "." in v.split("@")[-1] if v else True
            ),
        },
    }

    # Sale cancel schema (FR-027)
    SALE_CANCEL_SCHEMA = {
        "required": ["reason"],
        "optional": [],
        "types": {
            "reason": str,
        },
        "constraints": {
            "reason": lambda v: len(v.strip()) > 0,
        },
    }

    @staticmethod
    def validate_request(data, schema):
        """
        Validate request data against a schema.

        Args:
            data (dict): Request data to validate
            schema (dict): Schema definition with required, optional, types, constraints

        Returns:
            tuple: (is_valid: bool, errors: list of error messages)
        """
        errors = []

        # Check required fields
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")

        # Check field types
        types_def = schema.get("types", {})
        for field, field_type in types_def.items():
            if field in data and data[field] is not None:
                if not isinstance(data[field], field_type):
                    errors.append(
                        f"Field '{field}' must be {field_type.__name__}, got {type(data[field]).__name__}"
                    )

        # Check constraints
        constraints = schema.get("constraints", {})
        for field, constraint in constraints.items():
            if field in data and data[field] is not None:
                try:
                    if not constraint(data[field]):
                        errors.append(
                            f"Field '{field}' value '{data[field]}' violates constraint"
                        )
                except Exception as e:
                    errors.append(f"Field '{field}' validation error: {str(e)}")

        # Check for extra fields
        allowed_fields = set(schema.get("required", []) + schema.get("optional", []))
        extra_fields = set(data.keys()) - allowed_fields
        if extra_fields:
            _logger.debug(
                f"Extra fields in request (ignored): {', '.join(extra_fields)}"
            )

        return len(errors) == 0, errors

    @staticmethod
    def validate_agent_create(data):
        """Validate agent creation request."""
        return SchemaValidator.validate_request(
            data, SchemaValidator.AGENT_CREATE_SCHEMA
        )

    @staticmethod
    def validate_agent_update(data):
        """Validate agent update request."""
        return SchemaValidator.validate_request(
            data, SchemaValidator.AGENT_UPDATE_SCHEMA
        )

    @staticmethod
    def validate_profile_agent_fields(data):
        """Validate the agent-exclusive fields on POST /api/v1/profiles
        (creci/bank_name/bank_account/pix_key). Feature 026 (corrigido,
        2026-07-23): the caller MUST only invoke this after confirming the
        target profile_type resolves to 'agent' -- these fields are
        meaningless (and unvalidated) for every other profile_type."""
        return SchemaValidator.validate_request(
            data, SchemaValidator.PROFILE_AGENT_FIELDS_SCHEMA
        )

    @staticmethod
    def validate_profile_agent_update_fields(data):
        """Validate the agent-exclusive fields on PUT /api/v1/profiles/<id>
        (creci/bank_name/bank_account/bank_account_type/bank_branch/
        pix_key). Feature 027 (FR5.2): only called by profile_api.py::
        update_profile after confirming
        profile.profile_type_id.code == 'agent'."""
        return SchemaValidator.validate_request(
            data, SchemaValidator.PROFILE_AGENT_UPDATE_FIELDS_SCHEMA
        )

    @staticmethod
    def validate_assignment_create(data):
        """Validate assignment creation request."""
        return SchemaValidator.validate_request(
            data, SchemaValidator.ASSIGNMENT_CREATE_SCHEMA
        )

    @staticmethod
    def validate_performance_request(data):
        """Validate performance metrics request."""
        return SchemaValidator.validate_request(
            data, SchemaValidator.PERFORMANCE_SCHEMA
        )

    @staticmethod
    def build_response_schema(data, schema_type="agent"):
        """
        Build normalized response data according to schema.

        Args:
            data (dict or object): Data to normalize
            schema_type (str): Type of schema ('agent', 'assignment', 'performance')

        Returns:
            dict: Normalized response data
        """
        # This is where response transformation would happen
        # For now, just return the data as-is
        return data
