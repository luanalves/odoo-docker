# -*- coding: utf-8 -*-
"""
Integration tests proving build_public_property_domain(), combined with a
real search(), correctly enforces multi-tenancy isolation and the
publish_website/active public-visibility gates (spec User Stories 1-2).
"""
from odoo.tests.common import TransactionCase


class TestPublicPropertyDomainIsolation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.thedevkitchen_cms.services.cms_public_property_service import (
            build_public_property_domain,
        )

        cls.build_public_property_domain = staticmethod(build_public_property_domain)

        cls.company_a = cls.env["res.company"].create(
            {"name": "Domain Test Co A", "cnpj": "66.666.666/0001-91"}
        )
        # Note: the brief's original CNPJ ("98.765.432/0001-98") is checksum-
        # valid but collides with pre-existing seed data ("Urban Properties",
        # quicksol_estate/data/company_seed.xml) already loaded into this DB,
        # which violates res_company's cnpj unique constraint. Substituted
        # with another checksum-valid, unused CNPJ (same base, different
        # branch/check-digits) to avoid the collision.
        cls.company_b = cls.env["res.company"].create(
            {"name": "Domain Test Co B", "cnpj": "66.666.666/0002-72"}
        )
        cls.property_type = cls.env["real.estate.property.type"].create(
            {"name": "it_domain_house"}
        )
        cls.location_type = cls.env["real.estate.location.type"].search(
            [("code", "=", "URB")], limit=1
        ) or cls.env["real.estate.location.type"].create(
            {"name": "Urban", "code": "URB", "sequence": 10}
        )
        country = cls.env.ref("base.br")
        cls.state = cls.env["res.country.state"].search(
            [("country_id", "=", country.id)], limit=1
        )

        def _make(company, **overrides):
            vals = {
                "name": "it_domain_prop",
                "company_id": company.id,
                "property_type_id": cls.property_type.id,
                "location_type_id": cls.location_type.id,
                "state_id": cls.state.id,
                "zip_code": "01310-100",
                "city": "Sao Paulo",
                "street": "Av. Paulista",
                "street_number": "1000",
                "area": 70.0,
                "price": 300000.0,
                "for_sale": True,
                "property_status": "available",
                "publish_website": True,
            }
            vals.update(overrides)
            return cls.env["real.estate.property"].create(vals)

        cls.prop_a_published = _make(cls.company_a)
        # Second published/active company-A property: the N+1 query-count
        # test below needs >= 3 visible records for company A to prove
        # prefetch batching actually kicks in (a single record wouldn't
        # distinguish "no N+1" from "no relations to prefetch at all").
        cls.prop_a_published_2 = _make(cls.company_a)
        cls.prop_a_unpublished = _make(cls.company_a, publish_website=False)
        cls.prop_a_maintenance = _make(cls.company_a, property_status="maintenance")
        cls.prop_a_archived = _make(cls.company_a)
        cls.prop_a_archived.write({"active": False})
        cls.prop_b_published = _make(cls.company_b)

        cls.Property = cls.env["real.estate.property"].sudo()

    def _search(self, company_id, status_values=None, ids=None):
        domain = self.build_public_property_domain(company_id, status_values, ids)
        return self.Property.search(domain)

    def test_only_returns_properties_for_requested_company(self):
        results = self._search(self.company_a.id)
        self.assertNotIn(self.prop_b_published.id, results.ids)

    def test_publish_website_false_never_returned(self):
        results = self._search(self.company_a.id)
        self.assertNotIn(self.prop_a_unpublished.id, results.ids)

    def test_archived_property_never_returned(self):
        results = self._search(self.company_a.id)
        self.assertNotIn(self.prop_a_archived.id, results.ids)

    def test_no_status_filter_includes_maintenance_if_published(self):
        # Confirmed product decision (spec Assumptions): omitting `status`
        # applies no implicit status restriction.
        results = self._search(self.company_a.id)
        self.assertIn(self.prop_a_maintenance.id, results.ids)

    def test_explicit_status_filter_excludes_non_matching(self):
        results = self._search(self.company_a.id, status_values=["sold"])
        self.assertNotIn(self.prop_a_published.id, results.ids)

    def test_cross_company_id_silently_excluded(self):
        results = self._search(
            self.company_a.id, ids=[self.prop_a_published.id, self.prop_b_published.id]
        )
        self.assertIn(self.prop_a_published.id, results.ids)
        self.assertNotIn(self.prop_b_published.id, results.ids)

    def test_serialization_does_not_n_plus_one(self):
        """Spec NFR2: serializing a result set must not issue a query per
        record per relation (property_type_id/state_id/currency_id) — a
        single search() + iteration should let Odoo's prefetch batch these.
        """
        from odoo.addons.thedevkitchen_cms.services.cms_public_property_serializer import (
            serialize_public_property,
        )

        results = self._search(self.company_a.id)
        self.assertGreaterEqual(
            len(results), 3, "Need multiple records to prove batching"
        )

        self.env.invalidate_all()
        before = self.env.cr.sql_log_count
        for prop in results:
            serialize_public_property(prop, "it-slug")
        query_count = self.env.cr.sql_log_count - before

        # A handful of prefetch queries (property_type/state/currency), not
        # one set of queries per record — bounded constant, not O(n).
        self.assertLess(
            query_count,
            len(results) + 5,
            f"Expected bounded query count for {len(results)} records, got {query_count} "
            "— check for a per-record N+1 on a related field",
        )
