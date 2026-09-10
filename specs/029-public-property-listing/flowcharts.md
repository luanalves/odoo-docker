# Feature 029 — Journey Flowcharts

One diagram per user story, covering actor, endpoint calls (method + path), and decision points, per the spec's Success Criteria. Feature 029 is 100% headless API (no Odoo UI/views introduced — see spec NFR5), so all three diagrams are sequence diagrams rather than UI-navigation flowcharts.

---

## User Story 1: SSR frontend renders an agency's public property listing

```mermaid
sequenceDiagram
    actor U as SSR Frontend (service JWT)
    participant API as CmsPublicPropertyController
    participant Slug as cms_slug_service
    participant Prop as real.estate.property

    U->>API: GET /api/v1/public/properties/{company_slug}
    API->>API: auth="none" + @require_jwt (Bearer token only, no session)
    alt token ausente ou inválido
        API-->>U: 401 unauthorized
    else token válido
        API->>Slug: resolve_company_by_slug(env, company_slug)
        alt company_slug desconhecido
            Slug-->>API: None
            API-->>U: 404 not_found (mesma mensagem genérica sempre)
        else company_id resolvido
            API->>API: parse_status/ids/sort/limit (todos opcionais)
            alt qualquer parâmetro inválido
                API-->>U: 400 validation_error (+ "allowed" quando aplicável)
            else parâmetros válidos (ou omitidos)
                API->>Prop: search(domain, limit, order) com bin_size=True
                Note over API,Prop: domain SEMPRE inclui company_id + active=True +<br/>publish_website=True — nenhum filtro consegue remover isso
                Prop-->>API: até 100 registros (default 20)
                API->>API: serialize_public_property() por registro<br/>(PII-free: sem owner/agent/endereço exato/lat-long)
                API-->>U: 200 {company_slug, count, limit, filters, data[], _links}
            end
        end
    end
```

---

## User Story 2: Public listing filtered by status and explicit ID set

```mermaid
flowchart TD
    A[Frontend monta a URL] --> B{status informado?}
    B -->|Não| C[Sem filtro implícito de status —<br/>retorna qualquer property_status,<br/>desde que publish_website=True]
    B -->|Sim| D{status ∈ available/rented/sold/reserved?}
    D -->|Não| D1[400 validation_error + allowed: 4 valores]
    D -->|Sim| E[Filtro property_status IN status aplicado]
    C --> F{ids informado?}
    E --> F
    F -->|Não| G[Sem filtro por id]
    F -->|Sim| H{todos os tokens são inteiros?}
    H -->|Não| H1[400 validation_error]
    H -->|Sim| I[Filtro id IN ids — AND-combinado com<br/>company_id/active/publish_website/status]
    I --> J{algum id pertence a outra empresa<br/>ou não é publish_website=True?}
    J -->|Sim| K[Excluído SILENCIOSAMENTE do resultado —<br/>nunca um erro distinto ADR-008]
    J -->|Não| L[Incluído no resultado]
    G --> M[200 com data filtrada]
    K --> M
    L --> M
```

---

## User Story 3: Public main-image delivery for listing cards

```mermaid
sequenceDiagram
    actor U as SSR Frontend (service JWT)
    participant API as CmsPublicPropertyController
    participant Slug as cms_slug_service
    participant Prop as real.estate.property

    U->>API: GET /api/v1/public/properties/{company_slug}/{property_id}/image
    API->>API: auth="none" + @require_jwt (mesmo modelo da US1)
    alt token ausente ou inválido
        API-->>U: 401 unauthorized
    else token válido
        API->>Slug: resolve_company_by_slug(env, company_slug)
        alt company_slug desconhecido
            API-->>U: 404 not_found ("Image not found" — genérico)
        else company_id resolvido
            API->>Prop: search(build_public_property_domain(company_id) + [id=property_id])
            Note over API,Prop: MESMO gate de visibilidade da listagem —<br/>esta rota NUNCA pode ser usada para<br/>enumerar properties não-públicas
            alt não encontrado, outra empresa,<br/>não publicado, arquivado, ou sem imagem
                Prop-->>API: (vazio) ou image=False
                API-->>U: 404 not_found ("Image not found" —<br/>indistinguível entre os 5 casos)
            else encontrado com imagem
                Prop-->>API: property.image (base64)
                API->>API: base64.b64decode + magic.from_buffer (MIME real)
                API-->>U: 200 bytes brutos, Content-Type detectado,<br/>SEM Content-Disposition (renderização inline em <img>)
            end
        end
    end
    Note over U,Prop: Bytes NUNCA são servidos via redirect para<br/>/web/content/ — Response direto (Feature 017 invariant)
