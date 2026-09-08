# -*- coding: utf-8 -*-
"""
Unit tests for cms_public_property_service — pure functions, no DB.
"""
import unittest

from odoo.addons.thedevkitchen_cms.services.cms_public_property_service import (
    PUBLIC_PROPERTY_STATUSES,
    build_public_property_domain,
    parse_ids_filter,
    parse_limit,
    parse_sort,
    parse_status_filter,
)


class TestParseStatusFilter(unittest.TestCase):
    def test_omitted_returns_no_filter(self):
        self.assertEqual((None, True), parse_status_filter(None))
        self.assertEqual((None, True), parse_status_filter(""))

    def test_single_valid_value(self):
        self.assertEqual((["available"], True), parse_status_filter("available"))

    def test_multiple_valid_values(self):
        values, ok = parse_status_filter("available,reserved")
        self.assertTrue(ok)
        self.assertEqual(["available", "reserved"], values)

    def test_rejects_out_of_scope_model_value(self):
        # 'maintenance' is a real property_status value but not public-facing
        self.assertEqual((None, False), parse_status_filter("maintenance"))

    def test_rejects_unknown_token(self):
        self.assertEqual((None, False), parse_status_filter("not-a-status"))

    def test_rejects_mixed_valid_and_invalid(self):
        self.assertEqual((None, False), parse_status_filter("available,maintenance"))


class TestParseIdsFilter(unittest.TestCase):
    def test_omitted_returns_no_filter(self):
        self.assertEqual((None, True), parse_ids_filter(None))

    def test_parses_comma_separated_ints(self):
        self.assertEqual(([12, 45, 90], True), parse_ids_filter("12,45,90"))

    def test_rejects_non_integer_token(self):
        self.assertEqual((None, False), parse_ids_filter("12,abc,90"))


class TestParseSort(unittest.TestCase):
    def test_default_is_newest(self):
        self.assertEqual(("create_date desc", True), parse_sort(None))

    def test_newest_explicit(self):
        self.assertEqual(("create_date desc", True), parse_sort("newest"))

    def test_oldest(self):
        self.assertEqual(("create_date asc", True), parse_sort("oldest"))

    def test_rejects_unknown_value(self):
        self.assertEqual((None, False), parse_sort("random"))


class TestParseLimit(unittest.TestCase):
    def test_default_is_20(self):
        self.assertEqual((20, True), parse_limit(None))
        self.assertEqual((20, True), parse_limit(""))

    def test_clamps_above_max_to_100(self):
        self.assertEqual((100, True), parse_limit("500"))

    def test_within_range_passes_through(self):
        self.assertEqual((50, True), parse_limit("50"))

    def test_rejects_non_integer(self):
        self.assertEqual((None, False), parse_limit("abc"))

    def test_rejects_zero_or_negative(self):
        self.assertEqual((None, False), parse_limit("0"))
        self.assertEqual((None, False), parse_limit("-5"))


class TestBuildPublicPropertyDomain(unittest.TestCase):
    def test_mandatory_filters_only(self):
        domain = build_public_property_domain(7)
        self.assertEqual(
            [
                ("company_id", "=", 7),
                ("active", "=", True),
                ("publish_website", "=", True),
            ],
            domain,
        )

    def test_adds_status_filter_when_provided(self):
        domain = build_public_property_domain(7, status_values=["available", "sold"])
        self.assertIn(("property_status", "in", ["available", "sold"]), domain)

    def test_adds_ids_filter_when_provided(self):
        domain = build_public_property_domain(7, ids=[1, 2, 3])
        self.assertIn(("id", "in", [1, 2, 3]), domain)

    def test_public_statuses_constant_has_exactly_four_values(self):
        self.assertEqual(
            {"available", "rented", "sold", "reserved"}, PUBLIC_PROPERTY_STATUSES
        )


if __name__ == "__main__":
    unittest.main()
