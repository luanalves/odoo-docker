{
    "name": "TheDevKitchen User Onboarding",
    "version": "18.0.2.0.0",
    "category": "Human Resources",
    "summary": "User Onboarding & Password Management for RBAC Profiles",
    "description": """
User Onboarding & Password Management
======================================

Complete user onboarding flow (invite → email → set password) and password
reset functionality for all 9 RBAC profiles in the real estate system.

Features:
---------
* Invite users via secure email link (SHA-256 token hashing)
* Set password upon first access (invite link)
* Forgot password flow with reset link
* Resend invite for pending users
* Configurable link TTL and rate limiting
* Portal profile dual record creation (res.users + real.estate.tenant)
* Anti-enumeration protection on forgot-password
* Session invalidation after password reset
* Multi-tenant isolation at company level
* Email templates in Portuguese (pt_BR)

Technical Details:
------------------
* Token-based authentication (UUID v4 → SHA-256 hash)
* Redis rate limiting for forgot-password (3 requests/hour)
* Atomic dual record creation for portal users
* Authorization matrix: Owner → all profiles, Manager → 5 operational, Agent → owner+portal
* REST API with HATEOAS links
* ADR-003 compliant (unit tests + E2E tests)
* ADR-008 compliant (anti-enumeration on forgot-password)
* ADR-015 compliant (soft delete on tokens)
    """,
    "author": "TheDevKitchen",
    "website": "https://www.thedevkitchen.com",
    "license": "LGPL-3",
    "depends": [
        "mail",
        "thedevkitchen_apigateway",
        "quicksol_estate",
    ],
    "external_dependencies": {
        "python": [
            "validate_docbr",
            "email_validator",
        ],
    },
    "data": [
        "security/ir.model.access.csv",
        "security/record_rules.xml",
        "data/default_settings.xml",
        "data/email_templates.xml",
        "data/api_endpoints_data.xml",
        "views/email_link_settings_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "assets": {},
}
