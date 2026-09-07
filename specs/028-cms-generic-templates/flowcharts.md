# Feature 028 — Journey Flowcharts

One diagram per user story, covering actor, actions, endpoints (method + path), and decision points, per the spec's Success Criteria.

---

## User Story 1: Admin gerencia o catálogo de templates genéricos via Odoo UI

Fluxo 100% Odoo UI (admin-only, sem endpoint REST de escrita — ADR-029).

```mermaid
flowchart TD
    A[Admin loga no Odoo] --> B[Navega: CMS > Templates Genéricos]
    B --> C{List view carrega?}
    C -->|Erro / Oops!| C1[Investigar — bug, não deveria ocorrer]
    C -->|OK| D[Clica em Novo]
    D --> E[Preenche name, category, content Puck JSON]
    E --> F[Salva]
    F --> G{name já existe na plataforma?}
    G -->|Sim| G1[_sql_constraints unique_name bloqueia — mensagem clara]
    G -->|Não| H{content é JSON válido e ≤512KB?}
    H -->|Não| H1[Constraint Python rejeita antes de persistir]
    H -->|Sim| I[Registro salvo com active=True]
    I --> J[Template genérico disponível para todas as companies via API]
    J --> K[Admin decide desativar mais tarde?]
    K -->|Sim| L[active=False — desaparece da listagem/API]
    L --> M[Cópias já existentes em outras companies permanecem intactas]
    K -->|Não| N[Fim]
```

---

## User Story 2: Owner/Director/Manager lista e visualiza templates genéricos

```mermaid
sequenceDiagram
    actor U as Owner/Director/Manager
    participant API as CmsTemplateGenericController
    participant DB as thedevkitchen.cms.template.generic

    U->>API: GET /api/v1/cms/templates/generic?category=landing
    API->>API: @require_jwt + @require_session + @require_company
    API->>API: role in (owner, director, manager)?
    alt papel não autorizado (ex. agent, tenant)
        API-->>U: 403 forbidden
    else papel autorizado
        API->>DB: search(active=True[, category=...], limit≤50)
        DB-->>API: templates (sem content, sem company_id)
        API-->>U: 200 {items, total, limit, offset}
    end

    U->>API: GET /api/v1/cms/templates/generic/{id}
    API->>API: role in (owner, director, manager)?
    alt papel não autorizado
        API-->>U: 403 forbidden
    else papel autorizado
        API->>DB: search(id=..., active=True)
        alt inexistente ou inativo
            DB-->>API: (vazio)
            API-->>U: 404 not_found
        else encontrado
            DB-->>API: template + content_ids[0].content
            API-->>U: 200 {..., content: "Puck JSON"}
        end
    end
```

---

## User Story 3: Owner/Director/Manager copia um template genérico para a própria company

```mermaid
sequenceDiagram
    actor U as Owner/Director/Manager (Company A)
    participant API as CmsTemplateGenericController
    participant Gen as thedevkitchen.cms.template.generic
    participant Tpl as thedevkitchen.cms.template (Company A)

    U->>API: POST /api/v1/cms/templates/generic/{id}/copy {"name"?: "..."}
    API->>API: @require_jwt + @require_session + @require_company
    API->>API: role in (owner, director, manager)?
    alt papel não autorizado
        API-->>U: 403 forbidden
    else papel autorizado
        API->>Gen: search(id=..., active=True)
        alt genérico inexistente ou inativo
            Gen-->>API: (vazio)
            API-->>U: 404 not_found
        else genérico encontrado
            API->>API: company_id = request.env.company.id (NUNCA do payload — ADR-008)
            API->>API: name = payload.name ou generic.name
            API->>Tpl: name já existe em Company A?
            loop até 100 tentativas
                alt conflito de nome
                    API->>API: aplica sufixo " (2)", " (3)", ...
                else nome livre
                    API->>API: segue com este nome
                end
            end
            alt 100 tentativas esgotadas
                API-->>U: 409 generic_copy_conflict
            else nome livre encontrado
                API->>Tpl: with cr.savepoint(): create({name, category, company_id, source_generic_template_id: id})
                API->>Tpl: create content (copiado do genérico)
                Tpl-->>API: novo template criado
                API-->>U: 201 {id, ..., source_generic_template_id, content}
            end
        end
    end

    Note over Tpl: Cópia é um snapshot independente —<br/>desativar o genérico depois NUNCA afeta a cópia.
    Note over U,Tpl: Isolamento: Company B nunca vê esta cópia<br/>em GET /api/v1/cms/templates (domain company_id).
```
