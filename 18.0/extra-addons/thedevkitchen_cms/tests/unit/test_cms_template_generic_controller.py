# -*- coding: utf-8 -*-
"""
Unit tests for the pure helpers backing cms_template_generic_controller.py.
The HTTP route methods themselves (list_generic_templates, get_generic_template,
copy_generic_template) require a live Odoo request/env and are exercised by
integration_tests/test_us028_cms_generic_templates.sh instead — consistent
with how cms_template_controller.py's routes have never carried their own
unit tests in this module.
"""
import unittest
from unittest.mock import MagicMock

from psycopg2.errors import UniqueViolation

from odoo.addons.thedevkitchen_cms.controllers.cms_template_generic_controller import (
    GENERIC_TEMPLATE_MANAGEMENT_ROLES,
    _serialize_generic_template,
    _clamp_pagination_params,
    _build_copy_create_vals,
    _unique_company_template_name,
    _create_company_template_copy,
    _COPY_CREATE_RETRY_ATTEMPTS,
)
from odoo.addons.thedevkitchen_cms.controllers.cms_template_controller import (
    TEMPLATE_MANAGEMENT_ROLES,
)


class TestGenericTemplateManagementRoles(unittest.TestCase):

    def test_roles_match_cms_template_controller_exactly(self):
        """Must be the actual same object/value as cms_template_controller.py's
        TEMPLATE_MANAGEMENT_ROLES constant (imported, not redigitized), to
        avoid authorization drift between sibling controllers (spec Non-Goal:
        'não redigitar a lista'). Comparing against the real source of truth
        instead of a hardcoded literal means this test actually catches drift
        if cms_template_controller.py's roles ever change."""
        self.assertEqual(GENERIC_TEMPLATE_MANAGEMENT_ROLES, TEMPLATE_MANAGEMENT_ROLES)

    def test_agent_role_not_authorized(self):
        self.assertNotIn("agent", GENERIC_TEMPLATE_MANAGEMENT_ROLES)

    def test_tenant_role_not_authorized(self):
        self.assertNotIn("tenant", GENERIC_TEMPLATE_MANAGEMENT_ROLES)


class TestClampPaginationParams(unittest.TestCase):
    """Unit tests for pagination parameter validation.

    Validates the fix for the review finding: limit=0 must be rejected
    to prevent Odoo's ORM from omitting the SQL LIMIT clause entirely.
    """

    def test_limit_zero_raises_error(self):
        """limit=0 must raise ValueError, not be silently passed to ORM."""
        with self.assertRaises(ValueError) as cm:
            _clamp_pagination_params(limit=0, offset=0)
        self.assertIn("limit must be positive", str(cm.exception))

    def test_negative_limit_raises_error(self):
        """Negative limit must raise ValueError."""
        with self.assertRaises(ValueError) as cm:
            _clamp_pagination_params(limit=-5, offset=0)
        self.assertIn("limit must be positive", str(cm.exception))

    def test_negative_offset_raises_error(self):
        """Negative offset must raise ValueError."""
        with self.assertRaises(ValueError) as cm:
            _clamp_pagination_params(limit=10, offset=-1)
        self.assertIn("offset must be non-negative", str(cm.exception))

    def test_valid_limit_within_range(self):
        """limit=25 (within range) must pass through unchanged."""
        clamped_limit, clamped_offset = _clamp_pagination_params(limit=25, offset=0)
        self.assertEqual(clamped_limit, 25)
        self.assertEqual(clamped_offset, 0)

    def test_limit_one_is_minimum_valid(self):
        """limit=1 must be accepted (the minimum sane limit)."""
        clamped_limit, clamped_offset = _clamp_pagination_params(limit=1, offset=0)
        self.assertEqual(clamped_limit, 1)

    def test_limit_at_hard_cap(self):
        """limit=50 (at hard cap) must pass through unchanged."""
        clamped_limit, clamped_offset = _clamp_pagination_params(limit=50, offset=0)
        self.assertEqual(clamped_limit, 50)

    def test_limit_exceeding_hard_cap_is_clamped(self):
        """limit=999 must be clamped to 50."""
        clamped_limit, clamped_offset = _clamp_pagination_params(limit=999, offset=0)
        self.assertEqual(clamped_limit, 50)

    def test_large_offset_is_allowed(self):
        """offset=10000 must be allowed (pagination can go deep)."""
        clamped_limit, clamped_offset = _clamp_pagination_params(limit=10, offset=10000)
        self.assertEqual(clamped_limit, 10)
        self.assertEqual(clamped_offset, 10000)

    def test_offset_zero_is_allowed(self):
        """offset=0 must be allowed."""
        clamped_limit, clamped_offset = _clamp_pagination_params(limit=10, offset=0)
        self.assertEqual(clamped_offset, 0)


class TestSerializeGenericTemplate(unittest.TestCase):

    def _make_template(self, content=None):
        tpl = MagicMock()
        tpl.id = 1
        tpl.name = "seed_generic_landing"
        tpl.category = "landing"
        tpl.active = True
        tpl.create_date.isoformat.return_value = "2026-09-01T10:00:00"
        tpl.write_date.isoformat.return_value = "2026-09-01T10:00:00"
        if content is not None:
            content_record = MagicMock()
            content_record.content = content
            tpl.content_ids = [content_record]
        else:
            tpl.content_ids = []
        return tpl

    def test_list_serialization_excludes_content(self):
        """Listing must never include 'content' — avoids N+1 and heavy payloads."""
        tpl = self._make_template(content='{"content": []}')
        data = _serialize_generic_template(tpl, include_content=False)
        self.assertNotIn("content", data)

    def test_list_serialization_excludes_company_id(self):
        """Generic templates have no company_id — must never appear in the payload."""
        tpl = self._make_template()
        data = _serialize_generic_template(tpl, include_content=False)
        self.assertNotIn("company_id", data)

    def test_detail_serialization_includes_content(self):
        tpl = self._make_template(content='{"content": []}')
        data = _serialize_generic_template(tpl, include_content=True)
        self.assertEqual(data["content"], '{"content": []}')

    def test_detail_serialization_content_none_when_no_content_record(self):
        tpl = self._make_template(content=None)
        data = _serialize_generic_template(tpl, include_content=True)
        self.assertIsNone(data["content"])

    def test_serialization_includes_core_fields(self):
        tpl = self._make_template()
        data = _serialize_generic_template(tpl)
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["name"], "seed_generic_landing")
        self.assertEqual(data["category"], "landing")
        self.assertTrue(data["active"])


class TestBuildCopyCreateVals(unittest.TestCase):

    def _make_generic(self, id_=1, category="landing"):
        generic = MagicMock()
        generic.id = id_
        generic.category = category
        return generic

    def test_vals_use_explicit_company_id_not_payload(self):
        """ADR-008: company_id always comes from the session-derived argument,
        never from request payload — this function's signature doesn't even
        accept a raw payload dict, only the already-resolved company_id int."""
        generic = self._make_generic()
        vals = _build_copy_create_vals(generic, "Landing Padrão", company_id=42)
        self.assertEqual(vals["company_id"], 42)

    def test_vals_set_source_generic_template_id(self):
        generic = self._make_generic(id_=7)
        vals = _build_copy_create_vals(generic, "Landing Padrão", company_id=1)
        self.assertEqual(vals["source_generic_template_id"], 7)

    def test_vals_copy_category_from_generic(self):
        generic = self._make_generic(category="property")
        vals = _build_copy_create_vals(generic, "Some Name", company_id=1)
        self.assertEqual(vals["category"], "property")

    def test_vals_use_given_name(self):
        generic = self._make_generic()
        vals = _build_copy_create_vals(generic, "Custom Name", company_id=1)
        self.assertEqual(vals["name"], "Custom Name")

    def test_vals_only_contain_whitelisted_keys(self):
        generic = self._make_generic()
        vals = _build_copy_create_vals(generic, "X", company_id=1)
        self.assertEqual(set(vals.keys()), {"name", "category", "company_id", "source_generic_template_id"})


class TestUniqueCompanyTemplateName(unittest.TestCase):

    def _make_env(self, existing_names):
        """Mock env['thedevkitchen.cms.template'].sudo().search_count() to
        report a conflict for any name already in `existing_names`."""
        template_model = MagicMock()

        # domain is a list of tuples like [("name", "=", candidate), ("company_id", "=", company_id)]
        def _search_count_from_domain(domain):
            name = next(v for (f, op, v) in domain if f == "name")
            return 1 if name in existing_names else 0

        template_model.sudo.return_value.search_count.side_effect = _search_count_from_domain
        env = {"thedevkitchen.cms.template": template_model}
        return env

    def test_returns_base_name_when_no_conflict(self):
        env = self._make_env(existing_names=set())
        result = _unique_company_template_name(env, "Landing Padrão", company_id=1)
        self.assertEqual(result, "Landing Padrão")

    def test_applies_suffix_on_single_conflict(self):
        env = self._make_env(existing_names={"Landing Padrão"})
        result = _unique_company_template_name(env, "Landing Padrão", company_id=1)
        self.assertEqual(result, "Landing Padrão (2)")

    def test_applies_next_suffix_when_first_suffix_also_taken(self):
        env = self._make_env(existing_names={"Landing Padrão", "Landing Padrão (2)"})
        result = _unique_company_template_name(env, "Landing Padrão", company_id=1)
        self.assertEqual(result, "Landing Padrão (3)")

    def test_returns_none_when_attempts_exhausted(self):
        # Base name + suffixes (2..101) all taken -> 100 total candidates exhausted.
        existing = {"Landing Padrão"} | {f"Landing Padrão ({n})" for n in range(2, 102)}
        env = self._make_env(existing_names=existing)
        result = _unique_company_template_name(env, "Landing Padrão", company_id=1)
        self.assertIsNone(result)


class TestCreateCompanyTemplateCopy(unittest.TestCase):
    """PR #31 review (P1): the previous two-step
    "check name via search_count, then create()" was not atomic — a
    concurrent request could create the winning name between the two steps,
    surfacing as an unhandled psycopg2.errors.UniqueViolation -> 500 instead
    of the documented retry/409 behavior. These tests verify the retry
    control flow with mocks; the actual DB-level race is additionally
    covered by a TransactionCase in tests/integration/ (real UNIQUE
    constraint, not a simulated exception)."""

    def _make_generic(self, id_=1, category="landing"):
        generic = MagicMock()
        generic.id = id_
        generic.category = category
        return generic

    def _make_env(self, create_side_effect, existing_names=frozenset()):
        template_model = MagicMock()
        content_model = MagicMock()

        def _search_count_from_domain(domain):
            name = next(v for (f, op, v) in domain if f == "name")
            return 1 if name in existing_names else 0

        template_model.sudo.return_value.search_count.side_effect = _search_count_from_domain
        template_model.sudo.return_value.create.side_effect = create_side_effect

        env = MagicMock()
        env.__getitem__.side_effect = lambda key: {
            "thedevkitchen.cms.template": template_model,
            "thedevkitchen.cms.template.content": content_model,
        }[key]
        # Real cr.savepoint() does not swallow exceptions raised inside the
        # `with` block — it rolls back to the savepoint and re-raises. A bare
        # MagicMock's __exit__ returns a (truthy) MagicMock by default, which
        # would incorrectly suppress the exception, so pin it to False.
        env.cr.savepoint.return_value.__exit__ = MagicMock(return_value=False)
        return env, template_model, content_model

    def test_succeeds_on_first_attempt_when_no_conflict(self):
        generic = self._make_generic()
        new_template = MagicMock(id=99)
        env, template_model, content_model = self._make_env(create_side_effect=[new_template])

        result = _create_company_template_copy(env, generic, "Landing", company_id=1, source_content="{}")

        self.assertIs(result, new_template)
        self.assertEqual(template_model.sudo.return_value.create.call_count, 1)
        content_model.sudo.return_value.create.assert_called_once_with(
            {"template_id": 99, "content": "{}"}
        )

    def test_retries_on_unique_violation_then_succeeds(self):
        """A concurrent request wins the race on the first attempt (real
        UniqueViolation from the DB, not a search_count conflict this
        process could have seen in advance) — the second attempt must
        succeed rather than propagating the exception as a 500."""
        generic = self._make_generic()
        new_template = MagicMock(id=100)
        env, template_model, content_model = self._make_env(
            create_side_effect=[UniqueViolation("duplicate key value"), new_template]
        )

        result = _create_company_template_copy(env, generic, "Landing", company_id=1, source_content="{}")

        self.assertIs(result, new_template)
        self.assertEqual(template_model.sudo.return_value.create.call_count, 2)

    def test_gives_up_after_max_retries(self):
        """Sustained collision on every attempt returns None (caller turns
        this into 409 generic_copy_conflict) instead of retrying forever or
        letting the exception propagate."""
        generic = self._make_generic()
        env, template_model, content_model = self._make_env(
            create_side_effect=UniqueViolation("duplicate key value")
        )

        result = _create_company_template_copy(env, generic, "Landing", company_id=1, source_content="{}")

        self.assertIsNone(result)
        self.assertEqual(template_model.sudo.return_value.create.call_count, _COPY_CREATE_RETRY_ATTEMPTS)

    def test_returns_none_immediately_when_no_free_name_at_all(self):
        """When _unique_company_template_name itself can't find a free name
        (100 candidates all taken), _create_company_template_copy must not
        attempt create() at all."""
        existing = {"Landing"} | {f"Landing ({n})" for n in range(2, 102)}
        generic = self._make_generic()
        env, template_model, content_model = self._make_env(
            create_side_effect=AssertionError("create() should never be called"),
            existing_names=existing,
        )

        result = _create_company_template_copy(env, generic, "Landing", company_id=1, source_content="{}")

        self.assertIsNone(result)
        template_model.sudo.return_value.create.assert_not_called()

    def test_other_exceptions_propagate_unchanged(self):
        """A non-UniqueViolation error (e.g. a different constraint, or a
        genuine bug) must propagate to the caller, not be silently retried
        or swallowed — only the specific race this fix targets is caught."""
        generic = self._make_generic()
        env, template_model, content_model = self._make_env(create_side_effect=ValueError("boom"))

        with self.assertRaises(ValueError):
            _create_company_template_copy(env, generic, "Landing", company_id=1, source_content="{}")

        self.assertEqual(template_model.sudo.return_value.create.call_count, 1)


if __name__ == "__main__":
    unittest.main()
