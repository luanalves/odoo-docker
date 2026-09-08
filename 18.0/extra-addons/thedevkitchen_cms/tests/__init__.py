# -*- coding: utf-8 -*-
# NOTE: Do NOT import tests/unit/* here - they run independently via
# tests/run_unit_tests.py (plain unittest, no Odoo/DB).

# Integration tests directory (TransactionCase - WITH database)
from . import integration

# Feature 028: thedevkitchen.cms.template.generic ORM-level validations
from .integration import test_cms_template_generic_crud

# PR #31 review fix: copy_generic_template's name-allocation race (real
# UNIQUE constraint, not simulated) — see the module docstring for context.
from .integration import test_cms_template_generic_copy_race

# Feature 029: shared company-slug resolution helper
from .integration import test_cms_slug_service

# Feature 029: PII-free public property serializer
from .integration import test_cms_public_property_serializer
