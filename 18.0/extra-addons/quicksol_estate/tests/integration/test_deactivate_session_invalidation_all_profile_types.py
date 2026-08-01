# -*- coding: utf-8 -*-
"""Feature 027 -- session invalidation on profile deactivation, exercised
across every profile_type that can have a linked res.users (not just
'agent', which was the only type this was ever tested against before this
feature widened DELETE /profiles/<id> to cover every profile_type). The
underlying mechanism (thedevkitchen_apigateway/models/api_session.py::
write() invalidating the Redis cache entry synchronously, and
services/session_validator.py::validate() falling back to the DB and
finding is_active=False) is NOT introduced by this feature -- see
specs/023-redis-session-cache/spec.md for its origin. This test proves the
DB-level cascade write reaches every profile_type's linked session; the
Redis-cache-miss-then-401 behavior itself is Feature 023's own test
coverage and is not re-tested here.
"""
from odoo.tests.common import TransactionCase
from odoo.addons.quicksol_estate.controllers.profile_api import (
    ProfileApiController,
)

PROFILE_TYPES_WITH_USER = [
    "agent",
    "manager",
    "director",
    "owner",
    "tenant",
    "receptionist",
]

# NOTE: the brief's original CPF literals (f"1112223339{suffix % 10}" for
# suffix in 100..105, and "99988877766") failed real validate_docbr.CPF()
# checksum validation -- verified in-container, consistent with every prior
# test-adding task on this branch (Tasks 2, 3, 4, 6). Replaced with
# checksum-valid CPFs generated and verified in-container.
VALID_CPFS = [
    "46903897135",
    "48546645841",
    "55599919455",
    "75679811570",
    "76471210493",
    "89096414446",
]
NO_LOGIN_VALID_CPF = "93013219394"


class TestDeactivateInvalidatesSessionAcrossProfileTypes(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({"name": "Seed Company 027-F7"})
        self.controller = ProfileApiController()

    def _make_profile_with_user_and_session(self, profile_type_code, suffix, document):
        ptype = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", profile_type_code)], limit=1
        )
        user = self.env["res.users"].create(
            {
                "name": f"Session User {suffix}",
                "login": f"session_{suffix}_027f7@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
            }
        )
        profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": f"Session Profile {suffix}",
                "company_id": self.company.id,
                "profile_type_id": ptype.id,
                "document": document,
                "email": f"session_{suffix}_027f7@example.com",
                "birthdate": "1990-01-01",
                "partner_id": user.partner_id.id,
            }
        )
        session = self.env["thedevkitchen.api.session"].create(
            {
                "user_id": user.id,
                "session_id": f"session_027f7_{suffix}",
                "is_active": True,
            }
        )
        return profile, user, session

    def test_deactivate_invalidates_session_for_every_profile_type(self):
        for i, profile_type_code in enumerate(PROFILE_TYPES_WITH_USER):
            with self.subTest(profile_type=profile_type_code):
                profile, user, session = self._make_profile_with_user_and_session(
                    profile_type_code, suffix=100 + i, document=VALID_CPFS[i]
                )
                self.controller._deactivate_profile_cascade(profile)
                self.assertFalse(
                    user.active,
                    f"res.users should be deactivated for profile_type={profile_type_code}",
                )
                self.assertFalse(
                    session.is_active,
                    f"session should be invalidated for profile_type={profile_type_code}",
                )

    def test_deactivate_profile_without_linked_user_does_not_error(self):
        """Profile with no partner_id/res.users at all (never invited) --
        deactivation must complete without attempting session invalidation."""
        ptype = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "tenant")], limit=1
        )
        profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "No Login Tenant 027F7",
                "company_id": self.company.id,
                "profile_type_id": ptype.id,
                "document": NO_LOGIN_VALID_CPF,
                "email": "nologin_027f7@example.com",
                "birthdate": "1990-01-01",
            }
        )
        self.controller._deactivate_profile_cascade(profile)
        self.assertFalse(profile.active)


if __name__ == "__main__":
    pass
