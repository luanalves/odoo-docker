# Project Constitution — Realestate Backend (Odoo 18.0)

> **Navigation and overview document.** For in-depth details, see the [Knowledge Base](knowledge_base/README.md).

**Generated on:** 2026-07-08
**Last updated:** 2026-07-08
**Source directory analyzed:** `18.0/` (contains `odoo.conf`, `docker-compose.yml`, `extra-addons/`, `celery_worker/`) — workspace root = repository root (`/opt/homebrew/var/www/realestate/realestate_backend`)
**Detected stack:** Odoo 18.0 (Community, self-built image) + Python 3.12 + PostgreSQL 16 + Redis 7 + RabbitMQ 3 + Celery 5.3.4

**Prior documentation reconciled with code (Step 0.5):** `README.md` (root and `18.0/`), `docs/guide/*` (chapters 1–5), `docs/adr/*` (29 ADRs), `docs/architecture/*`, `TECHNICAL_DEBIT.md`. There is also a pre-existing, separately maintained **spec-kit constitution** at `.specify/memory/constitution.md` (v1.9.1) — a detailed, code-pattern-level governance document (Redis cache patterns, RBAC/multi-tenancy principles, forbidden patterns, etc.) used by the `.specify`/`.github/agents` speckit tooling. This `CLAUDE.md` is a separate, higher-level navigation document and does not replace or duplicate it; consult `.specify/memory/constitution.md` for binding, pattern-level engineering rules and amendment history.

## Specifications (spec-kit pattern)

This project tracks feature specs under `specs/NNN-slug/` (spec-kit convention), one numbered directory per feature — e.g. `specs/023-redis-session-cache/`, `specs/024-leads-company-isolation/`. Each directory typically contains `spec.md` (the design/requirements) plus, as needed, `plan.md`, `tasks.md`, `research.md`, `data-model.md`, `quickstart.md`, and `contracts/`/`checklists/` subfolders. When starting a new feature or writing a design doc, create the next sequentially numbered `specs/NNN-slug/` directory rather than a flat file elsewhere. `NNN` is zero-padded and increments from the highest existing number in `specs/`.

---

## Knowledge Base

This project has detailed documentation in `knowledge_base/`, split into two parts. Whenever you need in-depth information, consult the files below before directly analyzing the source code:

### Part 1 — Project Discovery (this codebase, code-verified)

| File | Content |
|------|---------|
| [modules-custom.md](knowledge_base/modules-custom.md) | 8 custom modules (TheDevKitchen/Quicksol) — purpose, status, dependencies |
| [modules-vendor.md](knowledge_base/modules-vendor.md) | Third-party dependencies — OCA module + Python/infra packages |
| [architecture.md](knowledge_base/architecture.md) | Detailed architecture, tech stack, request-flow Mermaid diagram |
| [infrastructure.md](knowledge_base/infrastructure.md) | Docker Compose, environments, CI/CD gap, support services |
| [multi-tenancy.md](knowledge_base/multi-tenancy.md) | Multi-agency SaaS model, isolation mechanisms, RBAC profiles |
| [integrations.md](knowledge_base/integrations.md) | External integrations — Kong, observability stack, MailHog, OAuth2 |
| [performance.md](knowledge_base/performance.md) | Redis cache strategy, indexing, async processing, runtime tuning |
| [security.md](knowledge_base/security.md) | Auth model, RBAC, CORS, compliance (LGPD), known gaps |
| [crons-queues.md](knowledge_base/crons-queues.md) | `ir.cron` scheduled jobs and RabbitMQ/Celery queue topology |
| [api-surface.md](knowledge_base/api-surface.md) | Full REST API surface (~180 endpoints across 9 modules) |
| [testing.md](knowledge_base/testing.md) | Testing strategy (Odoo tests, curl/integration_tests, Cypress) |

### Part 2 — Odoo Development Guidelines (reference, pre-existing)

General Odoo 18/19 coding standards (not project-specific business logic): module structure, naming conventions, Python/XML/JS/CSS guidelines, database best practices, frontend/views, email sending, deploy checklist, SaaS-admin-module checklist. See [knowledge_base/README.md](knowledge_base/README.md) for the full index, plus `QUICK_REFERENCE.md` and `EXAMPLES.md`.

> If any Part 1 file becomes stale (new module, ADR accepted, compose/infra change, new integration), re-run the **thedevkitchen-speckit-project-knowledge-base** agent pointed at `18.0/` as `SOURCE_DIR`.

---

## Specifications (spec-kit pattern)

Feature work in this project follows a spec-kit convention: numbered `specs/NNN-feature-name/` directories at the workspace root, one per feature (see `specs/` for existing examples). The `thedevkitchen-speckit-specify` agent generates `specs/NNN-feature-name/spec-idea.md`; this runs **before** `superpowers:brainstorming`/`superpowers:writing-plans`, not after, so those skills have grounded requirements to work from.

**Plan location override:** `superpowers:writing-plans`'s default save location is `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`. For this project, use `specs/NNN-feature-name/plan-idea.md` instead — the same numbered directory as the corresponding `spec-idea.md` — so the spec and its implementation plan live together. This is a "user preference" per that skill's own override clause, not a change to the skill file itself.

## 1. Overview

| Field | Value |
|-------|-------|
| **Name** | Realestate Backend — main application module: "Real Estate Management - Kenlo Imóveis Edition" (`quicksol_estate`, v18.0.5.0.0) |
| **Language/Runtime** | Python 3.12 (Odoo container; local `.venv` tooling uses 3.13) |
| **Framework** | Odoo 18.0 (Community, self-built Docker image) |
| **Architecture** | Hybrid — Modular Monolith (single Odoo instance, independently versioned addons) + async worker fleet (Celery/RabbitMQ) + external API Gateway (Kong, separate repo) |
| **Business Model/Domain** | B2B SaaS — multi-tenant real estate agency ("imobiliária") management platform, Brazilian market (CPF/CNPJ/CRECI validation, LGPD compliance) |
| **Multi-tenant** | Yes — config-driven/row-level, single shared database, tenant = `res.company` |
| **GraphQL API** | No — 100% REST/JSON over HTTP (no GraphQL or gRPC surface found) |
| **Frontend in this repo** | None — headless API only; consumed by an external Next.js/React application. Odoo's own web client is used only for back-office/admin operations. |

## 2. Infrastructure

| Field | Value |
|-------|-------|
| **Platform** | Docker Compose (not Kubernetes); production additionally attached to a `dokploy-network` — indicators of **Dokploy** (self-hosted PaaS) found (`DOKPLOY_DEPLOY.md`, `PRODUCTION_SETUP.md`, `docker-compose-production.yml`) — confirm with the infrastructure team |
| **CI/CD** | **No CI/CD pipeline configuration found in this repository** (no `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/`) — see discrepancy #2 below |
| **Web Server** | Odoo's bundled Werkzeug server (`odoo-bin`), not behind Gunicorn/uWSGI/Nginx |
| **Runtime version** | Python 3.12 / Odoo 18.0 / PostgreSQL 16 |
| **Local Dev** | Docker Compose (`18.0/docker-compose.yml`); `cd 18.0 && docker compose up -d`, default creds `admin/admin` |
| **Cache** | Redis 7 (session store DB 1, Celery result backend DB 2, custom JWT cache-aside layer) |
| **Search** | None — standard PostgreSQL ORM `search()` with targeted B-tree indexes; no Elasticsearch/OpenSearch |
| **CDN** | None found — Odoo serves its own web asset bundles directly; filestore is the only binary-attachment backend |
| **APM** | OpenTelemetry SDK → OTLP/gRPC → Grafana Tempo, correlated with Prometheus metrics and Loki logs (`thedevkitchen_observability` module, ADR-025/ADR-026); not New Relic/Datadog/Sentry |

Support services (from `docker-compose.yml`): PostgreSQL 16, Redis 7, RabbitMQ 3 (+ management UI), 3 dedicated Celery workers, Flower (task monitoring), MailHog + Mongo (dev-only SMTP), Grafana/Prometheus/Loki/Tempo/Promtail observability stack, `odoo-init` one-shot bootstrap container. Kong API Gateway sits in front in production only, maintained in a separate `apigateway` repository.

> Complete details: [infrastructure.md](knowledge_base/infrastructure.md), [architecture.md](knowledge_base/architecture.md)

## 3. Multi-tenancy / Environments

**Model:** SaaS multi-tenancy on a **single shared database** — tenant boundary is `res.company` ("imobiliária"/real estate agency), not database-per-tenant or schema-per-tenant. Tenants are created at runtime (there is no fixed, enumerable list of sites to document here); see [multi-tenancy.md](knowledge_base/multi-tenancy.md) for the full hierarchy (users, agents, owners, tenants, properties, leases, sales, CMS pages all scoped by `company_id`/`company_ids`).

Isolation defense-in-depth: `res.users.company_ids` membership, `ir.rule` record rules, the API-layer "5 mandatory security principles" (ADR-008), the `@require_company` decorator, and a cross-company System Admin exception for the Odoo web UI only (ADR-029, headless API explicitly blocks System Admin login).

**Deployment environments** (per `docs/guide/03-environments.md`, not independently verifiable from this repo since target servers are external):

| Environment | URL | Workers | Notes |
|---|---|---|---|
| Local | http://localhost:8069 | 0 (threaded dev mode) | `docker compose up -d` from `18.0/` |
| Dev | https://dev.torque-backoffice.thedevkitchen.com.br | 2 | Auto-deploy on push to `develop` (per docs — see CI/CD discrepancy below) |
| Homologação | https://homol.torque-backoffice.thedevkitchen.com.br | 4 | Manual deploy; weekly sanitized DB refresh from prod |
| Produção | https://torque-backoffice.thedevkitchen.com.br | 8 | Manual deploy; MFA required for admin access (infra-level); VPN required for DB access |

> Complete details: [multi-tenancy.md](knowledge_base/multi-tenancy.md)

## 4. Frontend / UI

**Not applicable — this repository is API-only/headless.** There is no server-rendered customer-facing frontend here; the REST API (JWT/OAuth2) is the contract for an external Next.js/React application. Odoo's own web client (with `thedevkitchen_branding` login-page customizations) is used solely for internal back-office/admin operations.

## 5. Custom Modules/Components (summary)

**Total:** 8 custom modules (TheDevKitchen/Quicksol), all active (no module-registry/feature-flag "disabled" state mechanism found — status assumed active unless noted).

| Module | Type | Purpose |
|--------|------|---------|
| `quicksol_estate` | Application (main) | Core real estate management — properties, owners, agents, leases, sales, leads, proposals, service pipeline, commissions, RBAC profiles. 108 REST endpoints. **Naming exception** (see §12). |
| `thedevkitchen_apigateway` | Library/Infra | OAuth 2.0 + JWT auth (token issuance/revocation/introspection), Swagger/OpenAPI generation, endpoint registry, API access logging |
| `thedevkitchen_cms` | Application | Headless CMS for agency web pages (Puck JSON editor), media library, public SSR route for Next.js consumption |
| `thedevkitchen_estate_credit_check` | Extension of `quicksol_estate` | Rental credit-analysis gate for lease proposals |
| `thedevkitchen_estate_goals` | Extension/reporting | Monthly performance goals/achievement tracking across the sales funnel |
| `thedevkitchen_observability` | Library/Infra | OpenTelemetry tracing instrumentation, Loki/Tempo/Prometheus correlation |
| `thedevkitchen_user_onboarding` | Extension | Invite → email → set-password flow, password reset, Redis rate limiting |
| `thedevkitchen_branding` | Extension (view-only) | Odoo login-page branding/UI customization |

Plus 1 vendored OCA module: `auditlog` (18.0.2.0.2, AGPL-3, audit-log CRUD/session/request recording).

> Complete documentation of each module: [modules-custom.md](knowledge_base/modules-custom.md)

## 6. Third-Party Dependencies (summary)

- **Auth:** `authlib` 1.6.5 (OAuth2), `PyJWT` 2.10.1, `bcrypt` 5.0.0, `cryptography` 46.0.3
- **Validation/QA:** `jsonschema` 4.25.1, `email-validator` 2.1.0, `validate_docbr` (CPF/CNPJ)
- **Security:** `python-magic` (magic-byte MIME detection for CMS uploads)
- **Messaging/Queue:** `celery[redis]` 5.3.4, `pika` 1.3.2 (AMQP)
- **Observability:** `opentelemetry-{api,sdk,exporter-otlp-proto-grpc,instrumentation,instrumentation-celery}` >=1.22.0
- **Code quality:** `black` 24.10.0, `isort` 5.13.2, `flake8` 7.1.1, `pylint` 3.3.1, `mypy` 1.13.0
- **Data processing (Celery worker image):** `pandas` 2.1.4, `requests` 2.31.0, `python-dotenv` 1.0.0
- **E2E testing:** `cypress` ^15.10.0
- **Infra images:** `postgres:16-alpine`, `redis:7-alpine`, `rabbitmq:3-management-alpine`, `mher/flower:2.0`, `mongo:4.4-focal`, `mailhog/mailhog:latest`

> Complete documentation: [modules-vendor.md](knowledge_base/modules-vendor.md)

## 7. External Integrations

| System | Type | Details |
|--------|------|---------|
| Kong API Gateway | Inbound reverse proxy (prod only) | Separate repository; front door for all `/api/v1/*` traffic in production. See [integrations.md](knowledge_base/integrations.md) |
| Grafana stack (Prometheus/Loki/Tempo) | Outbound observability | Metrics, logs, distributed traces from Odoo + Celery |
| RabbitMQ + Celery | Internal async messaging | Bidirectional — Odoo publishes events, Celery calls back via XML-RPC. See [crons-queues.md](knowledge_base/crons-queues.md) |
| MailHog | Dev/test-only SMTP double | No production SMTP relay found in repo (likely configured directly in prod DB `ir.mail_server`, not version-controlled) |
| OAuth 2.0 Client (external frontend) | Inbound SSO/API auth | `client_credentials` grant + JWT Bearer (RFC 9068) |
| Odoo IAP `partner_autocomplete` | Explicitly disabled | Deliberate opt-out via system parameter, not an oversight |

**Not found:** payment gateway, CEP/postal-code lookup webservice (despite a module description mentioning it), ERP/marketing/analytics-platform integrations.

## 8. Expected Files

| File | Present | Purpose |
|------|---------|---------|
| `18.0/.env` | Yes (not tracked by git — correctly gitignored) | Environment variables (DB, Redis, Celery, JWT, OAuth, seed users, OTel, domain routing) |
| Credentials manifest (`auth.json`/`.npmrc`/`.netrc`) | No (N/A for this stack) | — |
| `18.0/docker-compose.yml` + `docker-compose-production.yml` | Yes | Local dev and production container orchestration |
| CI/CD config (`.github/workflows/`, etc.) | **No** | See discrepancy #2 — documented pipeline not present in-repo |
| Lint/static-analysis config (`18.0/.flake8`) | Yes | flake8 config (max line length 88, `E203/E501/W503/E402` ignored); black/isort/pylint/mypy pinned in `Dockerfile` per ADR-022 |
| Test config | No dedicated `pytest.ini`/config file | Odoo's own `odoo.tests.common` test discovery (`--test-enable -i <module>`); validated via `scripts/validate_coverage.sh` per the ADR-003 flow (unit runner → E2E curl → optional Cypress) |
| Patches/hotfixes directory | No | Not applicable — no patch-management convention found |
| `.coderabbit.yaml` | Yes | AI PR-review bot configuration (closest thing to an automated quality gate found) |
| Orphaned `addons/` directory (repo root) | Yes — **stale/unreferenced** | See discrepancy #3 |

## 9. Security

| Item | Status |
|------|--------|
| **Admin/privileged access path** | `base.group_system` (Odoo System Admin) — cross-company access via Odoo web UI only; **explicitly blocked** from the headless REST login endpoint (ADR-029) |
| **Authentication** | Triple-decorator chain `@require_jwt` → `@require_session` → `@require_company` (ADR-011) on nearly all REST controllers; OAuth2 (authlib) + JWT for API auth, HTTP session for continuity |
| **2FA** | Not implemented at the application layer (docs reference "MFA mandatory" for prod admin access, but this is an infra-level control, not an Odoo/API feature) |
| **CSP / security headers** | Not identified — no CSP/`X-Frame-Options`/HSTS middleware found; Odoo defaults apply |
| **Session hijacking prevention (ADR-017)** | Status **Proposed**, not confirmed fully implemented — recommend verifying against current `thedevkitchen_apigateway` code before treating as a guarantee |
| **CORS** | Hardcoded `cors='*'` on several endpoints — known, open technical debt (see §12) |
| **Redis JWT cache-aside layer** | **Implemented** in `thedevkitchen_apigateway/middleware.py`/`redis_client.py` (see discrepancy #4 below) — reconciles with recent PR #25 "023-redis-session-cache" |
| **Credentials file in git** | OK — `.env` exists locally but is not tracked (confirmed via `git ls-files`) |
| **Rate limiting** | Confirmed only for forgot-password (3 req/hr, Redis-backed); no general per-IP/per-token API rate limiting found in this codebase (likely enforced at the external Kong layer) |
| **Compliance** | LGPD referenced extensively in ADRs and code comments; soft-delete (ADR-015) + `auditlog` OCA module as the main data-governance mechanisms; no dedicated data-export/right-to-erasure automation found |
| **Known open gap (RBAC)** | Action-level authorization is **global** (Odoo security groups), not per-company, despite per-company profile data (`thedevkitchen_estate_profile`) already existing — documented fix path in `TECHNICAL_DEBIT.md` and [multi-tenancy.md](knowledge_base/multi-tenancy.md) |

> Complete details: [security.md](knowledge_base/security.md)

## 10. Code Quality

| Tool | Status | Details |
|------|--------|---------|
| **Static analysis (Python)** | Configured, not confirmed wired to CI | black, isort, flake8 (`18.0/.flake8`), pylint, mypy — all installed in the Odoo Docker image per ADR-022 |
| **Static analysis (XML/views)** | Configured | Custom `18.0/lint_xml.py`/`lint_xml.sh` — detects deprecated `<tree>`/`attrs`, `column_invisible` Python-expression bugs |
| **Pre-commit/quality gate** | Not confirmed automated | `lint.sh`, `lint_xml.sh`, `scripts/validate_coverage.sh`, `scripts/validate_openapi_sync.sh` exist but there is no CI workflow file to confirm they run automatically on push/PR |
| **Test framework** | Present | Odoo `odoo.tests.common` (unit/integration) + curl-based `integration_tests/*.sh` (deliberately chosen over `HttpCase` due to its read-only-transaction limitation) + Cypress (41 E2E specs) |
| **PR review automation** | Configured | CodeRabbit (`.coderabbit.yaml`) |

**Tests present in the project:**
- [x] Unit tests (Odoo `TransactionCase`, per-module `tests/`, 114 test files total across 8 modules)
- [x] Integration tests (`integration_tests/*.sh`, curl-based, live Odoo instance)
- [x] Functional / E2E tests (Cypress, 41 specs)
- [x] API/contract tests (Postman collections governed by ADR-016; `scripts/validate_openapi_sync.sh`, scoped only to the proposals module)

ADR-003 (current, v3.0) requires 100% coverage of validations (`required=True`, `@api.constrains`, `_sql_constraints`, `compute=`, each with a success + failure test) rather than a blanket line/branch coverage percentage; a module-by-module audit against that rule has not yet been performed.

> Details: [testing.md](knowledge_base/testing.md)

## 11. Runtime Configuration

- Base URLs: see §3 environments table (asserted by documentation, not independently verifiable without infra access).
- Locale/i18n: standard Odoo i18n; no per-tenant locale sub-level found.
- Cache/search engine in use: Redis (session/JWT/Celery); PostgreSQL ORM search (no dedicated search engine).
- Feature flags: none found at a module/tenant level; `thedevkitchen.security.settings` model exists for security-related runtime settings (session cache TTL, etc., per `.specify/memory/constitution.md` v1.9.1).
- Per-environment performance tuning (`workers`, `max_cron_threads`, `limit_*`) is env-var driven (`ODOO_WORKERS`, etc.) — **Not identified/verifiable from this repo alone**, since production `.env` values are not committed (as expected for secrets) and `odoo.conf` itself leaves these directives commented out.

## 12. Attention Points — Documentation/Code Discrepancies (reconciled)

1. **Celery queue names/concurrency mismatch (RESOLVED — code is source of truth).** `docs/guide/02-docker-components.md` describes queues `commission_queue` / `notification_queue` / `audit_queue` at concurrency 2/4/2. The actual, verified configuration in `18.0/docker-compose.yml` and `event_bus.py`/`tasks.py`/`proposal.py` is `commission_events` (concurrency 2) / `audit_events` (concurrency 1) / `notification_events` (concurrency 1). Treat the code/compose values as authoritative; `docs/guide/02-docker-components.md` should be corrected to match. Details: [crons-queues.md](knowledge_base/crons-queues.md), [architecture.md](knowledge_base/architecture.md).

2. **No CI/CD pipeline exists in this repository, despite documentation describing one.** `docs/guide/02-docker-components.md` and `03-environments.md` describe a GitHub → CI/CD → Dev(auto)/Homol(manual)/Prod(manual) pipeline with quality gates, but no `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, or `.circleci/` exists (`.github/` in this repo only holds AI-assistant agent/prompt/skill instructions, no workflows). Local scripts (`lint.sh`, `lint_xml.sh`, `scripts/validate_coverage.sh`, `scripts/validate_openapi_sync.sh`) exist and strongly suggest CI intent, but there is no in-repo evidence they run automatically. `.coderabbit.yaml` (CodeRabbit AI PR review) is the only in-repo automated review aid found. **This needs confirmation from the team**: is the described pipeline managed externally (e.g., Dokploy git-push-to-deploy webhooks per `DOKPLOY_DEPLOY.md`, or a separate infra repo), or does it need to be built? Recommend updating `docs/guide/02-docker-components.md`/`05-deployment.md` to reflect the actual deployment mechanism, or adding the missing workflow files.

3. **Stale, orphaned `addons/` directory at the repository root.** Duplicates `auditlog`, `quicksol_estate`, `thedevkitchen_apigateway`, `thedevkitchen_branding`, `thedevkitchen_user_onboarding` from `18.0/extra-addons/`, but is **not** referenced by `18.0/odoo.conf` (`addons_path`) or `18.0/docker-compose.yml` (only `./extra-addons` is mounted), and `addons/quicksol_estate/__manifest__.py` is confirmed missing entirely — this copy could not even load as an Odoo module. Flagged as a cleanup candidate (possible leftover bind-mount or IDE index); left in place per this agent's read-only mandate — **recommend the team confirm and delete** `addons/` at the repo root.

4. **Redis/JWT session caching — `TECHNICAL_DEBIT.md` is partially reconciled already, not fully stale.** The current `TECHNICAL_DEBIT.md` text already acknowledges "(JWT já implementado; falta integração Redis no fluxo de sessão em `performance_service.py`)" — and code inspection confirms `thedevkitchen_apigateway/middleware.py` + `services/redis_client.py` **do** implement a Redis cache-aside layer for JWT validation (`RedisClient.jwt_key`, graceful fallback to DB on MISS), consistent with the recently merged PR #25 ("023-redis-session-cache"). **What remains genuinely open** (per `TECHNICAL_DEBIT.md` itself): the `session_id` lookup path is not yet Redis-backed in production use — Redis is configured in Docker but not yet used for `session_id` lookups end-to-end. Recommend the team do a final pass on `TECHNICAL_DEBIT.md` to split this single bullet into "JWT Redis cache: done" vs. "session_id Redis cache: still open" for clarity.

5. **`quicksol_estate` violates ADR-004's `thedevkitchen_` naming prefix — accepted, documented legacy exception.** ADR-004 (Status: Aceito) mandates the prefix for all customized modules to avoid naming collisions; `quicksol_estate` predates the ADR and is explicitly carried forward as the main application module, with a rename judged too costly. All newer modules correctly follow the convention. No action needed — this is intentional, not a defect.

6. **A handful of GET endpoints are fully public, breaking the otherwise-universal triple-decorator convention.** `/api/v1/leads` (GET), `/api/v1/sales` (GET), and `/api/v1/tags` (GET) are registered `auth='none'` with no `@require_jwt`/`@require_session`/`@require_company` decorators and `cors='*'`, unlike every sibling endpoint in the same controllers (`lead_api.py`, `sale_api.py`, `master_data_api.py`). This is corroborated by `TECHNICAL_DEBIT.md`'s existing note about hardcoded `cors='*'` needing to become dynamic/back-office-configurable. **This needs a decision from the team**: confirm whether these three specific public list endpoints are an intentional public marketing/lead-capture use case, or an oversight that should be brought in line with the standard auth chain. Until confirmed, treat as an open security question rather than settled behavior. Full endpoint-by-endpoint auth matrix: [api-surface.md](knowledge_base/api-surface.md).

7. **Other known, still-open items from `TECHNICAL_DEBIT.md`** (not new discoveries, listed here for visibility): CMS scheduled-publish feature descoped from Feature 021 (requires a new `celery_cms_worker`/`cms_events` queue, `scheduled` FSM state); UUID vs. sequential `id` for property routes not yet adopted; sequential `id` on `thedevkitchen_api_session` not yet reconsidered; `tracking_disable` skips on some models flagged as a possible audit/security gap needing validation; generic "log every CRUD as an activity" auditing goal not yet fully realized beyond the `auditlog` module.

8. **Data unavailable without runtime/DB/infra access:** actual per-environment `workers`/`limit_*` values in production (asserted only in docs, `odoo.conf` leaves them as env-var placeholders); actual test coverage percentages (only file counts were verifiable); production outgoing-SMTP configuration (`ir.mail_server`, DB-only); whether the documented CI/CD pipeline exists in Dokploy or elsewhere outside this repo.
