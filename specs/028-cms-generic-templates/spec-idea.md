# Feature Specification: CMS — Templates Genéricos (Catálogo de Plataforma)

**Feature Branch**: `028-cms-generic-templates`
**Created**: 2026-09-06
**Status**: Draft
**Solution Type**: Ambos — Odoo UI (admin, gestão do catálogo genérico) + API REST (leitura e cópia, papéis de gestão CMS)
**ADR References**: ADR-001, ADR-003, ADR-004, ADR-005, ADR-007, ADR-008, ADR-009, ADR-011, ADR-015, ADR-016, ADR-018, ADR-019, ADR-022, ADR-029

## Executive Summary

Introduz um catálogo de templates CMS de nível de **plataforma** (`thedevkitchen.cms.template.generic`) — sem `company_id`, curado exclusivamente pelo usuário `admin` do Odoo (`base.group_system`) via UI, conforme ADR-029. Usuários com papel de gestão de CMS (`owner`, `director`, `manager`) de qualquer imobiliária podem listar, visualizar e "copiar" esses templates para o catálogo de templates da própria company (`thedevkitchen.cms.template`, Feature 021), acelerando a criação de páginas sem exigir esforço editorial duplicado por tenant.

---

## Clarifications

### Decisões finais (todas resolvidas)

- **Nível admin** = literalmente `base.group_system` → CRUD do catálogo genérico é 100% Odoo UI (sem endpoints REST de create/update/delete), consistente com ADR-029 (admin bloqueado de autenticar via REST).
- **Modelo de dados** = novo modelo separado `thedevkitchen.cms.template.generic` (+ `.content` 1:1), sem `company_id`, visível a todas as companies. Copiar = criar registro correspondente em `thedevkitchen.cms.template` (company-scoped).
- **Autorização unificada de leitura e cópia** (list, detail e copy): restrita aos **mesmos papéis que já gerenciam templates CMS de company hoje** (Feature 021) — confirmado no código-fonte (`cms_template_controller.py`, todas as 5 rotas usam `if role not in ("owner", "director", "manager")`). Portanto, **`owner`, `director` e `manager`** são os únicos papéis autorizados nos 3 endpoints desta feature (`GET .../generic`, `GET .../generic/{id}`, `POST .../generic/{id}/copy`). Nenhum outro papel (agent, prospector, receptionist, financial, legal, property_owner, tenant/portal) tem acesso a este catálogo nesta iteração — isso substitui a decisão inicial de "qualquer um dos 10 papéis logados" levantada na primeira rodada de esclarecimento.
- **MVP** = Não — especificação completa.

> Não há pontos `[NEEDS CLARIFICATION]` em aberto nesta versão da spec — os dois pontos identificados durante a elaboração (autorização da cópia; escopo de papéis na leitura) foram resolvidos pelo usuário e incorporados acima.

---

## Out of Scope / Non-Goals

**Fora de Escopo**:
- Endpoints REST para criar/editar/excluir templates genéricos — CRUD do catálogo é 100% Odoo UI, admin-only (ADR-029). "Aplicar" um template genérico = geri-lo via Odoo UI, não escrevê-lo via API.
- Acesso de leitura (listagem/detalhe) ou de cópia por papéis fora de `owner`/`director`/`manager` — em particular, `agent`, `prospector`, `receptionist`, `financial`, `legal`, `property_owner` e `tenant`/portal **não** têm acesso a este catálogo nesta iteração, mesmo que já tenham algum nível de acesso de leitura a páginas CMS publicadas (Feature 021 US3). Uma extensão futura pode reavaliar isso, mas está fora do escopo atual.
- Sincronização/propagação automática de mudanças no template genérico para cópias já existentes nas companies — cada cópia é um snapshot independente, desacoplado do genérico após a criação.
- Versionamento/histórico de templates genéricos.
- Suporte multilíngue no catálogo genérico (mesmo non-goal da Feature 021).
- Alteração da autorização já estabelecida de `thedevkitchen.cms.template` (company-scoped) — a única mudança é uma nova origem possível de conteúdo (cópia de um genérico) e um novo campo de rastreabilidade.
- Limite de quantas vezes uma company pode copiar o mesmo template genérico — cópias múltiplas são permitidas (cada uma gera um nome único via sufixo automático).

**Comportamentos Proibidos** (o desenvolvimento NUNCA deve introduzir):
- [ ] Não permitir que `base.group_system` autentique via API REST (ADR-029) — nenhum endpoint novo desta feature deve contornar o bloqueio de login do admin.
- [ ] Não aceitar `company_id` em nenhum payload desta feature — o `company_id` da cópia é sempre derivado da sessão autenticada (`request.env.company.id`), nunca do body (ADR-008 princípios 2–3).
- [ ] Não enfraquecer o isolamento multi-tenant de `thedevkitchen.cms.template` — a cópia respeita o mesmo `unique(name, company_id)` e a mesma RBAC de escrita já existentes.
- [ ] Não expor endpoints de escrita (create/update/delete) do catálogo genérico via API.
- [ ] Não substituir soft delete por exclusão física (ADR-015) — desativação do genérico usa `active=False`.
- [ ] Não usar `.sudo()` para bypass de checagem de **autorização de papel** (a checagem `role not in ("owner", "director", "manager")` continua explícita no controller para os 3 endpoints); `.sudo()` é aceitável apenas para a leitura de uma entidade sem isolamento de company, mesmo padrão já usado em `cms_template_controller.py`.
- [ ] Não conceder acesso de leitura a este catálogo a papéis além de `owner`/`director`/`manager` sem uma decisão explícita futura — evitar "vazamento" gradual de escopo (ex.: adicionar `agent` "só para teste" e esquecer de remover).

**Armadilhas Conhecidas a Evitar**:
- Não reintroduzir a possibilidade de `base.group_system` logar via `/api/v1/users/login` — este é exatamente o gap que a ADR-029 fechou (Feature 022); esta feature reforça, não contorna, esse bloqueio.
- Evitar N+1 ao serializar conteúdo: listagem NUNCA inclui `content` (só metadados); apenas o endpoint de detalhe (`GET .../generic/{id}`) busca `content_ids[0].content` — mesmo padrão já usado em `_serialize_template()` (`cms_template_controller.py`).
- Não assumir que o conjunto de papéis autorizados desta feature é diferente do já usado em `cms_template_controller.py` — reaproveitar literalmente a mesma tupla `("owner", "director", "manager")`, não uma lista redigitada manualmente (risco de digitação/drift entre os dois controllers).

---

## User Scenarios & Testing

### User Story 1: Admin gerencia o catálogo de templates genéricos via Odoo UI (Priority: P1) 🎯 MVP

**As a** usuário `admin` do sistema (Odoo System Admin, `base.group_system`)
**I want to** criar, editar e desativar templates genéricos de página (landing, property, about) diretamente na interface do Odoo
**So that** todas as imobiliárias da plataforma tenham acesso a um catálogo curado de layouts iniciais, sem que eu precise gerenciar templates individualmente por company

**Acceptance Criteria**:
- [ ] Given usuário `admin` logado no Odoo, when navega até o menu "CMS > Templates Genéricos", then a list view carrega sem erro "Oops!" e sem erros de console JavaScript.
- [ ] Given form view aberta, when preenche `name`, `category` e o `content` (Puck JSON), then o registro é salvo com `active=True`.
- [ ] Given `name` já existente na plataforma, when salva, then Odoo bloqueia via `_sql_constraints unique(name)` com mensagem clara.
- [ ] Given `content` inválido (não é JSON), when salva, then a constraint Python rejeita antes de persistir.
- [ ] Given template genérico existente, when o admin desativa (`active=False`), then ele desaparece da listagem/API mas cópias já existentes permanecem intactas.
- [ ] Given qualquer usuário não-admin, when tenta acessar a UI do Odoo, then não é aplicável — apenas o `admin` acessa a UI (conforme Restrição Arquitetural do projeto); não há checagem de `groups` no menuitem.

**Test Coverage** (per ADR-003):

| Type | Test Name | Description | Status |
|------|-----------|-------------|--------|
| Unit | `test_generic_template_name_required()` | `name` obrigatório | ⚠️ Required |
| Unit | `test_generic_template_name_unique()` | Unicidade global de `name` | ⚠️ Required |
| Unit | `test_generic_template_category_required()` | `category` obrigatório, valores válidos | ⚠️ Required |
| Unit | `test_generic_template_content_valid_json()` | Conteúdo deve ser JSON válido | ⚠️ Required |
| Unit | `test_generic_template_content_max_size()` | Limite 512KB (mesmo de `cms.page.content`) | ⚠️ Required |
| Unit | `test_generic_template_soft_delete()` | `active=False` não remove fisicamente | ⚠️ Required |
| E2E (UI) | `cypress: test_generic_template_menu_loads_without_errors()` | Menu carrega sem "Oops!" | ⚠️ Required |
| E2E (UI) | `cypress: test_generic_template_form_view_saves()` | Form salva com sucesso | ⚠️ Required |

---

### User Story 2: Owner/Director/Manager lista e visualiza templates genéricos (Priority: P1) 🎯 MVP

**As a** Owner, Director ou Manager de uma imobiliária
**I want to** listar os templates genéricos disponíveis na plataforma e visualizar o conteúdo completo de um deles
**So that** eu possa avaliar qual layout copiar para a minha imobiliária

> Este acesso é restrito aos mesmos papéis que já gerenciam templates CMS de company (Feature 021) — não é aberto aos demais papéis de negócio (agent, prospector, receptionist, financial, legal, property_owner, tenant/portal).

**Acceptance Criteria**:
- [ ] Given `owner`/`director`/`manager` autenticado com JWT+session+company válidos, when `GET /api/v1/cms/templates/generic`, then retorna 200 com templates ativos, paginados (default 50, max 50), sem campo `content`.
- [ ] Given `?category=landing`, when listagem, then retorna apenas templates dessa categoria.
- [ ] Given `GET /api/v1/cms/templates/generic/{id}`, when executado por `owner`/`director`/`manager`, then retorna 200 com metadados + `content` (Puck JSON) completo.
- [ ] Given papel fora de `owner`/`director`/`manager` (ex.: `agent`, `tenant`), when `GET .../generic` ou `GET .../generic/{id}`, then retorna 403 `forbidden`.
- [ ] Given template genérico desativado (`active=False`) ou inexistente, when `GET .../generic/{id}` por um papel autorizado, then retorna 404.
- [ ] Given entrada inválida (paginação não numérica), when listagem, then retorna 400 `validation_error` (ADR-018).
- [ ] Given qualquer resposta desta rota, when inspecionada, then **nunca** contém `company_id` (entidade não pertence a nenhuma company).

**Test Coverage** (per ADR-003):

| Type | Test Name | Description | Status |
|------|-----------|-------------|--------|
| Unit | `test_serialize_generic_template_excludes_content_in_list()` | Serializer de listagem não inclui `content` | ⚠️ Required |
| E2E (API) | `test_owner_director_manager_can_list_generic_templates()` | 200 para os 3 papéis autorizados | ⚠️ Required |
| E2E (API) | `test_non_management_roles_forbidden_from_list()` | 403 para papéis fora de owner/director/manager (ex.: agent) | ⚠️ Required |
| E2E (API) | `test_list_generic_templates_filters_by_category()` | Filtro `?category=` funciona | ⚠️ Required |
| E2E (API) | `test_get_generic_template_detail_includes_content()` | Detalhe retorna `content` completo para papel autorizado | ⚠️ Required |
| E2E (API) | `test_get_generic_template_detail_forbidden_for_non_management()` | 403 para papéis não autorizados no detalhe | ⚠️ Required |
| E2E (API) | `test_get_inactive_generic_template_returns_404()` | Soft-deleted não é acessível | ⚠️ Required |
| E2E (API) | `test_list_pagination_limits_at_50()` | `limit` nunca excede 50 | ⚠️ Required |

---

### User Story 3: Owner/Director/Manager copia um template genérico para a própria company (Priority: P1) 🎯 MVP

**As a** Owner, Director ou Manager
**I want to** copiar um template genérico para o catálogo de templates da minha imobiliária
**So that** eu tenha um ponto de partida pronto para criar páginas, em vez de montar tudo do zero

**Acceptance Criteria**:
- [ ] Given owner/director/manager autenticado, when `POST /api/v1/cms/templates/generic/{id}/copy`, then cria um novo `thedevkitchen.cms.template` com `company_id` da sessão atual, `category` copiada, `content` copiado, `source_generic_template_id` apontando para o genérico, retorna 201.
- [ ] Given nenhum `name` enviado no body, when copiado, then usa o `name` do genérico como padrão.
- [ ] Given `name` (padrão ou customizado) já existente na company de destino, when copiado, then aplica sufixo incremental automático (`" (2)"`, `" (3)"`, ...) até encontrar nome livre — mesmo padrão FR-014 da Feature 021 (duplicação de páginas).
- [ ] Given papel fora de `owner`/`director`/`manager` (ex.: `agent`), when tenta copiar, then retorna 403 `forbidden`.
- [ ] Given `template_id` genérico inexistente ou desativado, when copia, then retorna 404 `not_found`.
- [ ] Given `company_id` enviado no body da requisição de cópia, when processado, then é **ignorado** — o valor usado é sempre `request.env.company.id` (ADR-008).
- [ ] Given cópia realizada com sucesso, when o template genérico de origem é posteriormente desativado, then a cópia permanece intacta e utilizável.

**Test Coverage** (per ADR-003):

| Type | Test Name | Description | Status |
|------|-----------|-------------|--------|
| Unit | `test_copy_derives_company_id_from_session_not_payload()` | `company_id` do body é ignorado | ⚠️ Required |
| Unit | `test_copy_name_conflict_auto_suffix()` | Sufixo incremental em conflito de nome | ⚠️ Required |
| Unit | `test_copy_sets_source_generic_template_id()` | Rastreabilidade preenchida | ⚠️ Required |
| Unit | `test_copy_snapshot_independent_of_source_deactivation()` | Cópia sobrevive à desativação do genérico | ⚠️ Required |
| E2E (API) | `test_owner_manager_director_can_copy_generic_template()` | 201 para os 3 papéis autorizados | ⚠️ Required |
| E2E (API) | `test_non_management_roles_forbidden_from_copy()` | 403 para papéis fora de owner/director/manager | ⚠️ Required |
| E2E (API) | `test_copy_multitenancy_isolation()` | Cópia de company A não aparece em `GET /api/v1/cms/templates` de company B | ⚠️ Required |
| E2E (API) | `test_copy_inactive_or_nonexistent_generic_returns_404()` | 404 corretamente tratado | ⚠️ Required |

---

### Edge Cases

- Duas companies copiam o mesmo template genérico simultaneamente com o mesmo `name` custom → cada cópia é isolada por `company_id`, sem conflito entre companies (unique é `(name, company_id)`).
- Sufixo incremental atinge um limite extremo (ex.: 100 cópias com o mesmo nome na mesma company) → após N tentativas (ex.: 100), retorna 409 `generic_copy_conflict` em vez de loop infinito.
- Admin exclui (desativa) um template genérico já copiado por 5 companies → as 5 cópias permanecem ativas e inalteradas; apenas novas listagens/cópias deixam de exibir o genérico.
- `content` do genérico ultrapassa 512KB (ex.: editado via Odoo UI colando um JSON gigante) → constraint Python rejeita antes de salvar, mesma regra de `cms.page.content`.
- Usuário sem papel de gestão CMS (ex.: `agent`, `tenant`, `property_owner`) chama qualquer um dos 3 endpoints desta feature (list, detail, copy) → 403 em todos os casos, sem exceção para leitura.

---

## Requirements

### Functional Requirements

**FR1: Catálogo Genérico — Gestão via Odoo UI (admin-only)**
- FR1.1: O sistema DEVE fornecer o modelo `thedevkitchen.cms.template.generic`, gerenciável exclusivamente via Odoo UI (menu/views) — sem endpoints REST de create/update/delete.
- FR1.2: `ir.model.access.csv` DEVE conceder CRUD completo apenas a `base.group_system`; leitura (`perm_read=1`) pode ser concedida a `base.group_user` para consistência interna, mas escrita/exclusão NUNCA a outro grupo.
- FR1.3: O `menuitem` do catálogo genérico NÃO DEVE ter atributo `groups` — visível apenas ao `admin`, pois é o único usuário que acessa a UI do Odoo (Restrição Arquitetural do projeto).
- FR1.4: Views seguem os padrões Odoo 18.0 (KB-10): sem `attrs`, `<list>` em vez de `<tree>`, `optional="show"` para colunas de listagem.
- FR1.5: A desativação de um template genérico usa soft delete (`active=False`, ADR-015) — nunca exclusão física.

**FR2: Leitura via API (papéis de gestão CMS apenas)**
- FR2.1: `GET /api/v1/cms/templates/generic` DEVE retornar templates ativos, paginados (default `limit=50`, máximo `50`), filtráveis por `category`, ordenados por `name`.
- FR2.2: `GET /api/v1/cms/templates/generic/{id}` DEVE retornar metadados + `content` (Puck JSON) completo, para permitir preview antes da cópia.
- FR2.3: Ambos endpoints são restritos aos papéis `owner`, `director` e `manager` — exatamente o mesmo conjunto já usado em `cms_template_controller.py` (`role not in ("owner", "director", "manager")` → 403). Nenhum outro papel (agent, prospector, receptionist, financial, legal, property_owner, tenant/portal) tem acesso.
- FR2.4: Nenhuma resposta desta feature deve conter ou aceitar `company_id` para a entidade genérica (ela não pertence a nenhuma company).
- FR2.5: A listagem NUNCA inclui o campo `content` (evita payload pesado); apenas o endpoint de detalhe o inclui.

**FR3: Cópia para a Company (escrita, API)**
- FR3.1: `POST /api/v1/cms/templates/generic/{id}/copy` DEVE criar um novo registro em `thedevkitchen.cms.template` com `company_id` derivado exclusivamente da sessão autenticada (`request.env.company.id`), nunca do payload.
- FR3.2: A cópia é restrita a `owner`, `director`, `manager` — mesmo conjunto de FR2.3, reaproveitando literalmente a checagem já usada para criação de templates de company (Feature 021).
- FR3.3: O `name` do template copiado usa o `name` do genérico por padrão (ou um `name` customizado enviado no body); em caso de conflito com um template já existente na company de destino, o sistema DEVE aplicar sufixo incremental automático (`" (2)"`, `" (3)"`, ...) até encontrar um nome livre, ou retornar 409 `generic_copy_conflict` após um número máximo de tentativas (100).
- FR3.4: O template copiado DEVE registrar `source_generic_template_id` apontando para o genérico de origem, para rastreabilidade/observabilidade.
- FR3.5: A cópia é um snapshot independente — mudanças ou desativação do genérico após a cópia NUNCA afetam cópias já existentes.

**FR4: Validação e Segurança**
- FR4.1: O campo `content` (do genérico e da cópia) segue a mesma validação de JSON válido e limite de 512KB já aplicada a `cms.page.content`/`cms.template.content` (Feature 021 FR-003).
- FR4.2: `name` do template genérico é único em toda a plataforma (`_sql_constraints unique(name)`), independente de qualquer company.
- FR4.3: Nenhum endpoint desta feature usa `.sudo()` para bypass de autorização de **papel** — a checagem `role not in ("owner", "director", "manager")` permanece explícita no controller (`resolve_role()`) para os 3 endpoints; `.sudo()` é aceitável apenas para leitura de uma entidade sem isolamento de company, mesmo padrão de `cms_template_controller.py`.

### Data Model (per ADR-004, knowledge_base/09-database-best-practices.md)

**Entity: CMS Template Generic**
- **Model Name**: `thedevkitchen.cms.template.generic`
- **Table Name**: `thedevkitchen_cms_template_generic`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, auto | Chave primária |
| `name` | Char(150) | required, unique global | Nome do template genérico |
| `category` | Selection | required (`landing`, `property`, `about`) | Mesma categorização da Feature 021 |
| `active` | Boolean | default True | Soft delete (ADR-015) |
| `create_uid` | Many2one res.users | auto (Odoo default) | Admin que criou (auditoria nativa) |
| `create_date` / `write_date` | Datetime | auto | Campos de auditoria |

**Sem `company_id`** — entidade de plataforma, visível a todas as companies (sujeita ao filtro de papel do controller). **Sem `ir.rule` de isolamento** — controle de acesso apenas via `ir.model.access.csv` (FR1.2) + checagem de papel no controller (FR2.3).

**SQL Constraints**:
```python
_sql_constraints = [
    ('unique_name', 'UNIQUE(name)', 'A generic template with this name already exists.'),
]
```

**Python Constraints**:
```python
@api.constrains('category')
def _check_category(self):
    # já garantido por Selection, mas validar explicitamente se vier via API/import
    valid = dict(self._fields['category'].selection)
    for record in self:
        if record.category not in valid:
            raise ValidationError(_("Invalid category"))
```

---

**Entity: CMS Template Generic Content**
- **Model Name**: `thedevkitchen.cms.template.generic.content`
- **Table Name**: `thedevkitchen_cms_template_generic_content`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, auto | |
| `template_id` | Many2one | required, unique, `ondelete=cascade`, indexed | FK para o template genérico (1:1) |
| `content` | Text | validado (JSON + máx. 512KB) | Puck JSON |

```python
_sql_constraints = [
    ('unique_template', 'UNIQUE(template_id)', 'A generic template can have only one content record (1:1).'),
]
```

---

**Alteração em Entidade Existente: CMS Template** (`thedevkitchen.cms.template`, Feature 021)

| Field (novo) | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `source_generic_template_id` | Many2one → `thedevkitchen.cms.template.generic` | opcional, `ondelete=set null`, readonly | Rastreabilidade: de qual genérico esta cópia se originou (nulo se criado manualmente) |

**Record Rules** (per ADR-019) — **nenhuma nova necessária** para `thedevkitchen.cms.template.generic` (sem `company_id`, logo sem isolamento a fazer; controle é via `ir.model.access.csv` + checagem de papel no controller). O `thedevkitchen.cms.template` já possui suas record rules (Feature 021), inalteradas.

### API Endpoints (per ADR-007, ADR-009, ADR-011)

**Endpoint: GET /api/v1/cms/templates/generic**

| Attribute | Value |
|-----------|-------|
| **Method** | GET |
| **Path** | `/api/v1/cms/templates/generic` |
| **Authentication** | `@require_jwt` + `@require_session` + `@require_company` |
| **Authorization** | `owner`, `director`, `manager` (mesmo conjunto de `cms_template_controller.py`) |
| **Query Params** | `category` (opcional), `limit` (default 50, máx 50), `offset` (default 0) |

**Response Success (200)**:
```json
{
  "items": [
    {
      "id": 1,
      "name": "Landing Padrão",
      "category": "landing",
      "active": true,
      "created_at": "2026-09-01T10:00:00Z",
      "updated_at": "2026-09-01T10:00:00Z",
      "links": [
        {"href": "/api/v1/cms/templates/generic/1", "rel": "self", "type": "GET"},
        {"href": "/api/v1/cms/templates/generic/1/copy", "rel": "copy", "type": "POST"}
      ]
    }
  ],
  "total": 3,
  "offset": 0,
  "limit": 50
}
```

---

**Endpoint: GET /api/v1/cms/templates/generic/{id}**

| Attribute | Value |
|-----------|-------|
| **Method** | GET |
| **Authentication** | `@require_jwt` + `@require_session` + `@require_company` |
| **Authorization** | `owner`, `director`, `manager` |

**Response Success (200)**:
```json
{
  "id": 1,
  "name": "Landing Padrão",
  "category": "landing",
  "active": true,
  "content": "{...Puck JSON...}",
  "created_at": "2026-09-01T10:00:00Z",
  "updated_at": "2026-09-01T10:00:00Z",
  "links": [
    {"href": "/api/v1/cms/templates/generic/1", "rel": "self", "type": "GET"},
    {"href": "/api/v1/cms/templates/generic", "rel": "collection", "type": "GET"},
    {"href": "/api/v1/cms/templates/generic/1/copy", "rel": "copy", "type": "POST"}
  ]
}
```

---

**Endpoint: POST /api/v1/cms/templates/generic/{id}/copy**

| Attribute | Value |
|-----------|-------|
| **Method** | POST |
| **Authentication** | `@require_jwt` + `@require_session` + `@require_company` |
| **Authorization** | `owner`, `director`, `manager` |

**Request Body**:
```json
{
  "name": "string (opcional — default: nome do genérico)"
}
```

**Response Success (201)**:
```json
{
  "id": 42,
  "name": "Landing Padrão",
  "category": "landing",
  "active": true,
  "company_id": 7,
  "source_generic_template_id": 1,
  "content": "{...Puck JSON copiado...}",
  "created_at": "2026-09-06T12:00:00Z",
  "updated_at": "2026-09-06T12:00:00Z",
  "links": [
    {"href": "/api/v1/cms/templates/42", "rel": "self", "type": "GET"},
    {"href": "/api/v1/cms/templates/42", "rel": "update", "type": "PUT"},
    {"href": "/api/v1/cms/templates", "rel": "collection", "type": "GET"}
  ]
}
```

**Error Responses** (todos os endpoints desta feature):

| Code | Condition | Response |
|------|-----------|----------|
| 400 | Erro de validação de paginação/JSON (ADR-018) | `{"error": "validation_error", "detail": "..."}` |
| 401 | JWT/sessão ausente ou inválida (ADR-011) | `{"error": "unauthorized"}` |
| 403 | Papel fora de owner/director/manager (em list, detail OU copy) | `{"error": "forbidden", "detail": "Insufficient permissions"}` |
| 404 | Template genérico inexistente ou inativo | `{"error": "not_found", "detail": "Generic template N not found"}` |
| 409 | Conflito de nome esgotado após 100 tentativas de sufixo (apenas copy) | `{"error": "generic_copy_conflict", "field": "name"}` |

### Seed Data (OBRIGATÓRIO — todos os solution types)

```python
# Companies (isolamento multi-tenant)
company_a = env['res.company'].create({'name': 'Imobiliária A (Seed)'})
company_b = env['res.company'].create({'name': 'Imobiliária B (Seed)'})

# Admin (gestor do catálogo genérico) — usuário admin do sistema já existe por padrão
# (não criar novo usuário; reutilizar base.group_system existente no ambiente de teste)

# Usuários — apenas os papéis relevantes para esta feature:
# 3 papéis autorizados (owner/director/manager) + 1 papel NÃO autorizado (agent, para testar 403)
# + 1 owner de company B (isolamento da cópia)
users = {
    'owner':      {'login': 'seed_owner_gt@test.com',      'company': company_a},
    'director':   {'login': 'seed_director_gt@test.com',   'company': company_a},
    'manager':    {'login': 'seed_manager_gt@test.com',    'company': company_a},
    'agent':      {'login': 'seed_agent_gt@test.com',      'company': company_a},  # 403 esperado
    'owner_b':    {'login': 'seed_owner_b_gt@test.com',    'company': company_b},  # isolamento da cópia
}

# Templates genéricos (catálogo de plataforma, sem company_id)
generic_landing = env['thedevkitchen.cms.template.generic'].create({
    'name': 'seed_generic_landing', 'category': 'landing',
})
env['thedevkitchen.cms.template.generic.content'].create({
    'template_id': generic_landing.id, 'content': '{"content": []}',
})

generic_property = env['thedevkitchen.cms.template.generic'].create({
    'name': 'seed_generic_property', 'category': 'property',
})
env['thedevkitchen.cms.template.generic.content'].create({
    'template_id': generic_property.id, 'content': '{"content": []}',
})

generic_inactive = env['thedevkitchen.cms.template.generic'].create({
    'name': 'seed_generic_inactive', 'category': 'about', 'active': False,
})  # cobre teste de 404 em item desativado
```

> ⚠️ Cobrir: `owner`/`director`/`manager` de company A para testar list/detail/copy com sucesso; `agent` de company A para testar 403 em todos os 3 endpoints; `owner_b` de company B para testar isolamento da cópia resultante; 1 template genérico ativo por categoria relevante + 1 inativo (testar 404 e filtro).

---

### Non-Functional Requirements

**NFR1: Security** (per ADR-008, ADR-011, ADR-017, ADR-019, ADR-029)
- Todos os endpoints exigem autenticação tripla (`@require_jwt` + `@require_session` + `@require_company`).
- `company_id` da cópia é sempre derivado da sessão, nunca do payload (ADR-008).
- Nenhum endpoint REST desta feature aceita `base.group_system` (ADR-029 — reforçado, não modificado).
- RBAC explícito via `resolve_role()` no controller, idêntico ao usado em `cms_template_controller.py`, aplicado uniformemente aos 3 endpoints (list, detail, copy) — `owner`/`director`/`manager`.

**NFR2: Performance** (per `knowledge_base/performance.md`)
- **Volume esperado**: catálogo genérico é curado manualmente pelo admin — cardinalidade baixa (dezenas, não milhares de registros). Não justifica paginação agressiva além do padrão de 50/página já usado em `cms_template_controller.py`.
- **Índices**: `category` (usado em filtro de listagem) DEVE ter `index=True`; `name` já é indexado implicitamente pela constraint `UNIQUE`.
- **Risco de N+1**: o campo `content` (relação 1:1 com `thedevkitchen.cms.template.generic.content`) só é acessado no endpoint de **detalhe** (`GET .../generic/{id}`, um único registro — sem N+1 possível). A **listagem** explicitamente NUNCA acessa `content_ids`, evitando 1 query extra por item da página — mesmo padrão já usado em `_serialize_template(include_content=False)`.
- **Cache Redis (cache-aside)**: candidato a cache. Embora o público leitor agora seja restrito a `owner`/`director`/`manager` (não mais os 10 papéis), o catálogo ainda é lido por gestores de **todas as companies da plataforma** e escrito apenas pelo admin, com baixíssima frequência de mutação. Proposta: cachear `GET /api/v1/cms/templates/generic` (por `category` como parte da chave: `cms:generic_templates:list:{category or "all"}`) com TTL de 300s, invalidado nos hooks `create()`/`write()`/`unlink()` de `thedevkitchen.cms.template.generic` e `.content` (mesmo padrão de invalidação por write-hook já usado em `APISession.write()`, Feature 023).
- **Offload assíncrono/Celery**: não se aplica — não há operação lenta nesta feature (sem upload de mídia, sem processamento em lote); a ação de cópia é uma escrita única e rápida, adequada para execução síncrona.
- Tempo de resposta da API: < 200ms para listagem/detalhe (mesmo padrão do resto da plataforma).

**NFR3: Quality** (per ADR-022)
- Código deve passar em: black, isort, flake8.
- Nota do Pylint ≥ 8.0/10.
- 100% de cobertura de testes em validações (ADR-003).
- Zero erros de console JavaScript no menu/views do admin.

**NFR4: Data Integrity** (per knowledge_base/09-database-best-practices.md)
- Modelo normalizado (conteúdo em tabela separada, mesmo padrão da Feature 021, evitando payload pesado em listagens).
- FK `template_id` com `ondelete=cascade` (content é sempre subordinado ao template genérico).
- FK `source_generic_template_id` com `ondelete=set null` (excluir/desativar o genérico nunca quebra a cópia já existente).
- Soft delete via `active` (ADR-015).

**NFR5: Frontend Compatibility** (per knowledge_base/10-frontend-views-odoo18.md)
- Views seguem padrões Odoo 18.0: sem `attrs`, `<list>` em vez de `<tree>`.
- Visibilidade de coluna via `optional="show|hide"`.
- Sem `column_invisible` com expressões Python.
- Menu SEM atributo `groups`.

---

## Technical Constraints

### Must Follow (from ADRs & Knowledge Base)

| Source | Requirement | Applied To |
|--------|-------------|------------|
| ADR-001 | Padrões de view Odoo 18.0 (sem `attrs`, usar `<list>`) | Views do catálogo genérico |
| ADR-001 | Menus SEM atributo `groups` | `menuitem` do catálogo genérico |
| Arch. Restriction | Apenas `admin` acessa a UI do Odoo | Gestão do catálogo genérico (US1) |
| ADR-003 | 100% cobertura de testes em validações | Constraints de `cms.template.generic` |
| ADR-004 | Prefixo `thedevkitchen_` | `thedevkitchen.cms.template.generic`, tabela `thedevkitchen_cms_template_generic` |
| ADR-007 | HATEOAS em todas as respostas | Endpoints de listagem/detalhe/cópia |
| ADR-008 | `company_id` nunca do payload | Endpoint de cópia |
| ADR-011 | Decorators de autenticação tripla | Todos os 3 endpoints REST |
| ADR-015 | Soft delete | Desativação do template genérico |
| ADR-018 | Validação de schema | `content` JSON, paginação |
| ADR-019 | RBAC explícito, papéis idênticos a `cms_template_controller.py` | list, detail e copy restritos a owner/director/manager |
| ADR-029 | Admin bloqueado da REST API | Nenhum endpoint REST de gestão do genérico |
| KB-10 | `optional` para colunas | List view do catálogo genérico |

### Architecture Patterns
- **Controller Pattern**: novo arquivo `cms_template_generic_controller.py` (mesmo módulo `thedevkitchen_cms`, seguindo convenção `{entity}_api.py`/`{entity}_controller.py` já usada em `cms_template_controller.py`).
- **Testing Pattern**: conforme `.github/instructions/test-strategy.instructions.md`.

---

## Success Criteria

### Backend
- [ ] User Stories 1–3 implementadas e testadas.
- [ ] 100% cobertura de testes unitários em validações (ADR-003).
- [ ] Testes E2E de API para os 3 endpoints, cobrindo owner/director/manager (sucesso) e ao menos 1 papel não autorizado (403) em cada um.
- [ ] Isolamento multi-empresa da cópia resultante verificado.
- [ ] Pylint ≥ 8.0, linters passando (ADR-022).
- [ ] Nenhum endpoint REST de gestão do catálogo genérico existe (verificado por ausência no OpenAPI/Postman).

### Frontend (Odoo UI, admin)
- [ ] Views seguem padrões Odoo 18.0 (KB-10).
- [ ] Menu SEM atributo `groups`.
- [ ] Teste E2E Cypress do menu/list/form do catálogo genérico.
- [ ] Zero erros de console JavaScript.
- [ ] Visibilidade de coluna via `optional`.

### Seeds
- [ ] Seed cobre owner/director/manager + 1 papel não autorizado (agent) + 2 companies + templates genéricos (ativo x2 categorias + 1 inativo).
- [ ] Seed idempotente, prefixo `seed_`.

### Documentation
- [ ] Swagger/OpenAPI gerado via skill `swagger-updater` (ADR-005).
- [ ] Fluxogramas de jornada em `specs/028-cms-generic-templates/flowcharts.md` (1 por user story).

---

## Constitution Feedback

### New Patterns Introduced

| Pattern | Description | Constitution Section | Priority |
|---------|-------------|---------------------|----------|
| Platform-Level Non-Tenant Catalog Entity | Entidade sem `company_id`, gerenciada só via Odoo UI pelo admin, lida por papéis de gestão CMS de qualquer company via API, sem `ir.rule` de isolamento (porque não há dimensão de company a isolar) | Architectural Patterns | Medium |
| Curated-Copy-Into-Tenant Pattern | Ação de API que lê de uma entidade de plataforma e "materializa" uma cópia isolada por company, com campo de rastreabilidade (`source_*_id`) mas sem sincronização futura | Architectural Patterns | Medium |
| Role-Set Reuse Across Sibling Controllers | Reaproveitar literalmente a mesma tupla de papéis (`("owner", "director", "manager")`) de um controller já existente para um controller novo que atua sobre uma entidade relacionada, em vez de redigitar a lista — reduz risco de drift de autorização entre entidades irmãs (genérico vs. company-scoped) | Security Requirements | Low |

### New Entities/Relationships

| Entity | Related To | Relationship Type | Notes |
|--------|-----------|-------------------|-------|
| `thedevkitchen.cms.template.generic` | `thedevkitchen.cms.template.generic.content` | 1:1 | Mesmo padrão de `cms.template`/`cms.template.content` |
| `thedevkitchen.cms.template.generic` | `thedevkitchen.cms.template` (via `source_generic_template_id`) | 1:N (um genérico pode originar N cópias, cada uma em uma company diferente) | Rastreabilidade, sem sincronização |

### Architectural Decisions

| Decision | Rationale | ADR Required? |
|----------|-----------|---------------|
| CRUD do catálogo genérico é exclusivamente Odoo UI, sem endpoints REST | Consequência direta de ADR-029 (admin bloqueado de REST) aplicada a um novo domínio | No — já coberto por ADR-029, apenas um novo caso de aplicação |
| Entidade sem `company_id` não precisa de `ir.rule` de isolamento | Não há dimensão de company para isolar; controle de acesso via `ir.model.access.csv` + checagem de papel no controller | No |
| Leitura do catálogo genérico restrita a owner/director/manager, não aberta a todos os papéis | Alinhamento com o princípio de menor privilégio já aplicado a `thedevkitchen.cms.template` — evita expor um catálogo de gestão de conteúdo a papéis (agent, portal, etc.) que não gerenciam CMS hoje | No |

### Constitution Update Recommendation

- **Update Required**: Yes
- **Suggested Version Bump**: MINOR (novo padrão arquitetural, sem quebra de princípios existentes)
- **Sections to Update**:
  - [x] Architectural Patterns (novo: "Platform-Level Non-Tenant Catalog + Curated-Copy-Into-Tenant Pattern")
  - [x] Reference Implementations (nova entrada Feature 028, após aprovação/implementação)

---

## Assumptions & Dependencies

**Assumptions**:
- O ambiente de teste possui um usuário `admin` (`base.group_system`) já provisionado — não é criado via seed API (seeds de API não podem criar admin, pois ele não é gerenciado por invite/API, conforme ADR-029 FR-007).
- `resolve_role()` (já usado em `cms_template_controller.py`) continua sendo o mecanismo de checagem de papel para os 3 endpoints desta feature — sem integração com a RBAC Capabilities API (Feature 020) nesta iteração, seguindo o precedente já existente no mesmo controller family.
- O limite de 512KB para `content` é reaproveitado tal qual definido na Feature 021 (não há motivo de negócio para um limite diferente em templates genéricos).

**Dependencies**:
- Módulo existente: `thedevkitchen_cms` (Feature 021) — esta feature estende o módulo, não cria um novo.
- `thedevkitchen_apigateway` — `@require_jwt`, `@require_session`, `@require_company`.
- `quicksol_estate` — `role_resolver.resolve_role()`.

---

## Implementation Phases

### Phase 1: Foundation
- Modelos `thedevkitchen.cms.template.generic` + `.content`, constraints, soft delete.
- Campo `source_generic_template_id` em `thedevkitchen.cms.template`.
- `ir.model.access.csv` (admin full CRUD; leitura interna opcional).
- Testes unitários de validação.

### Phase 2: API Layer
- Controller `cms_template_generic_controller.py`: `GET` list, `GET` detail, `POST .../copy` — todos com checagem `role not in ("owner", "director", "manager")`.
- Lógica de sufixo incremental de nome na cópia.
- Testes E2E de API (owner/director/manager autorizados, 1 papel não autorizado para 403, multi-tenancy).

### Phase 3: Odoo UI (admin)
- Views (`list`, `form`) + menu (sem `groups`) para o catálogo genérico.
- Testes Cypress + validação manual no navegador (zero erros de console).

### Phase 4: Documentation & Artifacts
- Atualização da constituição (novo padrão).
- Swagger/OpenAPI (skill `swagger-updater`).
- Coleção Postman (skill `postman-collection-manager`).
- Fluxogramas de jornada (`flowcharts.md`).

---

## Validation Checklist

### Backend Validation
- [x] Seção "Out of Scope / Non-Goals" preenchida com itens específicos da feature.
- [x] Todos os requisitos de ADR referenciados e seguidos (ADR-029 é o eixo central desta spec).
- [x] Multi-tenancy corretamente especificado (ADR-008) — inclusive a ausência deliberada de isolamento na entidade genérica.
- [x] Segurança adequadamente definida (ADR-011, ADR-019, ADR-029) — autorização unificada owner/director/manager nos 3 endpoints.
- [x] Estratégia de teste completa — unit + E2E API.
- [x] API segue padrões REST + HATEOAS (ADR-007).
- [x] Design de banco normalizado — conteúdo em tabela separada (3FN).
- [x] Tratamento de erros especificado (ADR-018).

### Frontend Validation
- [x] Views seguem padrões Odoo 18.0 (KB-10, ADR-001).
- [x] Sem `attrs`; `<list>` em vez de `<tree>`.
- [x] `optional="show|hide"` para colunas.
- [x] Sem `column_invisible` com expressões Python.
- [x] Menu SEM atributo `groups`.
- [x] Testes E2E Cypress especificados.
