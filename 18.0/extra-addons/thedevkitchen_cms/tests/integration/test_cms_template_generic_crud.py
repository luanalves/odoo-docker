# -*- coding: utf-8 -*-
"""
Integration tests for thedevkitchen.cms.template.generic — exercises the
real Odoo ORM (required=True, Selection values, _sql_constraints, soft
delete) against a live transactional database. Feature 028.

Exception types below were verified empirically against this project's
Odoo/Postgres version via `odoo shell` before writing this test: a missing
required field raises psycopg2.errors.NotNullViolation (an IntegrityError
subtype), not odoo.exceptions.ValidationError; an invalid Selection value
raises a plain ValueError before any SQL executes.
"""
from psycopg2 import IntegrityError

from odoo.tests.common import TransactionCase


class TestCmsTemplateGenericCrud(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Generic = self.env["thedevkitchen.cms.template.generic"].sudo()
        # Defensive cleanup: TransactionCase rolls back between test methods,
        # but not necessarily between separate `odoo --test-enable`
        # invocations against the same dev database (same precaution as
        # quicksol_estate/tests/integration/test_validation_gaps.py).
        self.Generic.search([("name", "like", "it_generic_")]).unlink()

    def test_create_with_valid_data(self):
        tpl = self.Generic.create({"name": "it_generic_landing", "category": "landing"})
        self.assertTrue(tpl.id)
        self.assertTrue(tpl.active)
        self.assertEqual(tpl.category, "landing")

    def test_name_required(self):
        with self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.Generic.create({"category": "landing"})

    def test_category_required(self):
        with self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.Generic.create({"name": "it_generic_no_category"})

    def test_category_rejects_unknown_value(self):
        with self.assertRaises(ValueError):
            self.Generic.create({"name": "it_generic_bad_category", "category": "not-a-real-category"})

    def test_unique_name_conflict(self):
        self.Generic.create({"name": "it_generic_dup", "category": "landing"})
        with self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.Generic.create({"name": "it_generic_dup", "category": "property"})

    def test_soft_delete_keeps_record(self):
        tpl = self.Generic.create({"name": "it_generic_soft_delete", "category": "about"})
        tpl.write({"active": False})
        self.assertFalse(tpl.active)
        found = self.Generic.with_context(active_test=False).search([("id", "=", tpl.id)])
        self.assertEqual(len(found), 1, "Deactivating must not remove the row")
