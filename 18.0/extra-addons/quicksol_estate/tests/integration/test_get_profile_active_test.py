# -*- coding: utf-8 -*-
"""Feature 027 bugfix (inserted between Task 10 and Task 11): GET
/api/v1/profiles/<id> (`get_profile`) does not pass active_test=False when
searching for the profile, unlike list_profiles (profile_api.py:605-621)
and reactivate_profile. This means a deactivated profile (soft-deleted per
ADR-015) 404s from the single-GET endpoint even though it is still
correctly retrievable from the list endpoint.

`get_profile` is an @http.route-decorated method that reads
odoo.http.request directly (request.env / request.user_company_ids), so it
cannot be called without a real HTTP request the way
_deactivate_profile_cascade/_reactivate_profile_cascade can (those were
deliberately extracted to take plain recordsets). Per this project's
standing convention of not mocking odoo.http.request in tests, we instead
prove the underlying ORM search pattern the fix depends on directly: a
deactivated profile is NOT found by a default search() (no active_test
context) but IS found once .with_context(active_test=False) is applied --
exactly the change applied to get_profile in this bugfix.

Full HTTP-level verification of get_profile itself is covered by the
existing E2E script integration_tests/test_us27_s1_deactivate_profile_authz.sh.
"""
from odoo.tests.common import TransactionCase
from odoo.addons.quicksol_estate.controllers.profile_api import (
    ProfileApiController,
)


class TestGetProfileActiveTest(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create(
            {"name": "Seed Company 027-GetProfileFix"}
        )
        self.tenant_type = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "tenant")], limit=1
        )
        self.profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "Deactivated Profile For GET Test",
                "company_id": self.company.id,
                "profile_type_id": self.tenant_type.id,
                "document": "98765432100",
                "email": "getprofilefix027@example.com",
                "birthdate": "1990-01-01",
            }
        )
        self.controller = ProfileApiController()
        self.controller._deactivate_profile_cascade(
            self.profile, reason="test setup for GET active_test bug"
        )

    def test_default_search_does_not_find_deactivated_profile(self):
        """Reproduces the bug: the search pattern get_profile used BEFORE
        the fix (no active_test context) cannot find a deactivated
        profile."""
        Profile = self.env["thedevkitchen.estate.profile"]
        found = Profile.search([("id", "=", self.profile.id)], limit=1)
        self.assertFalse(
            found,
            "Default search() unexpectedly found a deactivated profile -- "
            "Odoo's implicit active=True filtering may have changed.",
        )

    def test_search_with_active_test_false_finds_deactivated_profile(self):
        """Proves the fix: the search pattern get_profile uses AFTER the
        fix (.with_context(active_test=False), matching list_profiles)
        finds the deactivated profile."""
        Profile = self.env["thedevkitchen.estate.profile"]
        found = Profile.with_context(active_test=False).search(
            [("id", "=", self.profile.id)], limit=1
        )
        self.assertTrue(found)
        self.assertEqual(found.id, self.profile.id)
        self.assertFalse(found.active)


if __name__ == "__main__":
    pass
