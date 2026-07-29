# -*- coding: utf-8 -*-
# NOTE: Do NOT import tests/unit/* here - they run independently with unittest
# Unit tests are executed via: python3 tests/unit/run_unit_tests.py

# Base test classes (always available)
from . import base_validation_test
from . import base_company_test
from . import base_agent_test

# Integration tests directory (TransactionCase - WITH database)
from . import integration
# Feature 013: Property Proposals (explicit imports for Odoo test discovery)
from .integration import test_proposal_create
from .integration import test_proposal_send
from .integration import test_proposal_queue
from .integration import test_proposal_counter
from .integration import test_proposal_accept_reject
from .integration import test_proposal_lead_integration
from .integration import test_proposal_list
from .integration import test_proposal_attachments
from .integration import test_proposal_expiration
from .integration import test_validation_gaps
# Feature 026: characterization test for agent.create() profile/user setdefault mechanism
from .integration import test_agent_create_from_profile_and_user
# Feature 027: _serialize_profile embeds batched agent sub-object
from .integration import test_serialize_profile_agent_subobject
# Feature 027: creci_number/creci_state filters on GET /api/v1/profiles
from .integration import test_list_profiles_creci_filters
# Feature 027: PUT /api/v1/profiles/<id> syncs agent-exclusive fields
from .integration import test_update_profile_agent_fields

# Observer pattern tests
from . import observers
