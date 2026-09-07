<!--
Sync Impact Report - Constitution v1.11.0
==========================================

Version Change: 1.10.0 → 1.11.0
Change Type: MINOR (new architectural patterns + reference implementation documented from Feature 028)
Date: 2026-09-07

Sections Modified:
- Architectural Patterns → added "Platform-Level Non-Tenant Catalog Entity": a curated, platform-wide
  entity with no company_id, admin-curated exclusively via Odoo UI (no REST write route at all), no
  ir.rule (nothing to isolate) — access via ir.model.access.csv + explicit controller role check.
- Architectural Patterns → added "Curated-Copy-Into-Tenant Pattern": a REST action that materializes an
  independent, tenant-scoped snapshot from a platform-level entity, with a source_*_id traceability
  field (ondelete=set null, readonly) and no ongoing synchronization; company_id always session-derived;
  check-then-create for name uniqueness wrapped in a savepoint.
- Architectural Patterns → added "Role-Set Reuse Across Sibling Controllers": a new controller enforcing
  the same RBAC role tuple as an existing sibling MUST import a single shared constant, never an
  independently hardcoded literal — and any drift-guard test must compare against that same imported
  constant, not a second hardcoded copy. Enforced as a fix during Feature 028's own final review.
- Reference Implementations → added Feature 028 (CMS Generic Templates) entry; updated the closing
  "Use Feature X for..." summary paragraph to include it.
- Governance → added "API Documentation Is Not Deferred" under Runtime Guidance: Swagger/Postman updates
  must be verified with evidence in the same completion pass as tests, distinct from constitution/
  knowledge-base updates (which correctly wait for implementation validation) — a real gap caught during
  Feature 028 (Swagger left stale after the feature was declared complete).

Removed Sections:
- (none)

Follow-up TODOs:
- (none — all three patterns already have a validated reference implementation in Feature 028)

Previous Amendments:
- 2026-07-29 (v1.10.0 Feature 027 authorization hardening patterns)
- 2026-06-08 (v1.9.1 Feature 023 Redis cache TTL clarifications)
- 2026-06-08 (v1.9.0 Feature 023 Redis cache patterns initial)
- 2026-06-03 (v1.8.0 Feature 022 SaaS Admin channel separation)
- 2026-05-08 (v1.7.0 Feature 017 binary upload patterns)
- 2026-05-03 (v1.6.0 Feature 015 service pipeline patterns)
- 2026-02-16 (v1.3.0 Feature 009 security patterns)
- 2026-02-08 (v1.2.0 Feature 007 reference implementation)
-->

<!--
Sync Impact Report - Constitution v1.10.0 (historical)
==========================================

Version Change: 1.9.1 → 1.10.0
Change Type: MINOR (new RBAC/authorization patterns + architectural pattern documented from Feature 027)
Date: 2026-07-29

Sections Modified:
- Security Requirements → added "Explicit Group Check for Owner (Owner ≠ implies Manager)": when
  authorizing an Owner-restricted action, check `owner OR admin` explicitly over a list of group XML IDs;
  never assume checking `manager` alone also covers `owner` via `implied_ids`.
- Security Requirements → added "res.users Management is Owner-Only, Even Transitively (via Cascade)":
  any endpoint that cascades into `res.users` fields inherits the same Owner-only restriction already
  codified for direct user management, regardless of the endpoint's nominal subject.
- Architectural Patterns → added "Deliberate Authorization Hardening as a Cross-Cutting Fix (with
  Cross-Checking Against Existing Matrices)": when hardening authorization broadly to fix an
  inconsistency between a protected path and an unprotected legacy path, the resulting matrix MUST be
  cross-checked against every ACL and pre-existing authorization matrix touching the same entities.
- Reference Implementations → added Feature 027 (Agent/Profile Endpoint Unification) entry; updated the
  closing "Use Feature X for..." summary paragraph to include it.

Removed Sections:
- (none)

Follow-up TODOs:
- (none — all three patterns already have a validated reference implementation in Feature 027)

Previous Amendments:
- 2026-06-08 (v1.9.1 Feature 023 Redis cache TTL clarifications)
- 2026-06-08 (v1.9.0 Feature 023 Redis cache patterns initial)
- 2026-06-03 (v1.8.0 Feature 022 SaaS Admin channel separation)
- 2026-05-08 (v1.7.0 Feature 017 binary upload patterns)
- 2026-05-03 (v1.6.0 Feature 015 service pipeline patterns)
- 2026-02-16 (v1.3.0 Feature 009 security patterns)
- 2026-02-08 (v1.2.0 Feature 007 reference implementation)
-->

<!--
Sync Impact Report - Constitution v1.9.1 (historical)
========================================

Version Change: 1.9.0 → 1.9.1
Change Type: PATCH (clarifications to Redis cache TTL rules from Feature 023 spec finalization)
Date: 2026-06-08

Sections Modified:
- Redis Cache Patterns → JWT Cache Pattern: TTL rule corrected — use full `expires_at - now()` without an
  arbitrary 1-hour cap. JWT is already bounded by its own expiry; capping at 3600s would cause unnecessary
  cache misses for long-lived tokens.
- Redis Cache Patterns → Session Cache Pattern: TTL now references `session_cache_ttl_seconds` field in
  `thedevkitchen.security.settings` (default 300s) instead of hardcoded "5 minutes". Two new configurable
  fields added to the security settings pattern: `session_cache_ttl_seconds` and `session_inactivity_days`.
- Redis Cache Patterns → Session Cache Pattern: `last_activity` trade-off note updated to reference
  the configurable TTL value.

Removed Sections:
- (none)

Follow-up TODOs:
- Add `session_cache_ttl_seconds` (default 300) and `session_inactivity_days` (default 7) fields to
  `thedevkitchen.security.settings` model and its form view (menu: Technical → API Gateway → Security Settings).
- `cleanup_expired()` in `session_validator.py` must read `session_inactivity_days` from settings instead
  of its current hardcoded `days=7`.

Previous Amendments:
- 2026-06-08 (v1.9.0 Feature 023 Redis cache patterns initial)
- 2026-06-03 (v1.8.0 Feature 022 SaaS Admin channel separation)
- 2026-05-08 (v1.7.0 Feature 017 binary upload patterns)
- 2026-05-03 (v1.6.0 Feature 015 service pipeline patterns)
- 2026-02-16 (v1.3.0 Feature 009 security patterns)
- 2026-02-08 (v1.2.0 Feature 007 reference implementation)
-->
## Utilitários de Validação de CPF/CNPJ (Governança de Dados)

Para garantir unicidade, integridade e reutilização de validação de documentos fiscais brasileiros, o backend implementa as seguintes funções utilitárias em `utils/validators.py`:

- `normalize_document(document)`: Remove pontuação/máscara, retorna apenas dígitos.
- `is_cpf(document)`: Retorna True se for CPF válido.
- `is_cnpj(document)`: Retorna True se for CNPJ válido.
- `validate_document(document)`: Retorna True se for CPF ou CNPJ válido.

Essas funções devem ser usadas em todos os endpoints e modelos que aceitam documentos fiscais, garantindo padronização e governança de dados.
<!--
Sync Impact Report - Constitution v1.8.0
========================================

Version Change: 1.7.0 → 1.8.0
Change Type: MINOR (new SaaS Admin channel separation patterns + Feature 022 reference implementation)
Date: 2026-06-03

Sections Modified:
- Principle IV (Multi-Tenancy): Added SaaS Admin exception clause for base.group_system
- Principle VI (Headless Architecture): Clarified System Admin = Odoo Web only, explicitly blocked from REST API
- Forbidden Patterns: Added REST API authentication by base.group_system as a forbidden pattern

Sections Added:
- Security Requirements → SaaS Admin Channel Separation Patterns (Feature 022)
- Reference Implementations → Feature 022 — Admin UI Cross-Company Access

Removed Sections:
- (none)

Patterns Documented (new in this version):
1. Cross-Company Record Rule Override: domain_force=[(1,'=',1)] + groups=[(4, ref('base.group_system'))]
   grants SaaS Admin unrestricted cross-company visibility while preserving business-profile isolation.
2. Admin API Login Block: Explicit group check in login controller rejects base.group_system with
   HTTP 401 + audit log. Returns 401 (not 403/404) — response identical to bad-credential failure
   (anti-enumeration: channel rejection must not reveal admin credential validity).
3. noupdate="1" Compatibility: New admin override rules go in a separate noupdate="0" block within the
   same XML file to ensure they apply on --update without disturbing existing noupdate rules.
4. Developer Checklist Convention: Every new module introducing record rules with company isolation MUST
   include a SaaS Admin cross-company override rule (to be added to the new-module KB checklist).

Templates Requiring Updates:
✅ constitution.md — Updated (this file)
✅ plan-template.md — No update required (Constitution Check section is generic)
✅ spec-template.md — No update required (no admin-specific mandatory sections needed)
✅ tasks-template.md — No update required (task structure is generic)

Footer Version Bug Fixed:
Previous footer incorrectly showed v1.6.0 (was not updated in v1.7.0 amendment). Fixed to v1.8.0.

Follow-up TODOs:
- Add "SaaS Admin record rule override" to new-module developer checklist in knowledge_base/

Previous Amendments:
- 2026-05-08 (v1.7.0 Feature 017 binary upload patterns)
- 2026-05-03 (v1.6.0 Feature 015 service pipeline patterns)
- 2026-02-16 (v1.3.0 Feature 009 security patterns)
- 2026-02-08 (v1.2.0 Feature 007 reference implementation)
-->
<!--
Sync Impact Report - Constitution v1.7.0
========================================

Version Change: 1.6.0 → 1.7.0
Change Type: MINOR (new architectural patterns from Feature 017 — Property Attachments Upload API)
Date: 2026-05-08

Sections Added:
- Feature 017 entry in Reference Implementations
- `_att_error()` FR6.9 error envelope helper pattern documented
- Magic bytes MIME validation pattern (python-magic + libmagic)
- Hardcoded quantity limits pattern (not ir.config_parameter)
- `ir.attachment` as binary storage entity for property files
- Hard-delete exception to ADR-015 soft-delete rule
- Download URL invariant: /api/v1/ route only, never /web/content/

New Patterns Documented:
1. **FR6.9 Error Envelope**: Always `{"error": "<snake_case>", "detail": "<string>", ...extras}` — never `message` key. Extra fields per code (e.g., `received`, `max_size_bytes`, `received_size`, `limit`, `current`).
2. **`_att_error()` Pattern**: Module-local helper that bypasses shared `error_response()` (which uses `message` key). Use when a feature needs FR6.9-compliant errors incompatible with shared util.
3. **Magic Bytes MIME**: Use `python-magic` to detect MIME from file content (not extension). Separate whitelists per `attachment_type`. Global whitelist = union. Emit 415 `unsupported_mime` or `mime_mismatch` accordingly.
4. **Hardcoded Quantity Constants**: When limits are product decisions (not runtime-configurable), use module-level constants instead of `ir.config_parameter` to avoid unhandled ValueError on missing params.
5. **Hard-Delete Exception**: `ir.attachment.unlink()` is permissible for binary blobs to reclaim disk. Always document the ADR-015 exception explicitly in the spec/contract.

Previous Amendments:
- 2026-05-03 (v1.6.0)
- 2026-04-27 (v1.5.0)
- 2026-02-16 (v1.3.0 Feature 009 reference implementation)
- 2026-02-08 (v1.2.0 Feature 007 reference implementation)
-->
<!--
Sync Impact Report - Constitution v1.6.0
========================================

Version Change: 1.5.0 → 1.6.0
Change Type: MINOR (new architectural patterns from Feature 015 — Service Pipeline)
Date: 2026-05-03

Sections Added:
- **Pipeline State Machine Pattern**: Linear-with-rollback FSM with mail.thread auditing
- **Aggregation Endpoint Pattern**: GET /resource/summary for kanban-style counters
- **Conditional Uniqueness via PostgreSQL EXCLUDE Constraint**: Unique only for active/non-final records
- **System Tag Pattern**: Immutable tags driving business rules (`is_system=True`)
- **Pipeline Stage Gate Validators**: @api.constrains gating stage transitions on related records
- Feature 015 entry in Reference Implementations (planned/spec stage)

New Patterns Documented:
1. **Pipeline State Machine**: Stages declared as Selection field; @api.constrains gate transitions; mail.thread mixin records every transition with timestamp + user; rollback permitted with audit; terminal states (won/lost) prevent further movement.
2. **Aggregation Endpoint**: GET /resource/summary returning counts per stage filtered by company; SQL GROUP BY query; optional Redis cache TTL 30s; respects record rules.
3. **EXCLUDE Constraint**: PostgreSQL EXCLUDE constraint with WHERE clause for conditional uniqueness (e.g., "unique active record per natural key, ignoring archived/terminal"). Requires PostgreSQL 14+.
4. **System Tag**: Boolean `is_system` flag on tag entities; system tags are immutable by users (validated in @api.constrains on write/unlink); they drive business rules (e.g., presence locks pipeline movement).
5. **Stage Gate Validator**: @api.constrains validating that target stage's required relations exist (e.g., proposal stage requires property_ids; formalization requires approved proposal). ValidationError with user-facing reason.

Feature 015 — Service Pipeline (Atendimentos) [SPEC STAGE]:
- New entity `real.estate.service` distinct from `real.estate.lead` (different responsibilities)
- 7-stage pipeline: no_service → in_service → visit → proposal → formalization → won/lost
- Auxiliary entities: service.tag, service.source, partner.phone, service.settings (singleton per company)
- 9 REST endpoints with triple decorator (ADR-011); summary endpoint for kanban
- RBAC matrix covering Owner/Manager/Agent/Reception/Prospector
- Conditional unique active service per (client, type, agent) via EXCLUDE
- Multi-tenancy + soft delete + HATEOAS + audit via mail.thread
- Spec: `specs/015-service-pipeline-atendimentos/spec.md` (+ `spec-idea.md` for technical detail)
- Status: Specification approved; plan/implementation pending

Constitutional Compliance Verification - Feature 015 (spec):
✅ Principle I (Security First): Triple decorator on all 9 authenticated endpoints, multi-tenancy via record rules
✅ Principle II (Test Coverage): Unit tests for all stage gates, EXCLUDE constraint, RBAC; E2E API + Cypress admin
✅ Principle III (API-First): 9 REST endpoints with HATEOAS, OpenAPI via thedevkitchen_api_endpoint, Postman planned
✅ Principle IV (Multi-Tenancy): company_id on every entity (service, tag, source, settings), record rules per profile
✅ Principle V (ADR Governance): References ADR-001/003/004/005/007/008/009/011/015/016/017/018/019/022
✅ Principle VI (Headless Architecture): API for all 9 profiles via headless frontend; Odoo UI restricted to admin

Template Files Status:
✅ constitution.md - Updated with Feature 015 patterns and reference implementation
✅ Architectural Patterns section expanded (state machine, aggregation, EXCLUDE, system tags)
✅ Reference Implementations updated

Propagation: Pending implementation (plan → tasks → implement phases)

Previous Amendments:
- 2026-04-27 (v1.5.0)
- 2026-02-16 (v1.3.0 Feature 009 reference implementation)
- 2026-02-08 (v1.2.0 Feature 007 reference implementation)
-->
<!--
Sync Impact Report - Constitution v1.3.0
========================================

Version Change: 1.2.0 → 1.3.0
Change Type: MINOR (new reference implementation + security patterns documented)
Date: 2026-02-16

Sections Modified:
- Updated test statistics in Quality & Testing Standards
- Added Feature 009 as reference implementation for security patterns
- Added new security patterns section (token-based auth, anti-enumeration)
- Updated Forbidden Patterns with public endpoint marker requirement
- Added transactional email patterns (mail.template)
- Added singleton configuration model pattern
- Added rate limiting pattern documentation

New Content Added:
- **Security Patterns Section**: Token-based onboarding, anti-enumeration, public endpoint markers
- **Email Integration Patterns**: mail.template usage for transactional emails
- **Configuration Patterns**: Singleton model with validation constraints
- **Rate Limiting Patterns**: Redis-based with placeholder pattern
- **Atomic Transactions**: Dual record creation for portal entities
- **Session Management**: Session invalidation after password reset
- Feature 009 User Onboarding & Password Management as constitutional compliance example
- Updated test count statistics (Unit: 100+ → 190+)

Constitutional Compliance Verification - Feature 009:
✅ Principle I (Security First): Triple auth for invite (@require_jwt + @require_session + @require_company), anti-enumeration on forgot-password
✅ Principle II (Test Coverage): 90+ unit tests (4 test files), E2E tests, integration tests
✅ Principle III (API-First): 5 REST endpoints (1 authenticated invite, 3 public password, 1 resend)
✅ Principle IV (Multi-Tenancy): Token isolation via company_id, record rules enforced
✅ Principle V (ADR Governance): ADR-003 (testing), ADR-008 (anti-enumeration), ADR-011 (security), ADR-018 (validation)
✅ Principle VI (Headless Architecture): Public password endpoints for SSR frontend, authenticated invite for management

Reference Implementation - Feature 009:
- 5 REST endpoints (invite, set-password, forgot-password, reset-password, resend-invite)
- SHA-256 token hashing (UUID v4 → SHA-256 stored, raw token in email only)
- Anti-enumeration: forgot-password always returns 200 regardless of email existence
- Public endpoint pattern: `# public endpoint` comment above @http.route
- Email templates: mail.template integration with context variables
- Singleton settings: thedevkitchen.email.link.settings (TTL, rate limits)
- Authorization matrix: Owner→all 9 profiles, Manager→5 operational, Agent→owner+portal
- Portal dual record: Atomic res.users + real.estate.tenant via partner_id
- Session invalidation: api_session.is_active=False after password reset
- Rate limiting: Redis placeholder with TODO for production implementation
- Unit tests: 90+ test methods across 4 files (authorization, validation, token lifecycle, settings)
- Location: `18.0/extra-addons/thedevkitchen_user_onboarding/`

New Security Patterns Documented:
1. **Token-Based Onboarding**: Generate UUID v4, hash with SHA-256, store hash only, send raw token once
2. **Anti-Enumeration**: Public endpoints never reveal user existence (always 200 on forgot-password)
3. **Public Endpoint Marker**: `# public endpoint` comment mandatory for auth='none' routes
4. **Mail Template Integration**: Use mail.template model with context variables for transactional emails
5. **Singleton Configuration**: Single record configuration with get_settings() class method
6. **Rate Limiting Placeholder**: Log warning if Redis not available, allow request (fail-open for dev)
7. **Atomic Dual Record**: Odoo transaction for res.users + domain entity via partner_id linkage
8. **Session Invalidation**: Mark all user sessions inactive after security-sensitive operations

Template Files Status:
✅ constitution.md - Updated with Feature 009 reference and security patterns
✅ ADR-003 compliance (unit tests), ADR-008 (anti-enumeration), ADR-011 (security)
✅ Test pyramid statistics updated (190+ unit tests)
✅ Security patterns section added for token handling and session management

Propagation Complete:
✅ Unit tests passing (90+ test methods)
✅ All models with proper validation constraints
✅ Controllers following public endpoint marker pattern
✅ Services implementing authorization matrix
✅ Email templates created in Portuguese (pt_BR)
✅ Settings UI with Odoo 18.0 standards (no attrs, field grouping)

Follow-up Actions: E2E tests, Postman collection (ADR-016), translations, linting validation
Previous Amendment: 2026-02-08 (v1.2.0 Feature 007 reference implementation)
-->

# Realestate Backend Platform Constitution

## Core Principles

### I. Security First (NON-NEGOTIABLE)
Every API endpoint MUST use defense-in-depth authentication:
- `@require_jwt` validates OAuth 2.0 JWT tokens
- `@require_session` ensures user identification and state (not replaceable by generic OAuth)
- `@require_company` enforces multi-tenant data isolation
- Public endpoints MUST explicitly document with `# public endpoint` comment
- Session hijacking protection via fingerprinting (IP + User-Agent + Language)

**Rationale**: Brazilian real estate data has legal and privacy implications. Multi-layered security prevents single-point authentication failures and ensures compliance with LGPD (Brazilian data protection law).

### II. Test Coverage Mandatory (NON-NEGOTIABLE)
All code MUST achieve minimum 80% test coverage (per ADR-003):
- Unit tests for business logic and utilities
- Integration tests for API endpoints (auth, validation, permissions, edge cases)
- E2E tests (Cypress) for complete user journeys
- Tests MUST be written before PR submission
- PRs automatically rejected if coverage drops below 80%

**Rationale**: Real estate transactions involve financial and legal commitments. High test coverage prevents regressions that could cause property mismatches, pricing errors, or data corruption.

### III. API-First Design (NON-NEGOTIABLE)
All features expose RESTful APIs with:
- OpenAPI 3.0 documentation (Swagger UI at `/api/docs`)
- Postman collections (ADR-016) for endpoint testing and documentation
- HATEOAS hypermedia links (ADR-007, planned Phase 3)
- JSON request/response formats
- Consistent error responses (`success_response()`, `error_response()`)
- Master data endpoints for frontend hydration

**Postman Collection Requirements** (ADR-016):
- Location: `/docs/postman/`
- Naming: `{feature}_v{major.minor}_postman_collection.json`
- Must include: OAuth flow, session management, test scripts
- Auto-save tokens to collection variables
- Proper headers: GET uses `X-Openerp-Session-Id` header, POST/PUT/DELETE use body
- **Reference**: Feature 007 collection (`feature007_owner_company_v1.0_postman_collection.json`)

**Rationale**: Headless frontend architecture requires well-documented, discoverable APIs. HATEOAS enables frontend evolution without hardcoded URLs. Postman collections provide executable documentation that doubles as integration testing tool.

### IV. Multi-Tenancy by Design (NON-NEGOTIABLE)
Complete data isolation per real estate company (ADR-008):
- Users belong to one or more `company_ids`
- All queries filtered by company context via `@require_company`
- Creation/update operations validate company ownership
- Record Rules enforce isolation in Odoo Web UI
- No cross-company data leakage (tested via isolation tests)
- **SaaS Admin Exception**: `base.group_system` users (System Admins) operate exclusively via Odoo Web UI and intentionally bypass company isolation to manage all tenant data. This exception applies ONLY to the Odoo web interface — REST API isolation remains absolute for every user, including System Admins.

**Rationale**: Brazilian real estate agencies compete directly. Data leakage between companies would violate confidentiality and business trust. The SaaS Admin exception is explicitly scoped to the administrative web interface only, preserving API-level isolation unconditionally.

### V. ADR Governance
All architectural decisions documented as ADRs in `docs/adr/`:
- ADRs are authoritative for patterns, naming, workflows
- Code reviews MUST verify ADR compliance (especially ADR-001, ADR-011)
- New patterns require ADR creation before implementation
- ADRs include: context, decision, consequences, examples

**Rationale**: Distributed team + AI agents require consistent, searchable decision history to prevent pattern drift and ensure maintainability.

### VI. Headless Architecture (NON-NEGOTIABLE)
Platform employs dual-interface design:
- **Real Estate Agencies**: Headless SSR frontend (Next.js/React) consuming REST APIs
  - Enhanced security through SSR (credentials never reach client browser)
  - Better SEO for property listings
  - Modern UX/UI tailored for real estate workflows
  - Access via OAuth 2.0 REST APIs only (no direct Odoo Web access)
- **Platform Managers (System Admin)**: Odoo Web interface for system administration **only**
  - Backend management, configuration, database administration
  - Direct Odoo Web UI access for operational oversight across all tenant companies
  - MUST NOT authenticate via REST API — `base.group_system` is explicitly blocked at the login endpoint
  - Created and managed exclusively through the Odoo web interface (never via API invite flow)

**Why Odoo Framework**: Robust ORM, built-in multi-company support, security framework, proven scalability

**Rationale**: Complete UX control for agencies, SSR security advantages (sensitive data never in client-side code), API-first enables future mobile apps, frontend/backend independent evolution.

## Security Requirements

### Dual-Interface Security Model
- **Headless Frontend (SSR)**: Server-Side Rendering prevents credential exposure in client browser
  - Authentication tokens handled server-side only
  - API calls from SSR backend to Odoo backend
  - Public pages (property listings) benefit from SEO optimization
- **Odoo Web (Managers)**: Standard Odoo authentication for internal platform management

### Authentication Standards (ADR-009, ADR-011)
- OAuth 2.0 for application-to-application (Client Credentials Grant)
- Session-based with JWT for user authentication
- Token lifetime: 24 hours (configurable)
- Redis-backed session storage (**DB index 1**, AOF persistence)
- Redis used for **JWT and session lookup cache** (Feature 023) — eliminates 2 SELECTs + 1 UPDATE per authenticated request
- Rate limiting on authentication endpoints (brute-force protection)
- Audit logging for all security events

### Async Processing Architecture (ADR-021)
Eventos não-críticos processados via **RabbitMQ + Celery** (3 workers especializados):

| Worker | Fila | Concurrency | Uso |
|--------|------|-------------|-----|
| `celery_commission_worker` | `commission_events` | 2 | Cálculo de comissões |
| `celery_audit_worker` | `audit_events` | 1 | Audit logs / LGPD |
| `celery_notification_worker` | `notification_events` | 1 | Emails, webhooks |

**Regras**:
- Eventos `before_*` / validações → **sempre síncronos** (bloqueiam request)
- Audit, notificações, bulk ops → **assíncronos** via `EventBus.emit()`
- Redis DB separado: Odoo usa **DB 1** (`redis_dbindex=1`), Celery usa **DB 2** (`CELERY_RESULT_BACKEND=redis://redis:6379/2`)
- Celery client instalado no Odoo Dockerfile (`celery[redis]==5.3.4`)
- Monitoramento: Flower em `http://localhost:5555`

### Forbidden Patterns
- `.sudo()` abuse in controllers (bypasses security)
- `auth='public'` without `# public endpoint` comment above route
- Single decorator (`@require_jwt` alone without `@require_session`)
- Hardcoded credentials or secrets in code
- Exposing user existence in public endpoints (anti-enumeration violation)
- REST API authentication by `base.group_system` users — System Admins MUST use Odoo web interface only; return HTTP 401 (not 403/404) when blocked — response MUST be identical to a bad-credential failure (anti-enumeration: channel rejection MUST NOT reveal admin credential validity)

### Token-Based Authentication Patterns (Feature 009)
For invite links, password reset tokens, or similar one-time-use tokens:
1. **Generation**: Generate UUID v4 (32 hex chars), hash with SHA-256 (64 hex chars), store hash only
2. **Distribution**: Send raw token via email/SMS once, never log or expose again
3. **Validation**: Compute SHA-256 of received token, search by hash
4. **State Machine**: Token states: pending → used/expired/invalidated
5. **Expiry**: Use TTL from configuration singleton, auto-expire in cron or on validation
6. **Invalidation**: Mark previous tokens as invalidated when generating new token for same user+type

**Rationale**: SHA-256 prevents rainbow table attacks. Raw token never stored. State machine ensures single use. Auto-expiry limits attack window.

### Anti-Enumeration Patterns (ADR-008)
Public endpoints that accept user identifiers (email, username, document) MUST NOT reveal whether the identifier exists:
- **Forgot Password**: Always return 200 with generic message, only send email if user exists
- **User Lookup**: Return 404 for both "not found" and "not authorized"
- **Login Attempts**: Rate limit by IP, delay response by constant time regardless of success/failure

**Example** (forgot-password endpoint):
```python
# Always return success, log attempts for non-existent emails
def forgot_password(self, email):
    user = env['res.users'].search([('login', '=', email), ('active', '=', True)])
    if not user:
        _logger.info(f"Forgot password attempt for non-existent email: {email}")
        return True  # Never reveal user doesn't exist
    # Only send email if user exists
    self._send_reset_email(user)
    return True
```

**Rationale**: Prevents enumeration attacks where adversaries discover valid emails/usernames, reducing phishing and targeted attacks.

### Transactional Email Patterns (mail.template)
Use Odoo's `mail.template` model for all transactional emails (invites, resets, notifications):
1. **Template Creation**: Create `mail.template` records in data XML
2. **Context Variables**: Use `${ctx.get('variable')}` for dynamic values from service layer
3. **User Variables**: Use `${object.field}` for res.users fields (name, email, company)
4. **HTML + Plain Text**: Provide body_html for rich formatting, fallback to body_text
5. **Language Support**: Use `lang="${object.lang}"` for multi-language support
6. **Async Sending**: Use `force_send=False` to queue emails (better performance)
7. **Error Handling**: Catch send failures, log error, continue operation (email failure shouldn't block user creation)

**Example** (invite email template):
```xml
<record id="email_template_user_invite" model="mail.template">
    <field name="name">User Invitation Email</field>
    <field name="model">res.users</field>
    <field name="subject">Convite para ${object.company_id.name}</field>
    <field name="body_html" type="html">
        <p>Olá ${object.name},</p>
        <p>Você foi convidado para: <a href="${ctx.get('invite_link')}">${ctx.get('invite_link')}</a></p>
        <p>Este link expira em ${ctx.get('expires_hours')} horas.</p>
    </field>
</record>
```

**Rationale**: Centralized email templates enable multi-language support, consistent branding, and A/B testing without code changes. Odoo's queue prevents email slowdowns.

### Singleton Configuration Model Pattern
For application-wide settings (link TTL, rate limits, feature flags):
1. **Model**: Create model with no explicit uniqueness, enforce in class method
2. **get_settings() Class Method**: Search for first record, create default if none exists
3. **Validation Constraints**: Use `@api.constrains` for value range validation (e.g., 1-720 hours)
4. **UI**: Form view in singleton mode (`view_mode='form'`, auto-open single record)
5. **Default Data**: Provide default record in data XML with sensible values

**Example**:
```python
class EmailLinkSettings(models.Model):
    _name = 'thedevkitchen.email.link.settings'
    _description = 'Email Link Configuration'
    
    invite_link_ttl_hours = fields.Integer(default=24)
    
    @api.constrains('invite_link_ttl_hours')
    def _check_link_ttl_positive(self):
        for record in self:
            if not (1 <= record.invite_link_ttl_hours <= 720):
                raise ValidationError("TTL must be between 1 and 720 hours")
    
    @classmethod
    def get_settings(cls, env):
        settings = env['thedevkitchen.email.link.settings'].search([], limit=1)
        if not settings:
            settings = env['thedevkitchen.email.link.settings'].create({})
        return settings
```

**Rationale**: Singleton pattern avoids configuration ambiguity. Validation prevents invalid states. Class method ensures default creation. UI provides admin control without code deployment.

### Rate Limiting Pattern (Redis-based with Placeholder)
For public endpoints vulnerable to abuse (forgot-password, login):
1. **Redis Key**: `rate_limit:{endpoint}:{identifier}` (e.g., `rate_limit:forgot_password:user@example.com`)
2. **INCR + EXPIRE**: Atomic increment with TTL (e.g., 3600s for 1 hour window)
3. **Check Before Operation**: Call `check_rate_limit()` before expensive operations
4. **Fail-Open in Dev**: If Redis unavailable, log warning and allow request (dev environment)
5. **Fail-Closed in Prod**: If Redis unavailable in prod, return 503 (circuit breaker)
6. **Return Metadata**: Return `{allowed: bool, attempts: int, limit: int, window_seconds: int}`

**Placeholder Pattern** (for development without Redis):
```python
def check_rate_limit(self, identifier, limit_key):
    settings = self.env['thedevkitchen.email.link.settings'].get_settings()
    limit = getattr(settings, limit_key)
    
    # TODO: Implement Redis integration
    _logger.warning(f"Rate limiting not implemented (Redis integration pending), allowing request for {identifier}")
    return {'allowed': True, 'attempts': 0, 'limit': limit, 'window_seconds': 3600}
```

**Rationale**: Rate limiting prevents brute-force and DOS attacks. Redis INCR is atomic and fast. Placeholder pattern enables development without full infrastructure. Fail-open in dev balances security and developer experience.

### Redis Cache Patterns for Auth Hot Path (Feature 023)

Every authenticated request passes through `@require_jwt` and `@require_session`. These decorators historically issued 2 SELECTs + 1 UPDATE on PostgreSQL for each request. Feature 023 caches these lookups in Redis, reducing DB load to zero on cache hits while maintaining full security guarantees.

#### RedisClient Singleton

Single module-level class with a `ConnectionPool` (not per-request connections):

```python
class RedisClient:
    _pool = None

    @classmethod
    def _get_connection(cls):
        # Lazy init — reads redis_host, redis_port, redis_dbindex, redis_pass, enable_redis
        # from odoo.tools.config; returns None if enable_redis is falsy
        # Uses redis.ConnectionPool (one pool per Odoo worker process)

    @classmethod
    def get_json(cls, key: str) -> dict | None:
        # GET key → json.loads; ANY exception → _logger.warning → return None

    @classmethod
    def set_json(cls, key: str, data: dict, ttl: int) -> bool:
        # ttl ≤ 0 → skip (never cache an already-expired value)
        # SETEX key ttl json.dumps(data); exception → _logger.warning → return False

    @classmethod
    def delete(cls, *keys: str) -> bool:
        # DEL key1 key2 ...; exception → return False

    @classmethod
    def delete_pattern(cls, pattern: str) -> int:
        # SCAN (not KEYS) + DEL in batches; returns count deleted; exception → return 0
```

**Absolute rule**: `get_json`, `set_json`, `delete`, `delete_pattern` MUST NOT propagate exceptions. The application functions at 100% correctness without Redis (graceful degradation to PostgreSQL).

**Location**: `thedevkitchen_apigateway/services/redis_client.py`

#### JWT Cache Pattern

Cache key: `jwt:{sha256(raw_access_token).hexdigest()[:32]}`

- **Never use the raw token as a Redis key** — hash prevents key-space enumeration if Redis memory is inspected.
- **Payload**: `{"id": int, "application_id": int, "token_type": str, "expires_at_ts": float, "scope": str, "revoked": bool}`
- **TTL**: `max(0, int(expires_at.timestamp() - time.time()))` — derived directly from the token's own expiry. No arbitrary cap: the JWT already defines its own lifetime. A TTL ≤ 0 means the token is already expired; skip caching entirely (`set_json` discards TTL ≤ 0 by contract).
- **Cache HIT**: validate `expires_at_ts <= time.time()` and `revoked == True` in-memory → reject with 401 without touching DB; set `request.jwt_token = Token.browse(id)` (lazy ORM record, zero SELECT).
- **Cache MISS**: full `Token.search()` as today → cache populated after validation.
- **Invalidation**: Override `OAuthToken.action_revoke()` → compute hash → `RedisClient.delete(key)`.

```python
def action_revoke(self):
    result = super().action_revoke()
    try:
        from ..services.redis_client import RedisClient
        for record in self:
            key = f"jwt:{hashlib.sha256(record.access_token.encode()).hexdigest()[:32]}"
            RedisClient.delete(key)
    except Exception:
        pass  # Never block the revoke operation
    return result
```

#### Session Cache Pattern

Cache key: `session:{session_id}` (session_id is the Odoo session SID — opaque, 64+ chars, safe as key).

- **Payload includes `security_token`**: The JWT de fingerprint stored in `api_session.security_token` is required by `require_session` for `jwt.decode()`. Including it in cache allows `api_session = browse(id)` to stay lazy — accessing `api_session.security_token` is from-memory (no SELECT by PK).
- **Odoo 18 field cache injection**: After `browse(id)`, pre-populate the ORM field cache:
  ```python
  env.cache.set(api_session, APISession._fields['security_token'], cached['security_token'])
  env.cache.set(api_session, APISession._fields['is_active'], True)
  env.cache.set(api_session, APISession._fields['company_id'], cached['company_id'])
  env.cache.set(user, Users._fields['active'], True)
  ```
- **TTL**: Read `session_cache_ttl_seconds` from `thedevkitchen.security.settings.get_settings()` (default 300s). Sessions have no `expires_at` of their own — the configurable TTL controls re-validation frequency. Two fields must be added to `thedevkitchen.security.settings`: `session_cache_ttl_seconds` (Integer, default 300) and `session_inactivity_days` (Integer, default 7, consumed by `SessionValidator.cleanup_expired()`).
- **`last_activity` trade-off**: On cache HIT, `UPDATE last_activity` is **skipped**. The field is updated only on cache MISS (~every `session_cache_ttl_seconds`). This is an explicit trade-off: `last_activity` is a usage metric, not a security control. Document this decision when implementing.
- **Invalidation**: Override `APISession.write()` — delete cache key when `is_active` or `company_id` changes:

```python
def write(self, vals):
    result = super().write(vals)
    if 'is_active' in vals or 'company_id' in vals:
        try:
            from ..services.redis_client import RedisClient
            for record in self:
                RedisClient.delete(f"session:{record.session_id}")
        except Exception:
            pass  # Never block the write operation
    return result
```

This single override covers: logout, login (invalidates old sessions), switch-company, session cleanup cron, and user deactivation — all without modifying any of those call sites.

#### Cache-Before-Invalidation Deployment Order (MANDATORY)

When deploying Redis cache for any mutable entity:

1. **Deploy invalidation write hooks first** (before any cache population code is active).
2. **Only then activate cache HIT paths** (the `if cached:` branches).
3. **Rationale**: If cache population runs before invalidation hooks, a write event (e.g., logout immediately after deploy) fails to evict the new cache entry, creating a stale-data window. Deploying hooks first eliminates this race.

**Rationale for the full pattern**: Eliminating 2 SELECTs + 1 UPDATE per authenticated request reduces DB load proportionally to request volume. At 100 req/s, that is 300 DB operations/s eliminated. Redis latency (~0.3ms) vs PostgreSQL (~5ms) yields a measurable p95 improvement on every endpoint using triple decorators. Graceful fallback ensures Redis downtime does not affect correctness — only performance.
When creating portal users that require domain entity (e.g., res.users + real.estate.tenant):

### Atomic Dual Record Creation (Portal Entities)
When creating portal users that require domain entity (e.g., res.users + real.estate.tenant):
1. **Single Transaction**: Use Odoo's implicit transaction (no explicit `with env.cr.savepoint()`)
2. **Order Matters**: Create res.users first (Odoo auto-creates res.partner), then create domain entity with `partner_id=user.partner_id.id`
3. **Validation First**: Check for conflicts (duplicate document, existing tenant without user) before creation
4. **Link via partner_id**: Domain entity references res.partner, which links to res.users
5. **Error Handling**: If domain entity creation fails, transaction rolls back (res.users also deleted)
6. **Return Both**: Return both user_id and domain_entity_id in API response

**Example** (portal tenant creation):
```python
def create_portal_user(self, name, email, document, phone, birthdate, company_id):
    # Step 1: Check for conflicts
    existing_tenant = env['real.estate.tenant'].search([('document', '=', document)])
    if existing_tenant and not existing_tenant.user_id:
        raise ValidationError("Document already exists for unlinked tenant")
    
    # Step 2: Create res.users (portal group, password=False)
    user = env['res.users'].create({
        'name': name,
        'login': email,
        'email': email,
        'password': False,
        'signup_pending': True,
        'groups_id': [(6, 0, [env.ref('base.group_portal').id])],
    })
    
    # Step 3: Create domain entity linked via partner_id
    tenant = env['real.estate.tenant'].create({
        'partner_id': user.partner_id.id,  # Link to auto-created partner
        'document': document,
        'phone': phone,
        'birthdate': birthdate,
        'company_id': company_id,
    })
    
    return user, tenant
```

**Rationale**: Atomic transaction ensures data consistency. Order prevents orphaned partners. partner_id linkage is Odoo's standard pattern. Conflict check prevents data corruption. Rollback on failure maintains database integrity.

### Session Invalidation After Security Operations
After password reset or account compromise, invalidate all active sessions:
1. **Session Model**: Search `thedevkitchen.api.session` for user_id where is_active=True
2. **Bulk Update**: Write {is_active: False} to all matching sessions
3. **Logging**: Log count of invalidated sessions for audit trail
4. **Timing**: Invalidate AFTER password change succeeds (not before)
5. **User Communication**: Email user about active sessions terminated (security notification)

**Example**:
```python
def _invalidate_user_sessions(self, user):
    sessions = self.env['thedevkitchen.api.session'].search([
        ('user_id', '=', user.id),
        ('is_active', '=', True)
    ])
    count = len(sessions)
    sessions.write({'is_active': False})
    _logger.info(f"Invalidated {count} sessions for user {user.id} after password reset")
    return count
```

**Rationale**: Session invalidation prevents session hijacking after password change. Attacker with stolen session token loses access. User receives security notification. Audit log enables forensic analysis.

### Explicit Group Check for Owner (Owner ≠ implies Manager) (Feature 027)
When authorizing an action restricted to the company Owner, check `owner OR admin` explicitly against a list of group XML IDs — never assume that checking only `manager` also covers `owner` via Odoo's `implied_ids` group hierarchy:

```python
PROFILE_DEACTIVATE_REACTIVATE_GROUPS = [
    "quicksol_estate.group_real_estate_owner",
    "base.group_system",
]

def _user_can_deactivate_or_reactivate_profile(self, user):
    return any(
        user.has_group(group_xml_id)
        for group_xml_id in PROFILE_DEACTIVATE_REACTIVATE_GROUPS
    )
```

**Why this matters**: In this project's `security/groups.xml`, `group_real_estate_owner` does **not** imply `group_real_estate_manager` (or vice versa) — they are siblings, not a hierarchy. A check that only tests `has_group('...manager')`, assuming it also passes for Owner, silently locks Owners out (or, in the inverse mistake, silently authorizes Manager for an Owner-only action). This exact bug class existed in the legacy `agent_api.py` deactivate/reactivate endpoints (removed in Feature 027) before being fixed and generalized to `/api/v1/profiles`.

**Rationale**: Group hierarchy in Odoo is opt-in per `implied_ids`, not inferred from role seniority. Every authorization check MUST enumerate its accepted groups explicitly and test each with `has_group()` — treating "Owner implies Manager" (or any other unverified hierarchy assumption) as true is a recurring, easy-to-introduce bug class.

### res.users Management is Owner-Only, Even Transitively (via Cascade) (Feature 027)
Any endpoint that cascades into `res.users` fields (e.g. `active`) inherits the same Owner-only authorization restriction already codified for direct user management (ADR-019 + `security/ir.model.access.csv`) — **regardless of the endpoint's nominal subject**. Manager and Director, even with broad CRUD authority over `profile`/`agent`, do NOT gain authorization over `res.users` just because the endpoint is nominally "about a profile":

```python
def _deactivate_profile_cascade(self, profile, reason=None):
    """profile -> agent -> res.users -> session, all gated by the SAME
    owner/admin-only check as the endpoint that calls this — never a
    weaker one, even though only the last hop touches res.users."""
    ...
```

**Rationale**: `res.users` is the most sensitive entity a "profile" endpoint can transitively touch — deactivating it locks out a login. Authorization for the whole cascade must be no weaker than the strictest resource it touches, not the nominal resource of the endpoint (`profile`). Any future endpoint that cascades into `res.users` (directly or through an intermediate model) MUST apply this same rule.

### SaaS Admin Channel Separation Patterns (Feature 022)
The SaaS Admin (`base.group_system`) is a platform-level role above all business profiles. It operates
exclusively through the Odoo web interface — never through the REST API. All patterns below enforce this
channel boundary.

#### Cross-Company Record Rule Override
For every Odoo model that has multi-tenancy record rules blocking the SaaS Admin, add a complementary
rule with `domain_force=[(1,'=',1)]` assigned to `base.group_system`:

```xml
<!-- ADR-008 §3: Admin accesses via administrative interface -->
<!-- ADR-019: SaaS Admin operates above business role hierarchy -->
<record id="rule_admin_all_{entity}" model="ir.rule">
    <field name="name">System Admin: All {Entity} (Cross-Company)</field>
    <field name="model_id" ref="model_{module}_{entity}"/>
    <field name="domain_force">[(1, '=', 1)]</field>
    <field name="groups" eval="[(4, ref('base.group_system'))]"/>
</record>
```

**Why this works (Odoo native)**: When a user belongs to multiple groups that each have record rules for
the same model, Odoo combines them with OR (union). The `[(1,'=',1)]` rule for `base.group_system`
therefore overrides any company-filtered rules the admin inherits from `base.group_user`.

**noupdate="1" compatibility**: When the target file contains `noupdate="1"` blocks, place the new admin
rules in a **separate** `<data noupdate="0">` block within the same XML file. This ensures the rules are
applied on `--update` without disturbing existing noupdate rules.

**Developer checklist**: Every new module that introduces record rules with company isolation MUST include
a corresponding SaaS Admin cross-company override rule. Omitting it locks the System Admin out of new
data silently.

#### Admin API Login Block
In the REST API login controller, check for `base.group_system` AFTER validating credentials and BEFORE
issuing a session token:

```python
# Block SaaS Admin from REST API (ADR-009: API is for headless apps only)
if user.has_group('base.group_system'):
    _logger.warning(f"Admin login attempt via API blocked: {email}")
    AuditLogger.log_failed_login(ip_address, email, 'Admin API login blocked')
    return request.make_json_response(
        {'error': {'status': 401, 'message': 'Invalid credentials'}},
        status=401
    )
```

**Why 401 not 403**: Anti-enumeration principle (ADR-008) — the response for a blocked admin login MUST
be indistinguishable from an invalid-credential failure. Returning 403 would reveal that the admin
credentials are valid, enabling credential enumeration. HTTP 401 with a generic `'Invalid credentials'`
body preserves the same security envelope as a wrong-password attempt.

**Rationale**: System Admins bypass multi-tenancy controls by design. If they could authenticate via the
REST API they would expose all tenant data through a headless API intended for company-scoped users.
Channel separation (Odoo Web UI ↔ REST API) is the enforcement boundary. Audit logging captures all
blocked attempts for forensic review (ADR-008 §4).

## Architectural Patterns

### Pipeline State Machine Pattern (Feature 015)
For domain entities that flow through a sequence of stages (atendimentos, propostas, contratos):
1. **Stages as Selection field**: Declare all stages explicitly (`fields.Selection`) with stable codes (snake_case English) and translated labels.
2. **Linear flow with auditable rollback**: Forward transitions are the happy path; backward transitions are allowed but every transition (forward or backward) is recorded in `mail.thread` with timestamp + user + optional comment.
3. **Terminal states**: Final states (e.g., `won`, `lost`) prevent further movement except by explicit reopen (audited).
4. **Stage gate validators**: Use `@api.constrains('stage', '<related_field>')` to enforce that required relations exist before reaching certain stages (e.g., proposal stage requires `property_ids`; formalization requires approved proposal). Raise `ValidationError` with user-facing reason in pt_BR.
5. **System-tag locks**: A boolean `is_system` tag (e.g., `closed`) attached to the entity blocks `stage` writes; validated in `@api.constrains('stage','tag_ids')`.
6. **Mixin**: Inherit `mail.thread` and `mail.activity.mixin` for free audit timeline and activities.

**Rationale**: Centralizes pipeline rules in the model (single source of truth), prevents invalid states at the ORM level, gives free audit trail via Odoo's mail subsystem, and exposes uniform UX for backward compatibility (rollback allowed but accountable).

### Aggregation Endpoint Pattern (Kanban Summaries)
For pipeline UIs requiring per-stage counters or KPIs:
1. **Endpoint shape**: `GET /api/v1/{resource}/summary` returning `{stage_code: count, ...}` filtered by current company and respecting record rules.
2. **SQL strategy**: Single `GROUP BY` query (avoid N reads); leverage stored computed fields when filters are complex.
3. **Caching (optional)**: Redis cache (DB index 1) keyed by `summary:{model}:{company_id}:{user_id_or_role}` with TTL 30s; invalidate on write hooks of the underlying model.
4. **Auth**: Triple decorator (`@require_jwt + @require_session + @require_company`).
5. **Response < 100ms**: Mandatory for kanban responsiveness.
6. **HATEOAS**: Include `links` to filtered list endpoints (`?stage={code}`).

**Rationale**: Frontend kanbans need sub-second feedback. A dedicated aggregation endpoint avoids over-fetching list payloads just to count, scales linearly with stage count, and remains cacheable safely (short TTL).

### Conditional Uniqueness via PostgreSQL EXCLUDE Constraint
When a natural-key uniqueness rule applies only to **active/non-terminal** records (allowing historical duplicates):
1. **Use `EXCLUDE` constraint** with a `WHERE` predicate, not a partial UNIQUE index in `_sql_constraints` (Odoo `_sql_constraints` does not natively support partial UNIQUE; declare via migration script or `init.sql`).
2. **Example**: `EXCLUDE (client_partner_id WITH =, operation_type WITH =, agent_id WITH =) WHERE (active AND stage NOT IN ('won','lost'))`.
3. **Requires PostgreSQL 14+** (project standard).
4. **Pair with Python validation**: Catch `IntegrityError` in service layer and translate to user-facing 409 Conflict response.
5. **Idempotent migration**: Wrap constraint creation in `IF NOT EXISTS` check or Odoo migration script.

**Rationale**: Real-world domain rules frequently require uniqueness only on the "open" subset (one active proposal per property, one active service per client+type+agent). EXCLUDE constraint enforces this at the database level — the strongest guarantee — while preserving historical records for analytics.

### System Tag Pattern
For tag entities where some tags must be immutable and drive business rules:
1. **Schema**: Add `is_system = fields.Boolean(default=False)` to tag model.
2. **Seed in XML data**: System tags created with `is_system=True` and stable `xml_id` (e.g., `seed_service_tag_closed`).
3. **Immutability validators**: `@api.constrains('name','active','is_system')` rejects edits/deactivation when `is_system=True` (unless context flag explicitly bypasses, restricted to admin).
4. **Behavior coupling**: Models referencing tags use `tag_ids.filtered(lambda t: t.name == 'closed')` or check via xml_id (`env.ref('module.seed_service_tag_closed')`); presence triggers business rules (lock pipeline, flag, etc.).
5. **UI**: Read-only display in form views; CRUD restricted in controllers (403 for `is_system` writes).

**Rationale**: Some tags carry semantic weight beyond categorization (e.g., `closed` = locks pipeline). Marking them as system prevents accidental rename/deletion that would break business logic, while still allowing user-defined tags freely.

### Deliberate Authorization Hardening as a Cross-Cutting Fix (with Cross-Checking Against Existing Matrices) (Feature 027)
When an authorization inconsistency is discovered between an already-protected path and an unprotected legacy path for the same underlying resource (e.g. `agent`-typed profiles were owner/admin-gated on deactivate, but every other `profile_type` was not), the fix MAY legitimately be applied broadly — to all affected types/resources at once, not just the one where the gap was found:
1. **Broad hardening is acceptable** when the inconsistency has no principled reason to exist (here: there is no reason deactivating a `tenant` profile should be less protected than deactivating an `agent` profile).
2. **The resulting role matrix MUST be cross-checked against every ACL (`ir.model.access.csv`) and pre-existing authorization matrix touching the same entities before being finalized** — not just the one path where the gap was noticed. Feature 027's Task 5 cross-checked its new owner/admin-only deactivate/reactivate matrix against `security/groups.xml`, `security/ir.model.access.csv`'s `res.users` ACLs, and Feature 009's invite-authorization matrix, confirming none of them already grant Manager/Director an authority the new hardening would need to preserve.
3. **Document the breaking-change decision explicitly** (spec FR + OpenAPI description) rather than silently narrowing behavior — callers previously authorized under the inconsistent rule will start receiving 403s.

**Rationale**: A naive "harden this one broken case" fix leaves the same inconsistency latent for every other type/resource sharing the underlying pattern — the bug just moves, it doesn't disappear. But broadening the fix without cross-checking existing matrices risks *removing* a permission some other, already-correct part of the system deliberately grants — trading one bug for another. Both the "harden broadly" and the "verify against everything else that touches this resource" steps are required together.

### Platform-Level Non-Tenant Catalog Entity (Feature 028)
For an entity that must be visible platform-wide (across every company) rather than isolated per tenant — a curated catalog, not tenant data:
1. **No `company_id` field at all** — the entity does not belong to any tenant, so there is no column to isolate on.
2. **No `ir.rule` isolation** — since there is no company dimension, a record rule would have nothing to filter; access control is enforced entirely via `ir.model.access.csv` (model-level CRUD grants) plus an explicit role check inside the controller (`role not in (...)` → 403), not via record rules.
3. **Write path is Odoo-UI-only, by design** — grant full CRUD in `ir.model.access.csv` to `base.group_system` only; grant `perm_read=1` (never write/create/unlink) to the relevant internal-user group for consistency. No REST create/update/delete route exists for the entity at all — this is a direct application of the existing "SaaS Admin Channel Separation" principle (`base.group_system` never authenticates via REST, ADR-029) to a new domain, not a new ADR.
4. **REST exposure is read-only** — `GET` (list + detail) endpoints, gated by the same RBAC role tuple used for the tenant-scoped sibling resource (see "Role-Set Reuse Across Sibling Controllers" below), never by `company_id` filtering (there is none).

**Rationale**: Some domain data is a platform-curated reference set, not tenant-owned data — a shared template library, a rate table, a taxonomy. Modeling it with a `company_id` and record rules would be actively wrong (there is no owning tenant) and would tempt a future author into writing a rule that always evaluates true, which is a code smell for "this model shouldn't have record rules at all." Making the admin-only write path structural (no REST route exists, not just role-gated) also means it can never be reintroduced by mistake in a future PR.

**Reference**: `thedevkitchen.cms.template.generic` in `thedevkitchen_cms` — `18.0/extra-addons/thedevkitchen_cms/models/cms_template_generic.py`, `models/cms_template_generic_content.py`.

### Curated-Copy-Into-Tenant Pattern (Feature 028)
For an action that lets a tenant "adopt" a platform-level catalog record (see above) into their own tenant-scoped data:
1. **Materialize an independent snapshot, never a live reference** — the copy is a normal `create()` into the tenant-scoped model, populated from the platform entity's current fields at the moment of copy. No FK-based live link, no lazy-loading from the source at read time.
2. **Traceability field, not a sync mechanism** — add a `source_*_id` Many2one on the tenant-scoped model pointing back to the platform entity, `ondelete="set null"` (so deleting/deactivating the source never breaks or cascades into existing copies) and `readonly=True`. This field exists purely for observability/audit ("where did this come from"), never to drive behavior.
3. **No ongoing synchronization, ever** — changes to the platform source after the copy is made MUST NOT propagate to already-created copies. If future requirements need "push updates to adopters," that is a different, explicitly-designed feature (e.g. a versioning/notification system), not an extension of this pattern.
4. **`company_id` (or any tenant discriminator) is always session-derived** — never accepted from the request payload, per the existing ADR-008 principle; the copy action's create-vals builder should take the resolved `company_id` as an explicit typed parameter rather than a raw payload dict, so the tenant discriminator cannot leak in even by future accident (see the `_build_copy_create_vals(generic, name, company_id)` signature — it has no `data` parameter at all).
5. **Name-conflict handling wraps the create in a savepoint** — checking uniqueness then creating is not atomic; wrap the check-then-create in `with request.env.cr.savepoint():` so a race (two concurrent copies producing the same candidate name) rolls back cleanly instead of leaving a partially-created tenant row from a failed multi-step write.

**Rationale**: This is the tenant-facing half of the "Platform-Level Non-Tenant Catalog Entity" pattern — it's how tenant data gets seeded FROM a shared catalog without ever coupling the tenant's ongoing data lifecycle to the catalog's. Treating the copy as a permanent, independent snapshot (not a reference) keeps the mental model simple: once copied, it's yours, and nothing outside your company can ever change it again.

**Reference**: `POST /api/v1/cms/templates/generic/{id}/copy` in `18.0/extra-addons/thedevkitchen_cms/controllers/cms_template_generic_controller.py`, which sets `source_generic_template_id` on the new `thedevkitchen.cms.template` row (field added on that model, `models/cms_template.py`).

### Role-Set Reuse Across Sibling Controllers (Feature 028)
When a new controller enforces the exact same RBAC role tuple as an existing, closely-related sibling controller (e.g. a platform-level catalog's read/copy actions using the same role gate as the tenant-scoped resource it feeds into):
1. **The role tuple MUST be a single shared constant**, defined once in the original/sibling controller (e.g. `TEMPLATE_MANAGEMENT_ROLES = ("owner", "director", "manager")`), and imported — never independently hardcoded — by every other controller that needs the identical authorization boundary.
2. **A guard unit test comparing the two constants for equality is not sufficient** if both sides are separately hardcoded literals — that test can never detect real drift (if the sibling's tuple changes, the guard's own hardcoded copy doesn't). The guard test MUST import and compare against the single shared constant, not redeclare it.
3. **This was enforced as a fix, not a design-time decision** — Feature 028's final whole-branch review caught a case where the new controller had *independently* hardcoded the tuple a third time, with a comment falsely claiming it was "reused" from the sibling. The fix hoisted the constant into the sibling controller and had the new controller import + alias it (`GENERIC_TEMPLATE_MANAGEMENT_ROLES = TEMPLATE_MANAGEMENT_ROLES`), and rewrote the test to import the real constant. Treat this as the standard to apply from the start on any future sibling controller, not just as a retrospective fix.

**Rationale**: Comments claiming "reused, never redigitized" are not enforcement — only an actual shared import is. Two independently-typed identical tuples will inevitably drift apart the first time one file is edited without the other in mind, silently reopening or narrowing an authorization boundary. A self-referential test that only checks "does my local copy match your local copy" gives false confidence; it must anchor to the one real source of truth.

**Reference**: `TEMPLATE_MANAGEMENT_ROLES` in `18.0/extra-addons/thedevkitchen_cms/controllers/cms_template_controller.py`, imported as `GENERIC_TEMPLATE_MANAGEMENT_ROLES` in `controllers/cms_template_generic_controller.py`.

## Quality & Testing Standards

### Test Pyramid (ADR-002, ADR-003)
```
     E2E (56 Cypress tests)
    /____\
   /      \  Integration (195+ HTTP tests)
  /________\
 /          \ Unit (190+ tests)
```

### Reference Implementations
**Feature 007 - Owner & Company Management** (Constitutional Compliance Template):
- **Security**: Dual auth (`@require_jwt` + `@require_session`), multi-tenancy enforced
- **API Design**: 9 REST endpoints with HATEOAS links
- **Testing**: Integration tests (test_feature007_oauth2.sh), Cypress UI tests (2 files)
- **Documentation**: Postman collection with OAuth flow and test scripts
- **Location**: `18.0/extra-addons/quicksol_estate/controllers/owner_api.py`
- **Postman**: `docs/postman/feature007_owner_company_v1.0_postman_collection.json`

**Feature 009 - User Onboarding & Password Management** (Security Patterns Template):
- **Security**: Triple auth for invite, anti-enumeration on forgot-password, SHA-256 token hashing
- **API Design**: 5 REST endpoints (1 authenticated invite, 3 public password, 1 resend)
- **Token Lifecycle**: UUID v4 → SHA-256, state machine (pending/used/expired/invalidated), TTL configuration
- **Authorization Matrix**: Owner→all 9 profiles, Manager→5 operational, Agent→owner+portal
- **Portal Pattern**: Atomic res.users + real.estate.tenant via partner_id linkage
- **Session Management**: Invalidate all sessions after password reset
- **Email Integration**: mail.template with context variables (Portuguese pt_BR)
- **Configuration**: Singleton model with validation constraints (1-720h TTL range)
- **Rate Limiting**: Redis placeholder pattern (fail-open in dev, TODO for prod)
- **Testing**: 90+ unit tests (4 files), E2E integration tests (shell scripts)
- **Location**: `18.0/extra-addons/thedevkitchen_user_onboarding/`

**Feature 013 - Property Proposals Management** (FSM + Queue + Pessimistic Lock Template):
- **Data Model**: `real.estate.proposal` model with 8-state FSM (draft → queued → sent → negotiation → {accepted, rejected, expired, cancelled})
- **Concurrency**: Pessimistic locking (`SELECT FOR UPDATE NOWAIT`) + partial unique index `real_estate_proposal_one_active_per_property` (ADR-027)
- **FIFO Queue**: Auto-promotion of next queued proposal when active terminates non-accepted; `_promote_next_queued()` with queue_position recalculation
- **Counter-Proposals**: Linked chain via `parent_proposal_id` preserving full negotiation history; parent moves to `negotiation` state
- **Lead Integration**: Auto-create/link `real.estate.lead` on first proposal for client with source="proposal" (de-duplication by document)
- **Async Notifications**: Celery task `proposal.send_email` with 3 retries; failure logged to activity timeline (Outbox pattern)
- **API**: 12 REST endpoints under `/api/v1/proposals/` (all authenticated with triple decorators @require_jwt + @require_session + @require_company)
- **Security**: Triple auth on all endpoints, RBAC matrix (Owner/Manager: full CRUD; Agent: own proposals; Receptionist: read-only)
- **OTel**: `@trace_http_request` on all controller methods; composite DB indexes for performance
- **Testing**: 9 TransactionCase test files (47 test methods), 8 E2E bash scripts
- **Postman**: `docs/postman/feature013_property_proposals_v1.0_postman_collection.json`
- **OpenAPI**: `docs/openapi/proposals.yaml`
- **Location**: `18.0/extra-addons/quicksol_estate/models/proposal.py`, `controllers/proposal_controller.py`
- **ADRs**: ADR-027 (pessimistic locking), ADR-011 (security), ADR-016 (Postman), ADR-017 (performance)

**Feature 015 - Service Pipeline (Atendimentos)** [SPEC STAGE — Pipeline State Machine + Aggregation Template]:
- **Domain Boundary**: New entity `real.estate.service` distinct from `real.estate.lead` (one client may originate multiple services across operation types/agents)
- **Pipeline**: 7-stage state machine (no_service → in_service → visit → proposal → formalization → won/lost) with linear-with-audited-rollback flow; mail.thread mixin records every transition
- **Stage Gates**: @api.constrains validators — `proposal` requires `property_ids`; `formalization` requires approved proposal (013); `lost` requires `lost_reason`
- **System Tag**: `closed` tag (is_system=True) locks all pipeline movement
- **Conditional Uniqueness**: PostgreSQL EXCLUDE constraint — one active service per (client, operation_type, agent), historical duplicates allowed
- **Aggregation Endpoint**: `GET /api/v1/services/summary` returns per-stage counters for kanban (target < 100ms, optional Redis cache TTL 30s)
- **API**: 9 REST endpoints under `/api/v1/services/` and `/api/v1/service-tags`, `/api/v1/service-sources` (all authenticated with triple decorators)
- **RBAC Matrix**: Owner/Manager full; Agent/Prospector own only; Reception read-all + create
- **Auxiliary Entities**: `service.tag` (per company, with system flag), `service.source` (per company), `partner.phone` (multi-phone for clients), `service.settings` (singleton per company — pendency threshold 1-30 days)
- **Multi-Tenancy**: company_id on every entity + record rules per profile
- **Soft Delete**: ADR-015 active flag; archived services preserved for audit
- **Spec**: `specs/015-service-pipeline-atendimentos/spec.md` + `spec-idea.md` (technical detail)
- **ADRs Referenced**: 001, 003, 004, 005, 007, 008, 009, 011, 015, 016, 017, 018, 019, 022
- **Status**: Specification approved (2026-05-03); plan/implementation pending

**Feature 017 - Property Attachments Upload API** (Binary Upload + Magic Bytes + FR6.9 Error Envelope Template):
- **Storage**: `ir.attachment` as sole storage entity — `res_model='real.estate.property'`, `res_id=property_id`, `description='image'|'document'` as type discriminator; `company_id` field for multi-tenancy
- **MIME Validation**: `python-magic` (libmagic) magic bytes detection; separate whitelists per type: images (JPEG, PNG, WEBP, HEIC/HEIF), documents (PDF, DOCX, XLSX); global whitelist = union of both
- **Quantity Limits**: Hardcoded constants `MAX_IMAGES_PER_PROPERTY = 50`, `MAX_DOCUMENTS_PER_PROPERTY = 20` (NOT `ir.config_parameter` — avoids unhandled ValueError on missing params)
- **File Size Limit**: `ir.config_parameter` key `web.max_file_upload_size`, default 128MB (134,217,728 bytes) — shared system param, not module-specific
- **FR6.9 Error Envelope**: `{"error": "<snake_case>", "detail": "<string>", ...extras}` — ALWAYS `detail` NOT `message`; extra fields per error code (e.g., `received`, `max_size_bytes`, `received_size`, `attachment_type`, `limit`, `current`)
- **`_att_error()` Helper**: Module-level helper builds FR6.9 envelope via `request.make_json_response()` directly; bypasses shared `error_response()` util (which uses `message` key)
- **Download**: Binary serve via Werkzeug `Response` with `Content-Security-Policy: default-src 'none'` + `X-Content-Type-Options: nosniff` + `Content-Disposition: attachment`; URL NEVER contains `/web/content/`; always `/api/v1/properties/{id}/attachments/{aid}/download`
- **Filename Sanitization**: `werkzeug.utils.secure_filename()` with fallback to `'untitled'` when result is empty
- **Delete**: Hard-delete (`ir.attachment.unlink()`) — exception to ADR-015 soft-delete rule (binary blobs must be physically removed)
- **RBAC**: Owner/Manager: upload + list + download + delete; Agent: list + download only (upload=403, delete=403)
- **Company Domain**: `[('company_id', 'in', re_companies.ids)]` from `thedevkitchen_apigateway/middleware.py`
- **API**: 4 REST endpoints under `/api/v1/properties/{id}/attachments` (all authenticated with triple decorators `@require_jwt + @require_session + @require_company`)
- **Testing**: 65 unit tests (mock-only, no Docker), 19 API integration tests (TransactionCase + HttpCase), 6 E2E bash scripts
- **Location**: `18.0/extra-addons/quicksol_estate/controllers/property_attachments_controller.py`
- **Postman**: folder "23. Property Attachments (Feature 017)" in `docs/postman/quicksol_api_v1.28_postman_collection.json`

**Feature 022 — Admin UI Cross-Company Access** (SaaS Admin Channel Separation Template):
- **Problem**: Standard multi-tenancy record rules that correctly isolate business users also block `base.group_system` (System Admin) from accessing all tenant data in the Odoo Web UI
- **Solution**: Complementary `[(1,'=',1)]` record rules assigned to `base.group_system` — one per blocked model — override company-filtered rules via Odoo's OR-union rule evaluation
- **Models Covered**: `real.estate.property`, `real.estate.agent`, `real.estate.lease`, `real.estate.sale`, `real.estate.proposal`, `real.estate.service`, CMS page/media/settings, `thedevkitchen.estate.goal`, credit check, commission rule/transaction, lease renewal history, `thedevkitchen.estate.profile`, password token
- **API Block**: Login controller rejects `base.group_system` with HTTP 401 + audit log entry before issuing any session token (credentials valid, channel forbidden; anti-enumeration)
- **Menu Visibility**: `base.group_system` added to previously role-restricted menus (e.g., `menu_real_estate_lead`)
- **noupdate Handling**: New admin override rules placed in `noupdate="0"` blocks even when the target file uses `noupdate="1"`, ensuring apply-on-upgrade without disrupting existing rules
- **No new models**: Feature is purely security/record-rule configuration + one controller guard
- **Testing**: E2E (Cypress) for cross-company visibility in Odoo UI; integration test for API login block (HTTP 401)
- **Location**: Security XML files across `quicksol_estate/`, `thedevkitchen_cms/`, `thedevkitchen_estate_goals/`, `thedevkitchen_estate_credit_check/`, `thedevkitchen_user_onboarding/`; controller guard in `thedevkitchen_apigateway/controllers/user_auth_controller.py`
- **ADRs**: ADR-008 (multi-tenancy), ADR-009 (headless auth), ADR-011 (security decorators), ADR-019 (RBAC profiles)
- **Spec**: `specs/022-admin-ui-cross-company/spec.md`
- **ADRs**: ADR-008 (multi-tenancy), ADR-009 (headless auth), ADR-011 (security decorators), ADR-019 (RBAC profiles)
- **Spec**: `specs/022-admin-ui-cross-company/spec.md`

**Feature 023 — Redis Cache para Sessão e JWT** (Redis Auth Cache + Graceful Degradation Template):
- **Problem**: Every authenticated request issued 2 SELECTs + 1 UPDATE on PostgreSQL before any business logic (`require_jwt` + `require_session`). Redis was configured but unused for lookup.
- **Solution**: `RedisClient` singleton with `ConnectionPool`; JWT cached by `jwt:{sha256(token)[:32]}`; session cached by `session:{session_id}` including `security_token`; Odoo 18 ORM field cache pre-injected via `env.cache.set()` for zero-SELECT downstream access.
- **No contract break**: `request.jwt_token`, `request.jwt_application`, `request.api_session` remain ORM records (`browse(id)` lazy records with field cache pre-populated).
- **Graceful fallback**: All `RedisClient` methods catch every exception and return `None`/`False`/`0` — the application degrades to full PostgreSQL without any error.
- **Invalidation hooks**: `OAuthToken.action_revoke()` override deletes JWT cache key; `APISession.write()` override deletes session cache key when `is_active` or `company_id` changes — covers logout, switch-company, login (old sessions), cron cleanup, user deactivation.
- **Deployment order principle**: Invalidation hooks deployed BEFORE cache population is activated (eliminates stale-data window at deploy time).
- **Trade-off**: `last_activity` updated only on cache MISS (~every 5 min), not per-request — documented explicitly as metric field, not security control.
- **Performance stubs resolved**: `performance_service.py` methods `_get_cached_performance`, `_cache_performance`, `invalidate_cache` connected to `RedisClient` (were literal `return None` / `pass` stubs).
- **Testing**: 12 unit tests (mock-only, T01–T12) + 6 E2E bash scenarios (`test_redis_cache.sh`) with `redis-cli` assertions.
- **Files modified**: `middleware.py`, `services/session_validator.py`, `models/oauth_token.py`, `models/api_session.py`, `quicksol_estate/services/performance_service.py`
- **File new**: `thedevkitchen_apigateway/services/redis_client.py`
- **Spec**: `specs/023-redis-session-cache/spec.md`
- **Plan**: `specs/023-redis-session-cache/plan.md`

**Feature 027 — Agent/Profile Endpoint Unification** (Owner-Only Authorization Hardening + Batched Sub-Object Embedding Template):
- **Problem**: `real.estate.agent` list/get/update/deactivate/reactivate lived on a separate `/api/v1/agents` controller with its own (inconsistent, in places incorrect) authorization, duplicating the already-unified `thedevkitchen.estate.profile` read/write path established in Feature 026. `DELETE /api/v1/profiles/{id}` (deactivate) was also unrestricted for every `profile_type` except `agent`.
- **Solution**: Extended `profile_api.py` to own list/get/update/deactivate/reactivate for every `profile_type`, including `agent` (via a batched `agent` sub-object embedded in `_serialize_profile`); removed the 5 now-redundant `/api/v1/agents` CRUD routes outright (no deprecation window, same precedent as Feature 026).
- **N+1 Fix**: `list_profiles` now does ONE batched `real.estate.agent.search([("profile_id","in",[...])])` per page instead of one `search()` per row, building an `agent_by_profile_id` dict passed into `_serialize_profile(profile, agent_by_profile_id=None)` — the `None` default keeps `get_profile`'s single-record path unchanged (a single extra query is fine when only one record is being serialized).
- **Authorization Hardening**: `DELETE /api/v1/profiles/{id}` and the new `POST /api/v1/profiles/{id}/reactivate` are owner/admin-only for EVERY `profile_type` — see "Explicit Group Check for Owner" and "Deliberate Authorization Hardening as a Cross-Cutting Fix" patterns above, both introduced by this feature.
- **Atomic Cascade with Deliberate Asymmetry**: `_deactivate_profile_cascade`/`_reactivate_profile_cascade` mirror each other (profile → agent-if-agent-type → res.users), except reactivate NEVER restores a `thedevkitchen.api.session` row invalidated by a prior deactivate — the user must authenticate again (extends Feature 023's proactive session-invalidation guarantee to the reactivate path, tested across all 6 `profile_type` values with linked users, not just `agent`).
- **Testability without HTTP mocking**: every extracted helper (`_user_can_deactivate_or_reactivate_profile`, `_deactivate_profile_cascade`, `_reactivate_profile_cascade`, `_resolve_profile_ids_by_agent_filters`) takes plain recordsets/params instead of `odoo.http.request`, enabling direct `TransactionCase` unit coverage without mocking Werkzeug internals — this project's standing testing convention.
- **API**: `POST /api/v1/profiles/{id}/reactivate` (new); `GET /api/v1/profiles` gains `creci_number`/`creci_state` filters; 5 legacy `/api/v1/agents` routes removed (list/get/update/deactivate/reactivate — assignments/properties/performance/commission-rules/ranking are untouched, they stay on `agent_api.py`).
- **Testing**: 20+ new `TransactionCase` tests across 7 files, 5 new E2E bash scripts (`integration_tests/test_us27_s*.sh`) covering the full authorization matrix, reactivate cascade, agent sub-object/filter parity, and legacy-route-removal verification.
- **Location**: `18.0/extra-addons/quicksol_estate/controllers/profile_api.py`
- **Spec**: `specs/027-agent-profile-endpoint-unification/spec-idea.md`
- **Plan**: `specs/027-agent-profile-endpoint-unification/plan-idea.md`
- **Flowcharts**: `specs/027-agent-profile-endpoint-unification/flowcharts.md`
- **ADRs Referenced**: ADR-008 (anti-enumeration), ADR-011 (security decorators), ADR-015 (soft delete), ADR-019 (RBAC profiles)

**Feature 028 — CMS Generic Templates (Platform Catalog)** (Non-Tenant Catalog + Curated-Copy Template):
- **Problem**: No mechanism existed for the platform to offer a curated, shared set of CMS page templates (landing/property/about) that every company could start from, without either duplicating editorial effort per-tenant or awkwardly forcing a "shared" `company_id` onto tenant-scoped data.
- **Solution**: New non-tenant model `thedevkitchen.cms.template.generic` (+ `.content`, 1:1) with no `company_id`, curated exclusively by `base.group_system` via the Odoo backend UI — no REST create/update/delete route exists for it at all (see "Platform-Level Non-Tenant Catalog Entity" pattern above). `owner`/`director`/`manager` of any company can `GET` (list/detail) the catalog and `POST .../copy` a generic template into their own company's existing `thedevkitchen.cms.template` (Feature 021), which gains a new `source_generic_template_id` traceability field (see "Curated-Copy-Into-Tenant Pattern" above).
- **Authorization**: The exact same role tuple as the sibling company-scoped Templates controller, hoisted into one shared constant during final review to prevent drift (see "Role-Set Reuse Across Sibling Controllers" above).
- **Data Integrity on Copy**: `company_id` is always `request.env.company.id`, never the request payload (ADR-008); the two-step write (new template row, then its content row) is wrapped in `with request.env.cr.savepoint():` so a mid-write failure never leaves an orphaned, content-less template — a Critical finding from the final whole-branch review, fixed before merge.
- **Name-Conflict Handling**: Incrementing `" (2)"`, `" (3)"`... suffix on a name collision within the target company, up to 100 attempts, then `409 generic_copy_conflict` — same duplication pattern already used for CMS page duplication.
- **API**: 3 REST endpoints — `GET /api/v1/cms/templates/generic`, `GET /api/v1/cms/templates/generic/{id}`, `POST /api/v1/cms/templates/generic/{id}/copy` — all triple-decorated (`@require_jwt` + `@require_session` + `@require_company`).
- **Testing**: 115 unit tests (module total, incl. new ones for this feature), 6 TransactionCase integration tests (first `tests/integration/` in `thedevkitchen_cms`, mirroring `quicksol_estate`'s existing unit/integration split), 15 E2E API scenarios (`integration_tests/test_us028_cms_generic_templates.sh`), 8 Cypress UI tests, all with captured evidence (screenshots, videos, response logs) organized under `cypress/screenshots/028-cms-generic-templates/`.
- **Documentation**: Swagger/OpenAPI (`data/api_endpoints.xml`, tag "CMS Generic Templates") and Postman (`docs/postman/quicksol_api_v1.45_postman_collection.json`, folder "Generic Templates (Feature 028)" under "25. CMS Domain") both updated and evidence-verified as part of the same completion pass as the tests — not deferred (see Runtime Guidance addendum below).
- **Location**: `18.0/extra-addons/thedevkitchen_cms/models/cms_template_generic.py`, `models/cms_template_generic_content.py`, `controllers/cms_template_generic_controller.py`
- **Spec**: `specs/028-cms-generic-templates/spec-idea.md`
- **Plan**: `specs/028-cms-generic-templates/plan-idea.md`
- **Flowcharts**: `specs/028-cms-generic-templates/flowcharts.md`
- **ADRs Referenced**: ADR-004 (naming), ADR-008 (multi-tenancy/session-derived company_id), ADR-011 (security decorators), ADR-015 (soft delete), ADR-019 (RBAC), ADR-029 (SaaS Admin channel separation)

Use Feature 007 for standard CRUD patterns with HATEOAS. Use Feature 009 for security-sensitive flows requiring token-based authentication, anti-enumeration, and session management. Use Feature 013 for FSM-driven domain entities with concurrent access control, FIFO queues, and async notifications. Use Feature 015 for kanban-style pipeline domains with stage gates, conditional uniqueness, system tags, and aggregation endpoints. Use Feature 017 for binary file upload/download patterns with magic bytes validation, per-type quantity limits, and FR6.9-compliant error envelopes. Use Feature 022 for SaaS Admin cross-company access patterns (record rule overrides, API login block, noupdate compatibility). Use Feature 023 for Redis cache patterns on auth hot paths (JWT lookup, session lookup, ORM field cache injection, write hook invalidation, graceful fallback). Use Feature 027 for owner-only authorization hardening applied broadly across profile_type with existing-matrix cross-checks, batched sub-object embedding to avoid N+1 in list serializers, and atomic multi-model cascades with a deliberate deactivate/reactivate asymmetry (session invalidation never reversed). Use Feature 028 for platform-level non-tenant catalog entities offering a curated-copy-into-tenant action, and for the shared-role-tuple-constant discipline across sibling controllers.

### Required Tests per Feature
- **Unit**: Services, helpers, serializers, decorators
- **Integration**: All CRUD endpoints (success + 401 + validation + 404 + permissions)
- **E2E**: At least one complete journey per major feature

### Test Creation - Prompts Obrigatórios
Para criação de testes, **DEVEM ser utilizados** os prompts e agents especializados:

| Recurso | Arquivo | Propósito |
|---------|---------|-----------|
| **Test Strategy Agent** | `.github/prompts/test-strategy.prompt.md` | Consultor que analisa e recomenda o tipo de teste correto (aplica "Regra de Ouro") |
| **Test Executor Agent** | `.github/prompts/test-executor.prompt.md` | Executor que cria código de teste automaticamente baseado nas recomendações |
| **SpecKit Tests Agent** | `.github/agents/speckit.tests.agent.md` | Gerador completo de testes baseado em cenários de aceitação (spec.md) |

**Fluxo Recomendado:**
```
1. Test Strategy Agent → Analisa código e recomenda tipo de teste
2. Test Executor Agent → Cria código baseado na recomendação
   OU
   SpecKit Tests Agent → Gera múltiplos testes a partir da spec.md
```

**Rationale**: Prompts especializados garantem consistência, aderência à ADR-003 e uso correto de credenciais do `.env`.

### Code Quality Gates
- Linting: `ruff` + `black` (automated via `./lint.sh`)
- Coverage: ≥80% (measured, enforced in CI)
- Documentation: OpenAPI schemas for all endpoints
- **API Documentation**: Postman collections (ADR-016) for all new features
- ADR compliance: Verified in code review

## Development Workflow (ADR-006)

### Git Flow
- **Main branches**: `main` (production), `develop` (staging)
- **Feature branches**: `feature/`, `bugfix/`, `hotfix/`
- **PR requirements**: Tests, documentation, ADR compliance, CODEOWNERS approval

### Module Structure (ADR-001, ADR-004)
```
{company}_{domain}/
├── controllers/    # API endpoints
├── models/         # Business logic (ORM)
├── services/       # Reusable business services
├── tests/          # Unit + Integration
│   ├── api/        # HTTP integration tests
│   └── utils/      # Unit tests
├── security/       # Access rules, record rules
└── data/           # Master data (XML)
```

### Naming Conventions (ADR-004)
- **Modules**: `{company}_{domain}` (e.g., `quicksol_estate`)
- **Models**: `{company}.{domain}.{entity}` (e.g., `thedevkitchen.estate.property`)
- **Controllers**: `{entity}_api.py` (e.g., `property_api.py`)
- **Tests**: `test_{entity}_{scope}.py` (e.g., `test_property_api.py`)

## Governance

### Amendment Process
1. Propose change via ADR (if architectural) or constitution amendment
2. Document rationale, impact, migration plan
3. Update constitution version (semantic versioning)
4. Propagate changes to templates and dependent docs
5. Require CODEOWNERS approval for constitution changes

### Versioning Policy
- **MAJOR**: Breaking governance changes (principle removal/redefinition)
- **MINOR**: New principle/section added, material expansion, or reference implementations documented
- **PATCH**: Clarifications, wording, typo fixes

### Compliance Review
- All PRs MUST verify compliance with active ADRs
- Constitution violations require explicit justification + approval
- AI agents MUST consult `.specify/memory/constitution.md` before making architectural decisions

### Runtime Guidance
- AI agents use `.github/copilot-instructions.md` for operational rules
- Constitution provides strategic direction; copilot-instructions provides tactical rules
- Conflicts resolved in favor of constitution (strategic supersedes tactical)

### API Documentation Is Not Deferred (Feature 028)
Swagger/OpenAPI (`data/api_endpoints.xml` → `thedevkitchen.api.endpoint` → `/api/docs`, `/api/v1/openapi.json`) and the Postman collection (ADR-016) MUST be updated, and that update verified with evidence (a screenshot of `/api/docs` or the generated OpenAPI JSON showing the new endpoints; a diff of the Postman collection), in the same completion pass as the feature's tests — not deferred to a later "documentation" phase, and not satisfied by "endpoints implemented and tested" alone.

This is distinct from constitution/knowledge-base updates (see `CLAUDE.md`'s spec-kit section and the project's own workflow conventions), which SHOULD wait until a feature's implementation is validated before propagating speculative patterns into governance docs — API documentation carries no such "wait and see" rationale, since it is a mechanical description of code that has already passed review. Conflating the two and deferring both together was an actual regression caught during Feature 028: Swagger was left stale after the feature was declared complete, requiring a follow-up correction pass.

**Version**: 1.11.0 | **Ratified**: 2026-01-03 | **Last Amended**: 2026-09-07
