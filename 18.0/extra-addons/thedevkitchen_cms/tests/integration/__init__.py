# -*- coding: utf-8 -*-
"""
Integration Tests for thedevkitchen_cms Module

TransactionCase-based tests requiring a live Odoo/database connection.
Execution: docker compose -f 18.0/docker-compose.yml exec odoo \
    odoo -d realestate -u thedevkitchen_cms \
    --test-enable --stop-after-init --log-level=test --http-port=8988
"""
from . import test_cms_template_generic_crud
