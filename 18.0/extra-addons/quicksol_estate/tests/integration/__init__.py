# -*- coding: utf-8 -*-
"""
Integration Tests for Quicksol Estate Module

These tests use odoo.tests.TransactionCase and require:
- Odoo framework
- Database connection
- Test transaction rollback

Purpose: Test ACLs, record rules, database constraints, and integration
Execution: docker compose run --rm odoo odoo --test-enable --test-tags=quicksol_estate

Guidelines (ADR-003):
- Test security rules (ACLs, record rules, multi-tenancy)
- Test database constraints and triggers
- Test integration between models
- Use TransactionCase for database access
"""

from . import test_event_bus_integration
from . import test_rbac_owner_integration
# Feature 013: Property Proposals
from . import test_proposal_create
from . import test_proposal_send
from . import test_proposal_queue
from . import test_proposal_counter
from . import test_proposal_accept_reject
from . import test_proposal_lead_integration
from . import test_proposal_list
from . import test_proposal_attachments
from . import test_proposal_expiration

# 2026-07 ADR-003 validation-coverage audit gap fixes
from . import test_validation_gaps

# Feature 026: characterization test for agent.create() profile/user setdefault mechanism
from . import test_agent_create_from_profile_and_user

# Feature 027: _serialize_profile embeds batched agent sub-object
from . import test_serialize_profile_agent_subobject

# Feature 027: creci_number/creci_state filters on GET /api/v1/profiles
from . import test_list_profiles_creci_filters
