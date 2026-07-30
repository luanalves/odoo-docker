{
    "name": "Real Estate Management - Kenlo Imóveis Edition",
    "version": "18.0.7.0.0",  # Feature 027: agent/profile endpoint unification
    "category": "Real Estate",
    "summary": "Complete property management system following Kenlo Imóveis standards with RBAC",
    "description": """
Real Estate Management Module - Kenlo Imóveis Edition
=====================================================

This module provides a complete property management system for real estate agencies following Kenlo Imóveis standards.

Version 18.0.2.0.0 Changes:
===========================
- **RBAC User Profiles**: 9 predefined user profiles (Owner, Director, Manager, Agent, Prospector, Receptionist, Financial, Legal, Portal User)
- **Observer Pattern**: Event-driven architecture for decoupled business logic (ADR-020)
- **Async Messaging**: RabbitMQ + Celery for background processing (ADR-021)
- **Commission Split**: Prospector + Agent commission split functionality
- **Multi-Tenancy**: Enhanced company isolation with comprehensive record rules

Key Features:
============
- **Property Management**: Complete property registration with 13 organized sections
- **Owner Management**: Detailed owner profiles with CPF/CNPJ validation
- **Building/Condominium**: Track buildings and condominiums
- **Contact Management**: Multiple phones and emails per property
- **Photo Gallery**: Advanced photo management with main photo selection
- **Document Management**: Organize all property documents (matrícula, IPTU, contracts, etc.)
- **Key Control**: Track keys and their whereabouts
- **Commission Management**: Configure commissions per property
- **Web Publishing**: SEO-optimized property publishing
- **Authorization Control**: Track authorization periods
- **Brazilian Market**: CEP integration, IPTU, CNPJ, CPF validations
- **Agent Management**: Assign agents to properties
- **Lease Management**: Handle leasing contracts with profile integration
- **Sales Management**: Track property sales
- **Profile Unification**: Unified profile system for all RBAC types (Feature 010)

Property Form Sections:
======================
1. Owner Data
2. Structure
3. Location (with CEP search)
4. Primary Data (pricing, taxes, status)
5. Features (rooms, areas, amenities)
6. Zoning
7. Tags/Markers
8. Key Control
9. Photo Gallery
10. Web Publishing
11. Signs and Banners
12. Commissions
13. Documents

""",
    "author": "Quicksol Technologies",
    "website": "https://quicksol.ca",
    "depends": ["base", "portal", "mail", "thedevkitchen_apigateway"],
    "post_init_hook": "post_init",
    "data": [
        # Security files (must be loaded first)
        "security/groups.xml",
        "security/real_estate_security.xml",
        "security/record_rules.xml",
        "security/ir.model.access.csv",
        # Data files (sequences and master data)
        # Feature 010: Profile type lookup table (9 RBAC types)
        "data/profile_type_data.xml",
        "data/location_types.xml",
        # states.xml removed: Feature 011 — use native res.country.state
        "data/property_data.xml",
        "data/amenity_data.xml",
        # Carregado antes do company_seed: desativa IAP endpoint para evitar timeout do partner_autocomplete
        "data/system_parameters.xml",
        "data/company_seed.xml",  # Feature 007: Real Estate Companies seed data
        "data/demo_users.xml",  # Feature 007: Demo users
        "data/property_demo_data.xml",
        "data/agent_seed.xml",  # Feature 007: Agent seed data
        "data/seed_test_company.xml",  # Seed: Imobiliária Seed + todos os perfis para testes
        "data/seed_leads.xml",  # Seed: Leads da Imobiliária Seed cobrindo todas as jornadas de filtro
        "data/seed_leads_company_isolation.xml",  # Feature 024: company/agent isolation seed data
        "data/oauth2_seed.xml",  # Feature 007: OAuth2 test client
        # Test infra: MailHog SMTP (mailhog:1025) para captura de emails nos testes
        "data/mailhog_smtp_seed.xml",
        "data/seed_capabilities_data.xml",  # Feature 020: Capabilities endpoint fixtures
        "data/api_endpoints.xml",
        "data/user_auth_endpoints_data.xml",
        "data/lease_cron.xml",  # CHK002: Auto-expire leases cron job
        # Feature 013: Property Proposals
        "security/proposal_record_rules.xml",
        "data/proposal_sequence.xml",
        "data/mail_templates_proposal.xml",
        "data/proposal_cron.xml",
        "data/seed_proposals.xml",  # Seed: Proposals em todos os 8 estados FSM para testes de jornada
        "data/seed_property_relationships.xml",
        "data/seed_proposals_states.xml",  # Seed: Fase 2 — corrige estados FSM via SQL
        # 'data/default_groups.xml',  # Demo data temporarily disabled - complex dependencies
        # Feature 015: Service Pipeline (Atendimentos)
        "security/service_record_rules.xml",
        "data/service_sequence_data.xml",
        "data/service_tags_data.xml",
        "data/service_cron_data.xml",
        "data/service_api_endpoints.xml",
        "data/seed_services_data.xml",  # T072: Seed services all 7 stages
        # Views (actions must be loaded before menus that reference them)
        "views/property_views.xml",
        "views/property_auxiliary_views.xml",
        "views/agent_views.xml",
        "views/lead_views.xml",  # FR-001: Lead views for managers
        "views/commission_rule_views.xml",
        "views/assignment_views.xml",
        "views/lease_views.xml",
        "views/sale_views.xml",
        "views/company_views.xml",  # Feature 007: Company form, list, search views
        # Feature 007: Owner list, form views (REATIVADO - xpath corrigido)
        "views/owner_views.xml",
        "views/real_estate_menus.xml",
        "views/lead_filter_views.xml",  # FR-048: Saved search filters (REATIVADO)
        "views/res_users_views.xml",
        "views/proposal_views.xml",  # Feature 013: Proposal Kanban/List/Form
        # Feature 015: Service Pipeline (Atendimentos) views
        "views/service_tag_views.xml",
        "views/service_source_views.xml",
        "views/service_settings_views.xml",
        "views/service_views.xml",
        "views/service_menu.xml",
        # Feature 015: Wizards
        "wizards/service_reassign_wizard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "quicksol_estate/static/src/js/phone_widget.js",
            "quicksol_estate/static/src/js/email_widget.js",
        ],
    },
    "license": "LGPL-3",
    "images": ["static/description/banner.png"],
    "installable": True,
    "auto_install": False,
    "application": True,
}
