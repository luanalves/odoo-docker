# -*- coding: utf-8 -*-
"""
Integration tests for _create_company_template_copy()'s retry-on-collision
behavior (PR #31 review, P1 finding) — exercises the REAL
UNIQUE(name, company_id) constraint on thedevkitchen.cms.template against a
live database, not a simulated exception. The unit tests in
tests/unit/test_cms_template_generic_controller.py cover the retry control
flow with mocks; this file proves the exception type assumption
(psycopg2.errors.UniqueViolation) and the recovery/give-up behavior actually
hold against real Postgres, by forcing _unique_company_template_name (the
pre-check) to report a name as free when a colliding row already exists —
the exact situation a genuine concurrent-request race produces.
"""
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from odoo.addons.thedevkitchen_cms.controllers.cms_template_generic_controller import (
    _create_company_template_copy,
    _COPY_CREATE_RETRY_ATTEMPTS,
)

_PATCH_TARGET = (
    "odoo.addons.thedevkitchen_cms.controllers."
    "cms_template_generic_controller._unique_company_template_name"
)


class TestCmsTemplateGenericCopyRace(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Generic = self.env["thedevkitchen.cms.template.generic"].sudo()
        self.Template = self.env["thedevkitchen.cms.template"].sudo()
        self.company = self.env["res.company"].sudo().search([], limit=1)

        # Defensive cleanup (same precaution as the sibling CRUD integration
        # test — TransactionCase rolls back between test methods, but not
        # necessarily between separate `odoo --test-enable` invocations).
        self.Generic.search([("name", "like", "it_copy_race_")]).unlink()
        self.Template.search([("name", "like", "it_copy_race_")]).unlink()

        self.generic = self.Generic.create({"name": "it_copy_race_generic", "category": "landing"})
        self.env["thedevkitchen.cms.template.generic.content"].sudo().create(
            {"template_id": self.generic.id, "content": '{"content": []}'}
        )

    def test_recovers_after_one_real_collision_then_succeeds(self):
        """A row already occupies the first candidate name (simulating a
        concurrent request that won the race between the pre-check and our
        insert). _unique_company_template_name is forced to report that
        taken name as free on the first call (exactly what a genuine race
        would look like from this process's point of view), so the real
        UNIQUE constraint — not a mock — must reject the first create() with
        psycopg2.errors.UniqueViolation, and the second attempt (a name that
        really is free) must succeed."""
        colliding_name = "it_copy_race_collision"
        free_name = "it_copy_race_collision (2)"
        self.Template.create({"name": colliding_name, "category": "landing", "company_id": self.company.id})

        with patch(_PATCH_TARGET, side_effect=[colliding_name, free_name]):
            result = _create_company_template_copy(
                self.env, self.generic, colliding_name, self.company.id, source_content="{}"
            )

        self.assertIsNotNone(result, "must recover after the real collision, not give up")
        self.assertEqual(result.name, free_name)
        self.assertEqual(result.source_generic_template_id.id, self.generic.id)

        # The colliding row from "before" the race is untouched; the new
        # template is a second, distinct row.
        survivors = self.Template.search([("name", "in", [colliding_name, free_name]), ("company_id", "=", self.company.id)])
        self.assertEqual(len(survivors), 2)

    def test_gives_up_after_sustained_real_collisions(self):
        """_unique_company_template_name is forced to always report the same
        already-taken name as free (worst-case sustained contention) — every
        create() attempt must hit the real UNIQUE constraint, and after
        _COPY_CREATE_RETRY_ATTEMPTS attempts the function must return None
        (caller turns this into 409), not raise the raw UniqueViolation."""
        colliding_name = "it_copy_race_sustained"
        self.Template.create({"name": colliding_name, "category": "landing", "company_id": self.company.id})

        with patch(_PATCH_TARGET, return_value=colliding_name):
            result = _create_company_template_copy(
                self.env, self.generic, colliding_name, self.company.id, source_content="{}"
            )

        self.assertIsNone(result)
        # Only the original pre-existing row survives — no partial/orphaned
        # rows from any of the failed attempts (each wrapped in its own
        # savepoint).
        survivors = self.Template.search([("name", "=", colliding_name), ("company_id", "=", self.company.id)])
        self.assertEqual(len(survivors), 1)
