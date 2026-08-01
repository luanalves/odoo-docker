# Feature 027 — Journey Flowcharts

## User Story 1: Owner deactivates a profile (any profile_type)

```mermaid
sequenceDiagram
    actor Owner
    participant API as POST/DELETE /api/v1/profiles/{id}
    participant Profile as thedevkitchen.estate.profile
    participant Agent as real.estate.agent
    participant User as res.users
    participant Session as thedevkitchen.api.session (Redis-backed)

    Owner->>API: DELETE /api/v1/profiles/{id}
    API->>API: _user_can_deactivate_or_reactivate_profile(owner) -> True
    API->>Profile: write(active=False, deactivation_date, deactivation_reason)
    alt profile_type == 'agent'
        API->>Agent: write(active=False, ...)
    end
    API->>User: write(active=False)
    API->>Session: write(is_active=False)  note right: proactive Redis cache invalidation (Feature 023)
    API-->>Owner: 200 {"success": true}
```

## User Story 1b: Manager attempts to deactivate (denied)

```mermaid
sequenceDiagram
    actor Manager
    participant API as DELETE /api/v1/profiles/{id}

    Manager->>API: DELETE /api/v1/profiles/{id}
    API->>API: _user_can_deactivate_or_reactivate_profile(manager) -> False
    API-->>Manager: 403 forbidden
```

## User Story 2: Owner reactivates a previously deactivated profile

```mermaid
sequenceDiagram
    actor Owner
    participant API as POST /api/v1/profiles/{id}/reactivate
    participant Profile as thedevkitchen.estate.profile
    participant Agent as real.estate.agent
    participant User as res.users

    Owner->>API: POST /api/v1/profiles/{id}/reactivate
    API->>API: _user_can_deactivate_or_reactivate_profile(owner) -> True
    API->>Profile: active? -- if True, 400 "already active"
    API->>Profile: write(active=True, deactivation_date=False, deactivation_reason=False)
    alt profile_type == 'agent'
        API->>Agent: write(active=True, ...)
    end
    API->>User: write(active=True)
    note over API: thedevkitchen.api.session is NEVER touched here -- old session stays invalid
    API-->>Owner: 200 {"data": {...}}
```

## User Story 3: Any authorized user lists agents via /profiles

```mermaid
sequenceDiagram
    actor User
    participant API as GET /api/v1/profiles?profile_type=agent&creci_number=...
    participant ProfileModel as thedevkitchen.estate.profile
    participant AgentModel as real.estate.agent

    User->>API: GET /api/v1/profiles?company_ids=1&profile_type=agent&creci_number=12345
    API->>API: _resolve_profile_ids_by_agent_filters(env, "12345", None)
    API->>AgentModel: search([("creci_number","ilike","12345")])
    AgentModel-->>API: [profile_ids]
    API->>ProfileModel: search(domain + [("id","in",profile_ids)])
    ProfileModel-->>API: [profiles]
    API->>AgentModel: search([("profile_id","in",[p.id for p in profiles])])  note right: ONE batched query, not one per row
    AgentModel-->>API: [agents]
    API-->>User: 200 {"data": [{...,"agent": {...}}]}
```

## User Story 4: Manager updates an agent's CRECI via /profiles

```mermaid
sequenceDiagram
    actor Manager
    participant API as PUT /api/v1/profiles/{id}
    participant Profile as thedevkitchen.estate.profile
    participant Agent as real.estate.agent

    Manager->>API: PUT /api/v1/profiles/{id} {"creci": "CRECI-SP 99999"}
    API->>API: profile.profile_type_id.code == 'agent' -> validate_profile_agent_update_fields
    API->>Profile: write(updated_at)
    API->>Agent: write(creci="CRECI-SP 99999")
    alt duplicate creci in same company
        Agent-->>API: ValidationError
        API->>API: env.cr.rollback()
        API-->>Manager: 409 conflict
    else success
        API-->>Manager: 200 {"agent": {"creci": "CRECI-SP 99999", ...}}
    end
```
