# Security

> Sources: `docs/adr/ADR-008` (API Security/Multi-Tenancy), `ADR-009` (Headless Auth), `ADR-011` (Controller Security), `ADR-017` (Session Hijacking/JWT Fingerprint), `ADR-018` (Input Validation), `ADR-019` (RBAC), `ADR-029` (SaaS Admin Channel Separation), `thedevkitchen_apigateway/middleware.py`, `quicksol_estate/security/groups.xml`, `TECHNICAL_DEBIT.md`.

## Authentication Mechanism

**Dual authentication model** (ADR-011), combining stateless and stateful mechanisms depending on the channel:

1. **OAuth 2.0 + JWT (Bearer tokens)** for application/API-level authentication — `thedevkitchen_apigateway` module, `authlib`-based, RFC 6749 (`client_credentials` grant primarily used per ADR-003 testing guidance), RFC 7009 (revocation), RFC 7662 (introspection), RFC 9068 (JWT profile). Endpoints: `POST /api/v1/auth/token`, `/refresh`, `/revoke`.
2. **HTTP session** (`session_id`) layered on top for user-context continuity, validated by `@require_session` after `@require_jwt` has validated the bearer token.
3. **Company context** (`@require_company`) as a third gate, ensuring the authenticated user has a resolvable default tenant before any handler logic runs.
4. Nearly every custom REST controller in the codebase applies this **triple-decorator chain**: `@require_jwt` → `@require_session` → `@require_company` (confirmed by direct source inspection across all controller files — see [api-surface.md](api-surface.md) for the per-endpoint auth column).
5. **Odoo's native web UI** login remains a separate channel (cookie/session based), used only for back-office administration — explicitly **not** available to business/tenant users via the headless API's `/api/v1/users/login` endpoint, which **blocks** `base.group_system` (System Admin) logins (ADR-029) to prevent the admin channel from bypassing multi-tenancy controls through the API.

## Admin / Privileged Access Paths

- `base.group_system` (Odoo "System Administrator", uid=2 by convention) is the SaaS-level super-user role, with cross-company visibility granted via complementary `ir.rule` records (`domain_force=[(1,'=',1)]`) added specifically for this group (ADR-029) — access happens **only** through the Odoo web UI, never through the headless REST API.
- Within a tenant, the highest business-level privilege is the **Owner** profile (full CRUD across all tenant-scoped models), followed by Director, Manager, and 6 other operational profiles (Agent, Prospector, Receptionist, Financial, Legal, Portal User) — 11 `res.groups` records defined in `quicksol_estate/security/groups.xml`, mapped 1:1 (mostly) to the RBAC profile types described in [multi-tenancy.md](multi-tenancy.md).
- **Applied instance of ADR-029 to a new, non-tenant domain (Feature 028):** `thedevkitchen.cms.template.generic` (platform-level CMS template catalog, `thedevkitchen_cms`) has no REST create/update/delete endpoint at all — it is admin-curated exclusively via Odoo UI, exactly mirroring the "admin never authenticates via the headless API" principle. Its 3 read/copy REST endpoints instead reuse the same RBAC tuple as the sibling company-scoped controller via a single shared, imported constant (`GENERIC_TEMPLATE_MANAGEMENT_ROLES = TEMPLATE_MANAGEMENT_ROLES`, `cms_template_generic_controller.py` importing from `cms_template_controller.py`) rather than an independently hardcoded literal — a pattern worth following whenever a new controller must enforce identical authorization to an existing sibling, to prevent authorization drift.

## 2FA / MFA

- **Not implemented in application code.** `docs/guide/03-environments.md` states MFA is "mandatory" for production **administrator** access, but this appears to refer to an operational/infrastructure-level control (e.g., VPN/Dokploy/Grafana login), not an Odoo or REST-API-level MFA feature — **no MFA/TOTP model, field, or verification endpoint was found in any custom module.** Recorded as **Not identified** at the application layer.

## Session Hijacking Prevention (ADR-017)

- **Status: Proposed** (not confirmed as fully implemented in code at the time of this review — the ADR describes binding each session to a fingerprint of `user_id + IP + User-Agent + Accept-Language`, configurable via a `thedevkitchen.security.settings` model). Motivated by a documented critical-risk scenario: a stolen `session_id` alone (without the fingerprint check) would let an attacker impersonate another user, breaking multi-tenancy isolation and violating LGPD Art. 48 (right to confidentiality). Recommend verifying current implementation status directly against `thedevkitchen_apigateway` code if this control is safety-critical for the next release.

## Input Validation (ADR-018)

Two-layer validation for all REST write endpoints:
1. **Schema validation** against the OpenAPI 3.0 contract (mass-assignment protection, type checking, required-field checking) — implemented via `schema.py` / `SchemaValidator` helpers referenced across `quicksol_estate/controllers`.
2. **Business-rule validation** at the ORM level (`@api.constrains`) — CPF/CNPJ/CRECI format validation (Brazilian documents, via `validate_docbr` and a custom `CreciValidator`), email format, etc.

## CSP / Security Headers

**Not found.** No Content-Security-Policy, `X-Frame-Options`, `Strict-Transport-Security`, or other security-header middleware was identified in any controller or in `odoo.conf`. Odoo's default header behavior applies; no custom hardening layer was found in this repo. Recorded as **Not identified — no explicit CSP/security-header configuration found in code.**

## CAPTCHA / Bot Protection

**Not found.** No CAPTCHA (reCAPTCHA, hCaptcha, Turnstile) integration was identified on any public-facing endpoint (login, forgot-password, public CMS pages).

## CORS

- Several list endpoints explicitly set `cors='*'`. `GET /api/v1/leads` is fully authenticated (`@require_jwt` + `@require_session` + `@require_company`) and, as of Feature 024, enforces explicit company- and agent-based domain filtering. It was previously misdocumented here as public — the auth decorators were always present; the bug was a missing `company_id` domain filter inside the handler. `/api/v1/sales` and `/api/v1/tags` are unaffected by this correction and remain open questions, along with health/OTLP proxy endpoints and user-auth endpoints. `TECHNICAL_DEBIT.md` explicitly flags CORS configuration as a known issue: CORS should be configurable dynamically via the back-office "Technical" menu rather than hardcoded `cors='*'` on every endpoint — **documented, unresolved technical debt**, not a new finding.

## Multi-Tenancy Security

Covered in depth in [multi-tenancy.md](multi-tenancy.md) (ADR-008's 5 mandatory principles: no `.sudo()` on transactional queries, company_id validation on create, immutable `company_ids` on update, mandatory audit logging, auto-assignment of default company).

## Applied Security Patches / Advisories

No CVE-tracking file or dependency-vulnerability-scan report (e.g., `SECURITY.md`, Dependabot alerts export, `pip-audit`/`safety` report) was found in the repository. Security-relevant changes are instead tracked as ADRs with `Security` classification implicit in their titles:

| ADR | Classification | Summary |
|---|---|---|
| ADR-008 | Security | API security in multi-tenancy (IDOR/mass-assignment prevention) |
| ADR-009 | Security | Headless authentication with user context |
| ADR-011 | Security | Dual authentication (OAuth2 + session) for controllers |
| ADR-017 | Security | Session hijacking prevention via JWT fingerprint (Proposed) |
| ADR-018 | Security | Input/schema validation for REST APIs |
| ADR-019 | Security / Functionality | RBAC profiles in multi-tenant environment |
| ADR-027 | Bug Fix / Functionality | Pessimistic locking to prevent race-condition-induced invariant violations |
| ADR-029 | Security | SaaS admin channel separation (blocks admin login via headless API) |

Recent git history (`5181280 Merge pull request #25 from luanalves/023-redis-session-cache`, `564a94f fix(023): address second round of PR #25 review comments`) indicates active, reviewed hardening of the Redis-backed session/JWT cache layer.

## Rate Limiting / API Access Logs

- **Rate limiting:** confirmed only for the forgot-password flow (`thedevkitchen_user_onboarding`, "3 requests/hour" via Redis, per the module's manifest description). No general-purpose API rate limiting (e.g., per-IP or per-token throttling on all `/api/v1/*` routes) was found within this Odoo codebase — production-level rate limiting is asserted in `docs/guide/03-environments.md` ("Rate limiting configurado") but likely enforced at the Kong API Gateway layer (external repo), not in this codebase.
- **Access logs:** `thedevkitchen.api.access.log` model (in `thedevkitchen_apigateway`, view: `views/api_access_log_views.xml`) records API access attempts, satisfying ADR-008's audit-logging requirement.

## Compliance Considerations

- **LGPD (Brazilian data protection law)** is referenced explicitly multiple times in the ADRs (ADR-008 risk framing, ADR-017 Art. 48 citation, `TECHNICAL_DEBIT.md` item on auditing security-group changes) and in code comments (`event_bus.py`, `res_users.py`: `user.groups_changed` events emitted specifically for "LGPD compliance / audit"). No dedicated LGPD/data-subject-rights endpoints (e.g., data export, right-to-erasure automation) were found beyond the general soft-delete (`active=False`) pattern (ADR-015) and the `auditlog` OCA module.
- No PCI-DSS-relevant code was found (no payment card handling identified anywhere in the codebase, consistent with the "no payment gateway" finding in [integrations.md](integrations.md)).

## Discrepancies / Findings

- `TECHNICAL_DEBIT.md` flags: "arquivos que tem o skip como tracking_disable, podem ser problema de segurança, validar se é necessário manter desta forma?" — an open question about disabled audit tracking on some models, not yet resolved.
- ADR-017 (session fingerprinting) status is "Proposed," not "Accepted" — treat as a planned control, not a verified guarantee, until confirmed implemented.
- Hardcoded `cors='*'` across many endpoints is a known, still-open item per `TECHNICAL_DEBIT.md`.
