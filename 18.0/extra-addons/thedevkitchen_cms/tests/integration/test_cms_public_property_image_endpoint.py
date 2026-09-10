# -*- coding: utf-8 -*-
"""
Integration test proving the public property image endpoint's 200/
byte-streaming success path actually works — this was previously only
covered by 404 tests (no image attachment existed anywhere in test data).
"""
from unittest.mock import Mock

from odoo.tests.common import TransactionCase


class TestPublicPropertyImageEndpoint(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create(
            {"name": "Image Endpoint Test Co", "cnpj": "66.666.666/0002-72"}
        )
        cls.env["thedevkitchen.cms.settings"].create(
            {"company_id": cls.company.id, "company_slug": "it-image-endpoint-co"}
        )
        cls.property_type = cls.env["real.estate.property.type"].create(
            {"name": "it_image_endpoint_house"}
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
        cls.property_with_image = cls.env["real.estate.property"].create(
            {
                "name": "it_image_endpoint_prop",
                "company_id": cls.company.id,
                "property_type_id": cls.property_type.id,
                "location_type_id": cls.location_type.id,
                "state_id": cls.state.id,
                "zip_code": "01310-100",
                "city": "Sao Paulo",
                "street": "Av. Paulista",
                "street_number": "1000",
                "area": 80.0,
                "price": 350000.0,
                "for_sale": True,
                "property_status": "available",
                "publish_website": True,
                # 1x1 transparent PNG, base64-encoded
                "image": (
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
                    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
                ),
            }
        )

    def test_image_endpoint_streams_real_bytes(self):
        import odoo.addons.thedevkitchen_cms.controllers.cms_public_property_controller as controller_module

        # NOTE: odoo.http.request is a werkzeug LocalProxy backed by a
        # context-var. Outside of an active HTTP request (as in this
        # TransactionCase), even reading an attribute off it via
        # unittest.mock.patch()'s internal introspection
        # (_is_async_obj -> hasattr(obj, "__func__")) raises
        # "RuntimeError: object is not bound". So we bypass mock.patch's
        # auto-detection entirely and swap the module-level name directly.
        #
        # We also call the undecorated controller method directly (via
        # __wrapped__, set by functools.wraps on both @http.route and
        # @require_jwt) so this test exercises only the controller's own
        # 200/byte-streaming logic — the @require_jwt auth chain itself is
        # already covered by thedevkitchen_apigateway's own tests.
        route_wrapper = (
            controller_module.CmsPublicPropertyController.get_public_property_image
        )
        require_jwt_wrapped = route_wrapper.__wrapped__
        raw_method = require_jwt_wrapped.__wrapped__

        controller = controller_module.CmsPublicPropertyController()
        mock_request = Mock()
        mock_request.env = self.env

        original_request = controller_module.request
        controller_module.request = mock_request
        try:
            response = raw_method(
                controller, "it-image-endpoint-co", self.property_with_image.id
            )
        finally:
            controller_module.request = original_request

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers.get("Content-Type", "").startswith("image/"))
        body = response.get_data() if hasattr(response, "get_data") else response.data
        self.assertGreater(len(body), 0)
