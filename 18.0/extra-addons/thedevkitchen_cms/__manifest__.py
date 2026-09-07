{
    "name": "TheDevKitchen CMS",
    "version": "18.0.1.0.0",
    "category": "Website",
    "summary": "Headless CMS Domain for Real Estate Agencies",
    "description": """
TheDevKitchen CMS
==================

Headless CMS domain para imobiliárias gerenciarem páginas web.

Features:
---------
* Criação e publicação de páginas com editor Puck (JSON)
* Máquina de estados 4-fases: draft → pending_review → published → archived
* Biblioteca de mídia com upload seguro (validação por magic bytes)
* Templates reutilizáveis por imobiliária
* Configurações CMS por imobiliária (company_slug, CSS/JS customizados)
* Rota pública headless para Next.js SSR (JWT only, sem sessão Odoo)
* SEO completo: meta tags, Open Graph, structured data, robots_meta
* Isolamento multi-tenancy por company_id
* Observabilidade: eventos Loki + métricas Prometheus
* Interface administrativa Odoo com views, filtros e statusbar
* 19 endpoints REST documentados no Swagger (ADR-005)
* Postman collection (ADR-016)

Technical:
----------
* MIME validation via python-magic (magic bytes, não extensão)
* CSS injection guard: 5 padrões regex (service layer only)
* Hard delete para mídia — ADR-015 exception (pattern Feature 017)
* ADR-003, ADR-004, ADR-005, ADR-008, ADR-011, ADR-015, ADR-017, ADR-018, ADR-019
    """,
    "author": "TheDevKitchen",
    "website": "https://www.thedevkitchen.com",
    "license": "LGPL-3",
    "depends": [
        "mail",
        "thedevkitchen_apigateway",
        "thedevkitchen_observability",
        "quicksol_estate",
    ],
    "external_dependencies": {
        "python": [
            "magic",
        ],
    },
    "data": [
        "security/ir.model.access.csv",
        "security/cms_record_rules.xml",
        "data/api_endpoints.xml",
        "data/cms_demo_pages.xml",
        "views/cms_page_views.xml",
        "views/cms_template_views.xml",
        "views/cms_template_generic_views.xml",
        "views/cms_media_views.xml",
        "views/cms_settings_views.xml",
        "views/cms_menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
