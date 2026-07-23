# Postman Collection - Quicksol Real Estate API

## Overview

Complete Postman collection for Quicksol Real Estate Management System API.

**Version:** 1.39.0
**Last Updated:** 2026-07-23
**Spec Coverage:** Complete API (55+ endpoints)

## Available Collections

### 1. Complete API Collection (v1.39) ⭐ RECOMMENDED
**File:** `quicksol_api_v1.39_postman_collection.json`
**Coverage:** All 55+ endpoints - Complete API coverage
**ADR Compliance:** ADR-016 (complete)
**Note:** `Invite User`'s `agent` object example corrected — it only contains fields exclusive to the agent record (`creci`, `bank_name`, `bank_account`, `pix_key`); identity fields (`name`/`cpf`/`email`/`phone`/`mobile`/`hire_date`) already come from the referenced profile and are no longer part of this object.

### 1. Complete API Collection (v1.38)
**File:** `quicksol_api_v1.38_postman_collection.json`
**Coverage:** All 55+ endpoints - Complete API coverage
**ADR Compliance:** ADR-016 (complete)
**Note:** `POST /api/v1/agents` (legacy `Create Agent` request) removed — physically removed from the API (Feature 026, User Story 3).

### 1. Complete API Collection (v1.35)
**File:** `quicksol_api_v1.35_postman_collection.json`
**Coverage:** All 55+ endpoints - Complete API coverage
**ADR Compliance:** ADR-016 (complete)
**Note:** Lead company/agent isolation now correctly enforced on List Leads, Export Leads to CSV, Get Lead Statistics, and all three Lead Activities endpoints (Feature 024)

### 1. Complete API Collection (v1.31) ⭐ RECOMMENDED
**File:** `quicksol_api_v1.31_postman_collection.json`
**Coverage:** All 55+ endpoints - Complete API coverage
**ADR Compliance:** ADR-016 (complete)
**Security:** Token format validation + cross-type abuse block + last-token-wins
**Includes:** Authentication, Users, Properties, Agents, Assignments (full CRUD), Commissions, Performance, Leads, Activities, Filters, Master Data, Profile Management, User Onboarding, property selectable options, property owner relationship payloads, property FGTS eligibility fields

### 2. Complete API Collection (v1.30)
**File:** `quicksol_api_v1.30_postman_collection.json`
**Coverage:** Property options, property owner relationship payloads
**Note:** Use v1.31 for latest property FGTS eligibility examples

### 3. Complete API Collection (v1.29)
**File:** `quicksol_api_v1.29_postman_collection.json`
**Coverage:** Property attachments response examples
**Note:** Use v1.31 for latest property options, `property_situation` enum updates, property `owner` relationship payloads, and FGTS fields

### 4. Complete API Collection (v1.19)
**File:** `quicksol_api_v1.19_postman_collection.json`  
**Coverage:** Unified profile flow (Feature 010) - no legacy invite flows  
**Note:** Use v1.20 for latest security fixes on password endpoints

### 5. Complete API Collection (v1.18)
**File:** `quicksol_api_v1.18_postman_collection.json`  
**Coverage:** Unified Profile Flow introduced  
**Note:** Use v1.20 for latest version

### 6. Complete API Collection (v1.16)
**File:** `quicksol_api_v1.16_postman_collection.json`  
**Coverage:** Previous version (9 profile types + legacy invite flows)  
**Note:** Use v1.20 for unified profile workflow

### 7. Complete API Collection (v1.7)
**File:** `quicksol_api_v1.7_postman_collection.json`  
**Coverage:** All 55+ endpoints - Complete API coverage  
**ADR Compliance:** ADR-016 (complete)  
**Includes:** Authentication, Users, Properties, Agents, Assignments (full CRUD), Commissions, Performance, Leads, Activities, Filters, Master Data

### 8. Lead-Focused Collection (v1.2)
**File:** `quicksol_api_v1.2_postman_collection.json`  
**Coverage:** Lead Management focused (Feature 006)  
**ADR Compliance:** ADR-016 (complete)

### 9. Legacy API Collection (v1.1)
**File:** `quicksol_api_v1.1_postman_collection.json`  
**Coverage:** Properties, Agents, Assignments, Commissions, RBAC profiles

### 10. Lead Management Collection (Standalone)
**File:** `lead-management-collection.json`  
**Coverage:** Lead CRUD, conversions, statistics, multi-tenancy tests  
**Feature:** 006-lead-management

## Changelog v1.39 (Latest - 2026-07-23)

**`Invite User` example/description corrected — `agent` object scope**

✅ Fixed a stale example that survived the v1.38 correction: the `agent` object's example body and description text still showed `name`/`cpf`/`email`/`phone`/`mobile`/`hire_date` as accepted fields. These already live on the profile referenced by `profile_id` (shared by every profile_type this endpoint invites) and are no longer part of the `agent` object's actual contract — only `creci`, `bank_name`, `bank_account`, `pix_key` are.
✅ Removed a second stale claim in the same description: "external profiles (tenant, property_owner): creates dual record" — that code path (`create_portal_user`) is dead, never called; only agent-typed invites create a domain record alongside the login.

## Changelog v1.38 (2026-07-23)

**`POST /api/v1/agents` removed (Feature 026, User Story 3)**

✅ The legacy `Create Agent` request has been deleted from the "6. Agents" folder — the endpoint itself was physically removed from the API (no deprecation window, per explicit product decision recorded in `specs/026-user-agent-registration-unification/spec-idea.md`).
✅ `Invite User` (in "2. User Invitation") is now the single, unified way to onboard an agent, linking the resulting `real.estate.agent` record to both the profile and the new login.

## Changelog v1.35 (2026-07-09)

**Lead company isolation enforced (Feature 024)**

✅ `List Leads`, `Export Leads to CSV`, and `Get Lead Statistics` now actually enforce the company/agent isolation their descriptions always claimed.
✅ `List Lead Activities`, `Log Activity on Lead`, and `Schedule Activity on Lead` now require `@require_company` and document the new **403 ACCESS_DENIED** response for cross-company access attempts.

## Changelog v1.31 (2026-05-12)

**Property FGTS eligibility**

✅ Property create/update examples include a single `fgts` object with `accepts_fgts`, `used_fgts`, `last_usage_date`, and `usage_notes`.
✅ Property response examples document the single `fgts` object with computed eligibility fields.
✅ `fgts.last_usage_date` is documented as ISO date (`YYYY-MM-DD`); `fgts.used_fgts` is a JSON boolean.

## Changelog v1.30 (2026-05-11)

**Property selectable options**

✅ `property_situation` is now documented as a selectable property field.
✅ `GET /api/v1/properties/options` returns `property_situation` options: `Não Informado`, `Desocupado`, `Ocupado`, `Reservado`, `Em construção`, `Lançamento`, `Novo`.
✅ Property create/update examples use valid `property_situation` values.
✅ Property create/update examples use `owner_id` to link the related owner.
✅ Property detail/list examples document `owner` as the response object from the `owner_id` relationship.
✅ Legacy property owner scalar fields were removed from property request/response examples.
✅ Swagger/OpenAPI was validated after upgrading `quicksol_estate`.

## Changelog v1.20 (2026-02-22)

**Security hardening for password endpoints (Feature 009)**

🔐 **Token format validation** — `set-password` and `reset-password` now reject tokens that are not exactly 32 lowercase hex characters before touching the database. Returns **400 validation_error**. Prevents timing attacks and unnecessary DB lookups.

🔐 **Cross-type token abuse blocked** — `set-password` only accepts tokens with `token_type='invite'`; `reset-password` only accepts `token_type='reset'`. Submitting the wrong type returns **404 not_found** — identical to a missing token, so no state is leaked.

🔐 **Last-token-wins (race condition fix)** — `generate_token()` now atomically invalidates all previous `pending` tokens of the same type for the user before creating the new one. Only one active token per user+type can exist at any time.

📋 **E2E test added** — `integration_tests/test_us9_s2_set_password.sh` covers 9 scenarios (T28-1 to T28-9): valid token, used, expired, not found, malformed, short password, mismatch, missing fields, cross-type abuse.

## Changelog v1.19 (2026-02-21)

⚠️ **BREAKING CHANGE:** Removed legacy invite flows - only unified profile flow remains  
✅ **Removed requests:** "Invite User (Standard Profile)" and "Invite User (Tenant Profile)"  
✅ **Single endpoint:** Only "Invite User (from Profile ID)" remains (simplified name to "Invite User")  
✅ **Performance:** Query optimization (browse+exists → search, -1 query)  
✅ **Compliance:** ADR-001 — removed redundant validations from controller layer  
✅ **Response simplified:** No longer includes extension_record, tenant_id, property_owner_id fields  
✅ **Architecture:** Profile is the single source of truth (Feature 010 fully implemented)  
✅ **Unified flow:** create_user_from_profile() method replaces dual record logic  
✅ **Authorization matrix:** Updated to reflect tenant/property_owner (portal removed)

**Migration from v1.16/older:**  
If you have "Invite User (Standard Profile)" or "Invite User (Tenant Profile)" requests, delete them and use only the unified "Invite User" request with profile_id.

## Changelog v1.18 (2026-02-21)

⚠️ **BREAKING CHANGE:** POST /api/v1/users/invite - Unified Profile Flow introduced  
✅ **Simplified API:** Endpoint accepts `profile_id` + `session_id` in request body  
✅ **Workflow:** 1) POST /api/v1/profiles → 2) POST /api/v1/users/invite with profile_id  
✅ **Auto-extraction:** All user data (name, email, document, phone, birthdate, company_id, profile_type) loaded from profile  
✅ **No X-Company-ID header:** Company context extracted from profile.company_id  
✅ **Feature 010:** Integration with unified profile management started

**Migration Guide:**  
- **Before (v1.17):** POST /api/v1/users/invite with `{ name, email, document, profile, session_id, ...}`  
- **After (v1.18):** 1) POST /api/v1/profiles with all data → 2) POST /api/v1/users/invite with `{ profile_id, session_id }`

## Changelog v1.17

⚠️ **BREAKING CHANGE:** Profile type 'portal' renamed to 'tenant' (semantic clarity)  
✅ **NEW**: Added 'property_owner' as 10th profile type (external level)  
✅ Updated authorization matrix: Agent can now invite property_owner + tenant (not owner)  
✅ Updated all profile enums: 10 types total (owner, director, manager, agent, prospector, receptionist, financial, legal, tenant, property_owner)  
✅ Profile types organization: Admin (3), Operational (5), External (2)  
✅ Swagger generation: Dynamic from thedevkitchen_api_endpoint table (ADR-005)

## Changelog v1.16

✅ Minor documentation improvements

## Changelog v1.7

⚠️ **BREAKING CHANGE:** Create Owner (POST /api/v1/owners) now requires CPF field  
✅ CPF validation using validate_docbr library  
✅ CPF unique constraint: each user must have unique CPF  
✅ CPF returned in Create Owner response

## Changelog v1.6

✅ Added GET /api/v1/assignments (list with pagination + filters)  
✅ Added GET /api/v1/assignments/{id} (detail)  
✅ Added PATCH /api/v1/assignments/{id} (update)  
✅ Updated POST /api/v1/assignments (added company_id, responsibility_type, commission_percentage)  
✅ RBAC: Admin sees all, Manager sees company, Agent sees own  
✅ Multi-tenancy: 404 if not accessible (ADR-008)  
✅ HATEOAS: Pagination links (self, next, prev)

## Changelog v1.5

✅ Fixed ADR-016 compliance: version format (major.minor only)  
✅ Fixed Master Data endpoints: added required auth headers (JWT + Session + Company)  
✅ Fixed Link Owner to Company URL (POST to /owners/:id/companies with company_id in body)  
✅ Reorganized folder structure: merged Feature 007 into numbered folders  
✅ Added missing variables: owner_id, company_id

## Changelog v1.3

✅ Complete API coverage (50+ endpoints)  
✅ 13 organized folders by domain  
✅ Properties CRUD with filters  
✅ Agents management (create, deactivate, reactivate)  
✅ Assignments (property-to-agent)  
✅ Commission rules and transactions  
✅ Performance metrics and rankings  
✅ Lead management with activities and filters  
✅ Master Data (property types, locations, amenities, etc.)  
✅ Test scripts for auto-populating IDs  
✅ ADR-016 compliant headers

## Changelog v1.2

✅ Added all 15 Lead Management endpoints (Feature 006)  
✅ Fixed headers per ADR-016 (`X-Openerp-Session-Id` for GET)  
✅ Added test scripts for auto-populating tokens  
✅ Added `refresh_token` variable support  
✅ Reorganized folders by domain  
✅ Added advanced search examples  
✅ Added test scenarios for validation

## Collection Structure (v1.3)

### 1. Authentication
OAuth 2.0 token management endpoints:
- Get OAuth Token
- Refresh Token
- Revoke Token

### 2. Users
User login, logout, and session management:
- User Login (creates session)
- User Logout
- Get Current User (/me)
- Update Profile
- Change Password

### 3. Properties
Property CRUD operations:
- List Properties (with filters)
- Create Property
- Get Property Details
- Update Property
- Delete Property (archive)

### 4. Agents
Agent management operations:
- List Agents
- Create Agent
- Get Agent Details
- Update Agent
- Deactivate Agent
- Reactivate Agent
- Get Agent's Properties

### 5. Assignments
Property-to-agent assignments:
- List Assignments
- Create Assignment
- Delete Assignment

### 6. Commissions
Commission rules and transactions:
- Get Commission Rules
- Create Commission Rule
- Update Commission Rule
- Create Commission Transaction

### 7. Performance
Agent metrics and rankings:
- Get Agent Performance
- Get Agents Ranking

### 8-12. Leads (CRUD, Actions, Analytics, Activities, Filters)
Complete lead management:
- Lead CRUD operations
- Convert to Sale, Reopen Lost Lead
- Statistics and CSV export
- Activity logging and scheduling
- Saved search filters

### 13. Master Data
Reference data (some public):
- Property Types
- Location Types
- States/Regions
- Tags
- Amenities
- Owners
- Companies

### 3. Agents
Agent CRUD operations with RBAC:
- List Agents
- Create Agent
- Get Agent Details
- Update Agent
- Delete Agent

### 4. Properties
Property management with multi-tenancy:
- List Properties (filtered by user role)
- Create Property
- Get Property Details
- Update Property
- Delete Property

### 5. Assignments
Property-to-agent assignment management:
- List Assignments
- Create Assignment
- Update Assignment
- Delete Assignment

### 6. Commissions
Commission tracking and management:
- List Commissions
- Calculate Commission
- Update Commission Status

### 7. Performance
Agent performance metrics:
- Agent Sales Metrics
- Commission Reports
- Property Conversion Rates

### 8. Master Data
Reference data endpoints:
- Property Types
- Location Types
- States/Regions

### 9. Leads (NEW - Feature 006) ⭐
Lead management endpoints:
- **CRUD**: List, Create, Get, Update, Archive (soft delete)
- **Actions**: Convert to Sale, Reopen Lost Lead
- **Analytics**: Statistics by state, agent, date range
- **Test Scenarios**: Duplicate prevention, multi-tenancy, state transitions

### 10. Test Journeys (E2E) ⭐

Complete end-to-end test journeys validating RBAC implementation:

#### US1 - Owner Onboarding (3/3 ✅)
- **US1-S1:** Owner Login - Authentication and company creation
- **US1-S2:** Owner CRUD Operations - Full CRUD on properties
- **US1-S3:** Multi-tenancy Isolation - Cross-company access blocked

#### US2 - Manager Team Creation (4/4 ✅)
- **US2-S1:** Manager Creates Agent - Expected restriction (only Owner can create users)
- **US2-S2:** Manager Menu Access - Company data access validated
- **US2-S3:** Manager Assigns Properties - Property-to-agent assignment
- **US2-S4:** Manager Company Isolation - Multi-tenant filtering

#### US3 - Agent Property Management (4/5 ✅ + 1 SKIP)
- **US3-S1:** Agent Assigned Properties - Sees only assigned properties
- **US3-S2:** Agent Auto-Assignment - agent_id auto-set on create
- **US3-S3:** Agent Own Leads - ⏭️ SKIP (requires CRM module)
- **US3-S4:** Agent Cannot Modify Others - Record rule isolation
- **US3-S5:** Agent Company Isolation - Multi-tenant enforcement

#### US4 - Manager Oversight (3/3 ✅)
- **US4-S1:** Manager All Data - Sees all company properties/agents
- **US4-S2:** Manager Reassign Properties - Reassigns between agents
- **US4-S4:** Manager Multi-tenancy - Cross-company isolation

#### US5 - Prospector Property Creation (4/4 ✅)
- **US5-S1:** Prospector Creates Property - prospector_id auto-assigned
- **US5-S2:** Prospector Agent Assignment - Manager assigns selling agent
- **US5-S3:** Prospector Visibility - Sees only own prospected properties
- **US5-S4:** Prospector Restrictions - Cannot access leads/sales

#### US6 - Receptionist Lease Management (2/2 ✅)
- **US6-S1:** Receptionist Lease Management - Full CRUD on leases
- **US6-S2:** Receptionist Restrictions - Read-only on properties (security fix applied)

### 10. RBAC Testing

Additional RBAC validation scenarios:
- Agent - View Own Properties
- Prospector - Create Property
- Receptionist - View Sales (Read-Only)
- Receptionist - Update Sale (Should Fail)
- Financial - View Commissions
- Financial - Update Commission Status
- Legal - View Contracts (Read-Only)
- Portal User - View Own Contracts
- Multi-Tenancy - Company Isolation
- Audit Log - Permission Changes

## Environment Variables

Create a Postman environment with the following variables:

```json
{
  "base_url": "http://localhost:8069",
  "client_id": "your_client_id",
  "client_secret": "your_client_secret",
  "access_token": "",
  "session_id": "",
  "refresh_token": ""
}
```

## Usage

### 1. Get OAuth Token

Run "Get OAuth Token" request first. It will automatically save `access_token` to environment.

### 2. Login as User

Run "User Login" request with credentials:
```json
{
  "db": "realestate",
  "login": "user@company.com",
  "password": "password123"
}
```

This will save `session_id` to environment.

### 3. Run Business Requests

All business endpoints require:
- **Authorization header:** `Bearer {{access_token}}`
- **Session ID:**
  - GET requests: Header `X-Openerp-Session-Id: {{session_id}}`
  - POST/PUT/PATCH: Body property `"session_id": "{{session_id}}"`

### 4. Run Test Journeys

Navigate to **"9. Test Journeys (E2E)"** folder to run complete validation scenarios:

1. **Setup Test Users** (via Odoo UI or admin API):
   - Owner: `owner@company.com`
   - Manager: `manager@company.com`
   - Agent: `agent@company.com`
   - Prospector: `prospector@company.com`
   - Receptionist: `receptionist@company.com`

2. **Run Journey Sequentially**:
   - Each test builds on previous setup
   - Follow US1 → US2 → US3 → US4 → US5 → US6 order

3. **Validate Results**:
   - Check HTTP status codes (200, 201, 403, 404)
   - Verify response data matches expectations
   - Confirm record rules filter correctly

## Test Coverage

**Total E2E Tests:** 21 scenarios  
**Passing:** 20 tests (95.2%)  
**Skipped:** 1 test (US3-S3 - CRM module not implemented)

**User Profiles Validated:**
- ✅ Owner (Real Estate Owner)
- ✅ Director (Company Director) 
- ✅ Manager (Company Manager)
- ✅ User (Company User)
- ✅ Agent (Real Estate Agent)
- ✅ Prospector (Property Prospector)
- ✅ Receptionist (Office Receptionist)
- ✅ Financial (Financial Team)
- ✅ Legal (Legal Team)
- ✅ Portal User (External Portal User)

## Critical Security Fix

**Receptionist Privilege Escalation** (2026-01-26 - Commit 2ce112c)

**Issue:** Receptionist could create properties despite read-only role specification.

**Solution:**
1. Changed Receptionist group inheritance (groups.xml line 51)
2. Removed CREATE permission from User group (ir.model.access.csv line 85)
3. Fixed test to use dynamic group lookup (test_us6_s2)

**Validation:** All 6 restriction checks passing ✅

## Session ID Transmission Rules

⚠️ **CRITICAL - Read Carefully**

### GET Requests (type='http')
```
Header: X-Openerp-Session-Id: {{session_id}}
```

**❌ NEVER send session_id in body for GET requests** - it will be ignored!

### POST/PUT/PATCH (type='json')
```json
{
  "session_id": "{{session_id}}",
  "field1": "value1"
}
```

**✅ Direct property in JSON body** (NOT inside params wrapper)

## JSON Format

**OAuth endpoints:** Direct JSON (no JSONRPC wrapper)
```json
{
  "client_id": "...",
  "client_secret": "...",
  "grant_type": "client_credentials"
}
```

**Business endpoints:** Direct JSON (no JSONRPC wrapper)
```json
{
  "session_id": "...",
  "name": "Property Name",
  "price": 500000
}
```

**❌ DO NOT use:**
```json
{
  "jsonrpc": "2.0",
  "method": "call",
  "params": { ... }
}
```

## Fingerprint Validation

Keep **User-Agent** header consistent during session lifetime:
- Session is bound to IP + User-Agent + Accept-Language
- Changing User-Agent invalidates session
- Use same Postman app for entire session

## Authentication Flow

```
1. GET /api/v1/auth/token
   ↓ (returns access_token)
2. POST /api/v1/users/login (with Bearer token)
   ↓ (returns session_id)
3. Business requests (with Bearer + session_id)
```

## Related Documentation

- [IMPLEMENTATION_VALIDATION.md](../../specs/005-rbac-user-profiles/IMPLEMENTATION_VALIDATION.md) - Complete validation report
- [STATUS.md](../../integration_tests/STATUS.md) - Integration tests status
- [COMPLETION-STATUS.md](../../specs/005-rbac-user-profiles/COMPLETION-STATUS.md) - Final achievement summary
- [spec.md](../../specs/005-rbac-user-profiles/spec.md) - RBAC specification
- [ADR-016](../../docs/adr/ADR-016-api-documentation-standards.md) - API documentation standards

## Standards Compliance

This collection follows:
- **ADR-016:** API Documentation Standards
- **ADR-003:** Mandatory Test Coverage
- **ADR-008:** Testing Best Practices
- **Spec 005:** RBAC User Profiles Implementation

## Import Instructions

1. Open Postman
2. Click "Import" button
3. Select `quicksol_api_v1.1_postman_collection.json`
4. Create environment with required variables
5. Start with "1. Authentication" folder
6. Progress through "9. Test Journeys" for E2E validation

---

**Last Updated:** 2026-01-27  
**Collection Version:** 1.2.0  
**Odoo Version:** 18.0  
**Module:** quicksol_estate
