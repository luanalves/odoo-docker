# -*- coding: utf-8 -*-
"""
Integration tests for cms_slug_service.resolve_company_by_slug.
"""
from odoo.tests.common import TransactionCase


class TestCmsSlugService(TransactionCase):

    def setUp(self):
        super().setUp()
        from odoo.addons.thedevkitchen_cms.services.cms_slug_service import (
            resolve_company_by_slug,
        )
        self.resolve_company_by_slug = resolve_company_by_slug

        self.company = self.env["res.company"].create(
            {"name": "Slug Service Test Co", "cnpj": "44.444.444/0001-53"}
        )
        self.env["thedevkitchen.cms.settings"].create(
            {"company_id": self.company.id, "company_slug": "it-slug-service-co"}
        )

    def test_resolves_known_slug(self):
        company_id = self.resolve_company_by_slug(self.env, "it-slug-service-co")
        self.assertEqual(company_id, self.company.id)

    def test_returns_none_for_unknown_slug(self):
        company_id = self.resolve_company_by_slug(self.env, "it-slug-does-not-exist")
        self.assertIsNone(company_id)
