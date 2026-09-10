# -*- coding: utf-8 -*-
"""
Verifies the composite index backing the public property listing hot path
(Feature 029: company_id + publish_website + active + create_date) exists.
"""
from odoo.tests.common import TransactionCase


class TestPropertyPublicListingIndex(TransactionCase):

    def test_composite_index_exists(self):
        self.env.cr.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'real_estate_property'
            AND indexname = 'real_estate_property_public_listing_idx'
            """
        )
        row = self.env.cr.fetchone()
        self.assertIsNotNone(
            row, "Expected index 'real_estate_property_public_listing_idx' to exist"
        )
