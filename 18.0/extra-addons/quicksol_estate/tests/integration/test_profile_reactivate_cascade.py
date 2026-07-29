# -*- coding: utf-8 -*-
"""Feature 027 FR2 -- POST /api/v1/profiles/<id>/reactivate cascade:
profile -> agent -> user reactivated atomically, deactivation_date/reason
cleared, and NO thedevkitchen.api.session record is ever restored.
"""
from odoo.tests.common import TransactionCase
from odoo.addons.quicksol_estate.controllers.profile_api import (
    ProfileApiController,
)


class TestReactivateProfileCascade(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({"name": "Seed Company 027-F6"})
        self.agent_type = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "agent")], limit=1
        )
        self.tenant_type = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "tenant")], limit=1
        )
        self.user = self.env["res.users"].create(
            {
                "name": "Reactivate Test User",
                "login": "reactivate_027f6@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
            }
        )
        self.profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "Agent To Reactivate",
                "company_id": self.company.id,
                "profile_type_id": self.agent_type.id,
                "document": "11122233396",
                "email": "reactivateagent027@example.com",
                "birthdate": "1990-01-01",
                "partner_id": self.user.partner_id.id,
            }
        )
        self.agent = self.env["real.estate.agent"].create(
            {"profile_id": self.profile.id, "user_id": self.user.id}
        )
        self.session = self.env["thedevkitchen.api.session"].create(
            {
                "user_id": self.user.id,
                "session_id": "reactivate027f6sessionid",
                "is_active": True,
            }
        )
        # Simulate a prior deactivation via the Task 5 helper (proves the
        # two cascades are true inverses of each other).
        self.controller = ProfileApiController()
        self.controller._deactivate_profile_cascade(self.profile, reason="test setup")
        self.session.write({"is_active": False})

    def test_reactivate_cascades_to_agent_and_user(self):
        self.controller._reactivate_profile_cascade(self.profile)
        self.assertTrue(self.profile.active)
        self.assertIsNone(self.profile.deactivation_date or None)
        self.assertFalse(self.profile.deactivation_reason)
        self.assertTrue(self.agent.active)
        self.assertFalse(self.agent.deactivation_date)
        self.assertTrue(self.user.active)

    def test_reactivate_does_not_restore_session(self):
        """FR2.6/NFR1: reactivation must never touch
        thedevkitchen.api.session -- a previously invalidated session stays
        invalidated; user must log in again for a new one."""
        self.controller._reactivate_profile_cascade(self.profile)
        self.assertFalse(self.session.is_active)

    def test_reactivate_non_agent_profile_skips_agent_cascade(self):
        tenant_profile = self.env["thedevkitchen.estate.profile"].create(
            {
                "name": "Tenant To Reactivate",
                "company_id": self.company.id,
                "profile_type_id": self.tenant_type.id,
                "document": "27448487434",
                "email": "reactivatetenant027@example.com",
                "birthdate": "1990-01-01",
                "active": False,
                "deactivation_date": "2026-01-01",
                "deactivation_reason": "pre-deactivated seed",
            }
        )
        # Should not raise even though there's no real.estate.agent row.
        self.controller._reactivate_profile_cascade(tenant_profile)
        self.assertTrue(tenant_profile.active)


if __name__ == "__main__":
    pass
