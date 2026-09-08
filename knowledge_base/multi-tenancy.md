# Multi-Tenancy

> Sources: `docs/architecture/DATABASE_ARCHITECTURE_USERS.md`, `docs/adr/ADR-008` (API Security in Multi-Tenancy), `ADR-019` (RBAC + Multi-Tenancy), `ADR-029` (SaaS Admin Channel Separation), `18.0/extra-addons/quicksol_estate/models/company.py`, `res_users.py`, `TECHNICAL_DEBIT.md`.

## Model

**Applicable — multi-tenant SaaS application.** The system serves multiple independent real estate agencies ("imobiliárias") on a **single shared Odoo database** (config-driven / row-level multi-tenancy, not database-per-tenant or schema-per-tenant). Tenancy is modeled through Odoo's native `res.company` entity, extended with Brazilian-market fields (CNPJ, CRECI, legal name), plus a combination of `Many2one`/`Many2many` relationships and `ir.rule` record rules that scope every query to the companies the requesting user belongs to.

## Tenant Hierarchy

```
Tenant boundary: res.company ("imobiliária" — real estate agency)
  ├── company_id / company_ids relationships (per-entity, see table below)
  │
  ├── Users (res.users) — linked to 1..N companies via company_ids (Many2many);
  │     one company acts as the user's "current/default" company (company_id)
  │
  ├── Agents (real.estate.agent) — company_id (Many2one, single company per agent;
  │     migrated away from the legacy Many2many `company_ids`, kept for backward compatibility)
  │
  ├── Property Owners (real.estate.property.owner) — NOT linked directly to a company;
  │     isolation is indirect, via the owned property's company_ids
  │
  ├── Tenants (real.estate.tenant) — company_ids (Many2many; a tenant CAN be shared
  │     across multiple agencies, e.g. renting from two different agencies)
  │
  ├── Properties (real.estate.property) — company_ids (Many2many)
  ├── Leases (real.estate.lease) — company_ids (Many2many)
  ├── Sales (real.estate.sale) — company_ids (Many2many)
  └── CMS pages/media/templates (thedevkitchen_cms) — company_id (Many2one),
        with a public `company_slug` route for headless SSR consumption
```

There is no further "environment/locale" sub-level within a tenant (e.g. no per-tenant multi-language site variants beyond Odoo's standard i18n) found in the code; each `res.company` record is a single, flat tenant.

## Isolation Mechanisms (defense in depth)

1. **User → Company membership** (`res.users.company_ids`, extended by `quicksol_estate/models/res_users.py`): non-admin users only see data for companies in this list; `base.group_system` (System Admin) bypasses this by design.
2. **Record Rules** (`ir.rule`) on every tenant-scoped model, e.g. `[('company_id', 'in', user.company_ids.ids)]` — enforced automatically by the Odoo ORM regardless of which controller/service issues the query, **as long as `.sudo()` is not used**.
3. **API-layer enforcement** (ADR-008, "5 mandatory security principles" for every transactional REST endpoint):
   - Never use `.sudo()` on transactional data queries; always filter by company in the domain before executing.
   - Validate that the authenticated user has access to **all** `company_ids` supplied on `POST`/create before creating a record; reject unauthorized company assignment (mass-assignment protection).
   - `company_ids` is **immutable** via `PUT`/`PATCH` on the API — company transfers must go through the admin interface only.
   - Mandatory audit logging of every access attempt (success and failure): user, resource, operation, timestamp, IP, result.
   - Auto-assign the user's default company when `company_ids` is omitted on create.
4. **`@require_company` decorator** — part of the standard triple-decorator auth chain (`@require_jwt` → `@require_session` → `@require_company`) applied to nearly all REST controllers; ensures the request's user has a resolvable default company before any business logic executes.
5. **Cross-company System Admin access (ADR-029):** `base.group_system` gets complementary `ir.rule` records with `domain_force=[(1,'=',1)]` so the SaaS-level admin can see records across all tenant companies in the **Odoo web UI**. Critically, the headless REST login endpoint (`POST /api/v1/users/login`) explicitly **blocks** System Admin authentication — the admin channel (Odoo web UI) and the business/tenant channel (headless API) are kept separate by design, to prevent an admin session from bypassing multi-tenancy controls via the API.
6. **Platform-level, non-tenant entities are an explicit exception to `ir.rule` isolation, not a gap in it** (introduced by Feature 028, `thedevkitchen.cms.template.generic`): a model with no `company_id` field has nothing to isolate, so it correctly carries **no** `ir.rule` record; access is controlled instead via `ir.model.access.csv` (full CRUD to `base.group_system` only) plus an explicit role check in the controller (`owner`/`director`/`manager`). Company isolation is only re-introduced at the moment of the "copy" action, which always derives `company_id` from the authenticated session (ADR-008), never from the request payload.

## RBAC Profiles (per-tenant roles, ADR-019)

9 profile types apply within the scope of a company: **Owner, Director, Manager, Agent, Prospector, Receptionist, Financial, Legal, Portal User** (+ `base.group_system` as the cross-tenant SaaS admin role, outside the business hierarchy). A user can hold **different profiles in different companies** simultaneously, tracked in `thedevkitchen_estate_profile (partner_id, company_id, profile_type_id)`.

## Discrepancies / Known Gaps (from `TECHNICAL_DEBIT.md`)

- **Authorization is global, not per-company.** Action-level authorization currently relies on `user.has_group('quicksol_estate.group_real_estate_manager')`, which is a **global** Odoo security group membership (`res_groups_users_rel` has no `company_id` column) — i.e., if a user is in the Manager group, they are a manager in **every** company they belong to, even though the `thedevkitchen_estate_profile` table already stores a proper per-company profile mapping. This means a user invited as "agent" in Company A could act as "agent" in Company B too, if granted access to Company B, without an actual profile record there. Documented fix path: introduce a `get_user_role_for_company(user, company_id)` helper backed by `thedevkitchen_estate_profile` and replace `has_group()` calls in the authorization matrices (`PROFILE_CREATION_MATRIX` in `profile_api.py`, `invite_controller.py`).
- **Legacy `Many2many company_ids` relationship tables still exist** for agents (`thedevkitchen_company_agent_rel`) for backward compatibility, even though agents were migrated to a single `company_id` (Many2one) architecture — a partial migration state.
- **Property Owners have no direct company link** — isolation is only indirect (via the properties they own), which the architecture doc itself flags as a "point of attention."
