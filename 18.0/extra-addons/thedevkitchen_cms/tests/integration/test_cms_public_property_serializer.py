# -*- coding: utf-8 -*-
"""
Integration tests for cms_public_property_serializer.serialize_public_property.
"""
from odoo.tests.common import TransactionCase

FORBIDDEN_KEYS = {
    "owner",
    "owner_id",
    "agent",
    "agent_id",
    "internal_notes",
    "commission_ids",
    "total_commission",
    "document_ids",
    "documents",
    "street",
    "street_number",
    "complement",
    "zip_code",
    "latitude",
    "longitude",
    "company",
}


class TestSerializePublicProperty(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.thedevkitchen_cms.services.cms_public_property_serializer import (
            serialize_public_property,
        )

        cls.serialize_public_property = staticmethod(serialize_public_property)

        cls.company = cls.env["res.company"].create(
            {"name": "Serializer Test Co", "cnpj": "55.555.555/0001-91"}
        )
        cls.property_type = cls.env["real.estate.property.type"].create(
            {"name": "it_serializer_house"}
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
        owner = cls.env["real.estate.property.owner"].create(
            {"name": "Serializer Test Owner", "email": "owner@example.com"}
        )

        cls.property_with_image = cls.env["real.estate.property"].create(
            {
                "name": "it_serializer_prop_with_image",
                "company_id": cls.company.id,
                "property_type_id": cls.property_type.id,
                "location_type_id": cls.location_type.id,
                "state_id": cls.state.id,
                "owner_id": owner.id,
                "zip_code": "01310-100",
                "city": "Sao Paulo",
                "street": "Av. Paulista",
                "street_number": "1000",
                "area": 80.0,
                "price": 350000.0,
                "for_sale": True,
                "property_status": "available",
                "publish_website": True,
                "description_short": "A lovely test property",
                # 1x1 transparent PNG, base64-encoded
                "image": (
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
                    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
                ),
            }
        )
        cls.property_no_image = cls.env["real.estate.property"].create(
            {
                "name": "it_serializer_prop_no_image",
                "company_id": cls.company.id,
                "property_type_id": cls.property_type.id,
                "location_type_id": cls.location_type.id,
                "state_id": cls.state.id,
                "zip_code": "01310-100",
                "city": "Sao Paulo",
                "street": "Av. Paulista",
                "street_number": "1000",
                "area": 60.0,
                "price": 200000.0,
                "for_sale": True,
                "property_status": "sold",
                "publish_website": True,
            }
        )

    def test_image_url_populated_when_image_set(self):
        payload = self.serialize_public_property(self.property_with_image, "it-slug")
        self.assertEqual(
            f"/api/v1/public/properties/it-slug/{self.property_with_image.id}/image",
            payload["image_url"],
        )

    def test_image_url_null_when_no_image(self):
        payload = self.serialize_public_property(self.property_no_image, "it-slug")
        self.assertIsNone(payload["image_url"])

    def test_expected_keys_present(self):
        payload = self.serialize_public_property(self.property_with_image, "it-slug")
        expected_keys = {
            "id",
            "reference_code",
            "name",
            "property_status",
            "for_sale",
            "for_rent",
            "price",
            "rent_price",
            "currency",
            "area",
            "num_rooms",
            "num_bathrooms",
            "num_parking",
            "city",
            "neighborhood",
            "state",
            "property_type",
            "image_url",
            "description_short",
            "create_date",
        }
        self.assertEqual(expected_keys, set(payload.keys()))

    def test_no_pii_or_internal_fields_leaked(self):
        payload = self.serialize_public_property(self.property_with_image, "it-slug")
        leaked = FORBIDDEN_KEYS & set(payload.keys())
        self.assertFalse(leaked, f"Forbidden keys leaked into public payload: {leaked}")

    def test_property_type_and_state_are_nested_objects(self):
        payload = self.serialize_public_property(self.property_with_image, "it-slug")
        self.assertEqual(
            {"id": self.property_type.id, "name": "it_serializer_house"},
            payload["property_type"],
        )
        self.assertEqual(self.state.id, payload["state"]["id"])
