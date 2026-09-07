# -*- coding: utf-8 -*-
# NOTE: Do NOT import tests/unit/* here - they run independently via
# tests/run_unit_tests.py (plain unittest, no Odoo/DB).

# Integration tests directory (TransactionCase - WITH database)
from . import integration

# Feature 028: thedevkitchen.cms.template.generic ORM-level validations
from .integration import test_cms_template_generic_crud
