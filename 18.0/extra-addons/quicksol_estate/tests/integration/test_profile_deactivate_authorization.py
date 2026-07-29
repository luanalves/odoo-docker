# -*- coding: utf-8 -*-
"""Feature 027 FR3 -- DELETE /api/v1/profiles/<id> and the new
POST /api/v1/profiles/<id>/reactivate require owner OR admin, for ANY
profile_type. Manager/Director are explicitly excluded (see spec-idea.md,
"Mudança de Comportamento Breaking" section, for the ADR-019 +
ir.model.access.csv + Feature 009 justification).

Tests the authorization helper directly with real res.users/groups -- no
odoo.http.request mocking.
"""
from odoo.tests.common import TransactionCase
from odoo.addons.quicksol_estate.controllers.profile_api import (
    ProfileApiController,
)


class TestProfileDeactivateReactivateAuthorization(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({"name": "Seed Company 027-F5"})

        def make_user(login, group_xml_id):
            return self.env["res.users"].create(
                {
                    "name": login,
                    "login": login,
                    "company_id": self.company.id,
                    "company_ids": [(6, 0, [self.company.id])],
                    "groups_id": [(4, self.env.ref(group_xml_id).id)],
                }
            )

        self.owner = make_user(
            "owner_027f5@example.com", "quicksol_estate.group_real_estate_owner"
        )
        self.director = make_user(
            "director_027f5@example.com", "quicksol_estate.group_real_estate_director"
        )
        self.manager = make_user(
            "manager_027f5@example.com", "quicksol_estate.group_real_estate_manager"
        )
        self.agent_user = make_user(
            "agentuser_027f5@example.com", "quicksol_estate.group_real_estate_agent"
        )
        self.admin = make_user("admin_027f5@example.com", "base.group_system")
        self.controller = ProfileApiController()

    def test_owner_without_manager_group_is_authorized(self):
        """Closes the class of bug present in legacy agent_api.py: Owner
        must be authorized without needing an explicit Manager group,
        since group_real_estate_owner does NOT imply
        group_real_estate_manager in this project's security/groups.xml."""
        self.assertFalse(
            self.owner.has_group("quicksol_estate.group_real_estate_manager")
        )
        self.assertTrue(
            self.controller._user_can_deactivate_or_reactivate_profile(self.owner)
        )

    def test_admin_is_authorized(self):
        self.assertTrue(
            self.controller._user_can_deactivate_or_reactivate_profile(self.admin)
        )

    def test_manager_is_not_authorized(self):
        self.assertFalse(
            self.controller._user_can_deactivate_or_reactivate_profile(self.manager)
        )

    def test_director_is_not_authorized(self):
        """Director inherits every Manager permission on profile/agent CRUD
        elsewhere in this project, but NOT this one -- deliberately, per
        the ADR-019/ir.model.access.csv res.users-is-Owner-only rule."""
        self.assertFalse(
            self.controller._user_can_deactivate_or_reactivate_profile(self.director)
        )

    def test_agent_is_not_authorized(self):
        self.assertFalse(
            self.controller._user_can_deactivate_or_reactivate_profile(self.agent_user)
        )
