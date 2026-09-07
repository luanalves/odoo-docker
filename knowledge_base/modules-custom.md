# Custom Modules / Components

> Source analyzed: `18.0/extra-addons/` (mounted into the Odoo container at `/mnt/extra-addons`, per `18.0/odoo.conf` `addons_path` and `18.0/docker-compose.yml`).
> Cross-referenced with: `docs/adr/*`, `docs/architecture/DATABASE_ARCHITECTURE_USERS.md`, `docs/architecture/event-driven-rbac.md`, module `__manifest__.py` files, and `TECHNICAL_DEBIT.md`.

The system is a single **Odoo 18.0** instance extended with 8 custom addons developed by TheDevKitchen/Quicksol (application modules), plus one vendored OCA community module (`auditlog`, documented in [modules-vendor.md](modules-vendor.md)).

Naming convention: **ADR-004** mandates the `thedevkitchen_` prefix for all new custom modules and tables. `quicksol_estate` predates this ADR and is kept as a **documented legacy exception** (it is the original/main application module and a rename was judged too costly); all newer modules correctly follow the `thedevkitchen_` prefix.

---

### quicksol_estate
- **Purpose:** Core real estate management application — properties, owners, agents, leases, sales, leads, proposals (with FSM/queue), service pipeline ("Atendimentos"), commissions, and RBAC profile management. This is the main `application: True` module; all other custom modules extend it.
- **Type:** Application (Odoo module, `application: True`)
- **Version:** 18.0.5.0.0
- **Dependencies:** `base`, `portal`, `mail`, `thedevkitchen_apigateway`
- **Main extension point:** Defines 108 REST endpoints (`/api/v1/agents`, `/properties`, `/leases`, `/sales`, `/leads`, `/proposals`, `/services`, `/companies`, `/owners`, `/profiles`, commission rules/transactions, assignments); extends `res.users` and `res.company` with multi-tenant fields; emits domain events via `quicksol.event.bus` (Observer pattern, ADR-020) consumed synchronously and asynchronously (RabbitMQ/Celery, ADR-021); defines 3 `ir.cron` jobs (lease/proposal/service auto-expiration, pendency recompute).
- **Naming exception:** Does not follow the `thedevkitchen_` prefix (ADR-004 legacy exception, predates the ADR).
- **Last modified:** 2026-06-17 (git)

### thedevkitchen_apigateway
- **Purpose:** Generic OAuth 2.0 API Gateway for Odoo REST APIs — token issuance/revocation/introspection, endpoint registry (used to auto-generate the OpenAPI spec), Swagger UI, JWT authentication middleware (`require_jwt`, `require_session`, `require_company`, `require_jwt_with_scope` decorators), and API access logging.
- **Type:** Library / Technical infrastructure module (`application: False`)
- **Version:** 18.0.1.2.0
- **Dependencies:** `base`, `web`, `mail`, `bus`; external Python: `authlib` (RFC 6749/7009/7662/9068 compliant)
- **Main extension point:** All other custom modules depend on this module for authentication decorators and Swagger endpoint registration (`thedevkitchen.api.endpoint` model). Exposes `/api/v1/auth/token`, `/api/v1/auth/revoke`, `/api/v1/auth/refresh`, `/api/v1/me`, `/api/v1/health`, `/api/docs`, `/api/v1/openapi.json`, `/api/v1/users/login|logout|profile|change-password|switch-company`.
- **Last modified:** 2026-06-17 (git)

### thedevkitchen_cms
- **Purpose:** Headless CMS for real estate agencies to build and publish web pages (Puck JSON editor), with a 4-state FSM (`draft` → `pending_review` → `published` → `archived`), a media library with magic-byte MIME validation, reusable templates, and a public headless route for Next.js SSR consumption (JWT-only, no Odoo session).
- **Type:** Application module (`application: False`, but functionally a distinct product domain)
- **Version:** 18.0.1.0.0
- **Dependencies:** `mail`, `thedevkitchen_apigateway`, `thedevkitchen_observability`, `quicksol_estate`; external Python: `magic` (python-magic)
- **Main extension point:** 19 REST endpoints (`/api/v1/cms/pages`, `/templates`, `/media`, `/settings`, plus the public `/api/v1/public/cms/<company_slug>/pages/<page_slug>`); multi-tenant isolation via `company_id`; CSS-injection guard (regex-based) at the service layer.
- **Feature 028 addition (branch `028-cms-generic-templates`):** platform-level, non-tenant template catalog — `thedevkitchen.cms.template.generic` (+ `.content`, 1:1) has **no `company_id`** and is managed exclusively via Odoo UI by `base.group_system` (ADR-029 applied to a new domain — no REST create/update/delete for this model by design). Read (`GET /api/v1/cms/templates/generic`, `GET .../generic/{id}`) and copy (`POST .../generic/{id}/copy`) are exposed via `cms_template_generic_controller.py`, restricted to `owner`/`director`/`manager` — the same role tuple as company-scoped templates, imported as `GENERIC_TEMPLATE_MANAGEMENT_ROLES = TEMPLATE_MANAGEMENT_ROLES` from `cms_template_controller.py` (no hardcoded duplicate) to prevent authorization drift between sibling controllers. Copy materializes an independent, company-scoped `thedevkitchen.cms.template` snapshot with `source_generic_template_id` for traceability only — no ongoing sync; deactivating/editing the source never affects existing copies. See `specs/028-cms-generic-templates/spec-idea.md` ("Constitution Feedback" section) for the full pattern write-up.
- **Last modified:** 2026-09-06 (git, branch `028-cms-generic-templates`)

### thedevkitchen_estate_credit_check
- **Purpose:** Rental credit analysis ("Análise de Ficha") gate for lease proposals — introduces a `credit_check_pending` state in the proposal FSM, automatic queue promotion on rejection, automatic competitor cancellation on approval, and cron-driven expiry of pending checks.
- **Type:** Plugin/Extension of `quicksol_estate` (`_inherit` on `real.estate.proposal`)
- **Version:** 18.0.1.0.0
- **Dependencies:** `mail`, `thedevkitchen_apigateway`, `quicksol_estate`
- **Main extension point:** New model `thedevkitchen.estate.credit.check`; 4 REST endpoints under `/api/v1/proposals/<id>/credit-checks` and `/api/v1/clients/<partner_id>/credit-history`; async notifications via the Outbox/EventBus pattern (`notification_events` queue); partial unique index enforcing "one pending check per proposal" (ADR-027).
- **Last modified:** 2026-06-05 (git)

### thedevkitchen_estate_goals
- **Purpose:** Monthly performance goals and achievement tracking across 5 real-estate funnel metrics (captações, novos clientes, visitas, propostas, fechamento) for Owners/Directors/Managers to set targets per agent.
- **Type:** Plugin/Extension (reporting on top of `quicksol_estate` entities)
- **Version:** 18.0.1.0.0
- **Dependencies:** `mail`, `quicksol_estate`, `thedevkitchen_apigateway`
- **Main extension point:** 5 REST endpoints (`/api/v1/goals`, `/api/v1/goals/report`); achievements computed via raw SQL aggregation (no ORM N+1) over `real.estate.service`/`property`/`proposal`; composite DB index `(company_id, year, month, operation_type) WHERE active=true`.
- **Last modified:** 2026-06-05 (git)

### thedevkitchen_observability
- **Purpose:** OpenTelemetry distributed tracing instrumentation for Odoo (HTTP requests, DB queries, Redis ops), exporting to Grafana Tempo via OTLP/gRPC, with `trace_id` log correlation (Loki) and Prometheus exemplar linking.
- **Type:** Library / Technical infrastructure module
- **Version:** 18.0.1.0.0
- **Dependencies:** `base`, `web`; external Python: `opentelemetry-api/sdk/exporter-otlp-proto-grpc/instrumentation >=1.22.0/0.43b0`
- **Main extension point:** `@trace_http_request` controller decorator used across all other modules' controllers; `otel_loader.js` frontend asset bundle; `/api/otel/traces` OTLP proxy endpoint; `post_init_hook` for setup.
- **Last modified:** 2026-04-25 (git)

### thedevkitchen_user_onboarding
- **Purpose:** User onboarding (invite → email → set password) and password reset flow for all 9 RBAC profiles, with SHA-256 token hashing, Redis rate limiting, and dual-record creation for portal users (`res.users` + `real.estate.tenant`).
- **Type:** Plugin/Extension (auth flow on top of `thedevkitchen_apigateway` + `quicksol_estate` profiles)
- **Version:** 18.0.1.0.0
- **Dependencies:** `mail`, `thedevkitchen_apigateway`, `quicksol_estate`; external Python: `validate_docbr`, `email_validator`
- **Main extension point:** 5 REST endpoints (`/api/v1/users/invite`, `/resend-invite`, `/api/v1/auth/set-password`, `/forgot-password`, `/reset-password`); anti-enumeration protections (ADR-008); soft-delete on tokens (ADR-015).
- **Last modified:** 2026-06-05 (git)

### thedevkitchen_branding
- **Purpose:** Custom Odoo login page branding/UI customization (logo, simplified login screen).
- **Type:** Plugin/Extension (view/asset overrides only, no models or controllers)
- **Version:** 18.0.1.0.0
- **Dependencies:** `web`
- **Main extension point:** Overrides `web.login` templates (`views/webclient_templates.xml`) and injects `login.scss` into both `web.assets_frontend` and `web.assets_backend`.
- **Last modified:** 2026-01-22 (git)

---

## Discrepancies / Findings

1. **Stale duplicate `addons/` directory at the repository root.** A second copy of `auditlog`, `quicksol_estate`, `thedevkitchen_apigateway`, `thedevkitchen_branding`, and `thedevkitchen_user_onboarding` exists at `<repo_root>/addons/` (outside `18.0/`). It is **not** referenced by `18.0/odoo.conf` (`addons_path = .../dist-packages/odoo/addons,/mnt/extra-addons`) or by `18.0/docker-compose.yml` (which only mounts `./extra-addons`), and the copy under `addons/quicksol_estate` is missing `__manifest__.py` entirely (confirmed via diff) — meaning it could not even be loaded by Odoo as-is. This looks like leftover/orphaned content (possibly from an old bind-mount or IDE index) and is a candidate for cleanup. Flagging for confirmation rather than deleting, per this agent's read-only mandate.
2. **`quicksol_estate` violates ADR-004 naming convention** (no `thedevkitchen_` prefix). This is called out as a known, accepted legacy exception in the ADR itself.
3. Two modules declared `"assets": {}` empty in some manifests (e.g. `thedevkitchen_apigateway`, `thedevkitchen_user_onboarding`) despite having `static/` directories in some cases — not a functional issue, just noted for completeness.

No prior module-level documentation existed outside each module's own `README.md`/docstring in the manifest `description`; this file was built primarily from manifest inspection, controller/cron source inspection, and the ADRs in `docs/adr/`.
