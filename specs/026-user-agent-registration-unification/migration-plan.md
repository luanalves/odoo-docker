# Plano de Migração entre Endpoints — Feature 026

**Feature**: `026-user-agent-registration-unification`
**Criado em**: 2026-07-25
**Baseado em**: [`spec-idea.md`](./spec-idea.md) (requisitos, critérios de aceitação, correções de design datadas) e [`design-idea.md`](./design-idea.md) (arquitetura)
**Status**: ✅ **Concluído** — as duas migrações abaixo já estão em produção neste branch (`POST /api/v1/agents` removido, `agent` node fora do invite). Este documento existe para orientar qualquer time consumidor (frontend, scripts, integrações externas) que ainda tenha código apontando para o comportamento antigo.
**Janela de descontinuação**: Nenhuma — por decisão explícita do solicitante (ver `spec-idea.md`, User Story 3), a remoção foi direta, sem fase de `deprecated: true`/header `Sunset`.

---

## Resumo em uma frase

O cadastro de um agente deixou de ser um endpoint isolado (`POST /api/v1/agents`) e o convite deixou de carregar dados de agente (`agent` node em `POST /api/v1/users/invite`) — hoje **todo** o registro de qualquer perfil (agente ou não) passa por `POST /api/v1/profiles`, e o convite (`POST /api/v1/users/invite`) só recebe `profile_id` + `session_id`, para qualquer `profile_type`.

---

## Migração 1: Criar um Agente

### Antes (removido — `fef7436`, User Story 3)

```http
POST /api/v1/agents
Authorization: Bearer {access_token}

{
  "name": "João Silva",
  "cpf": "123.456.789-09",
  "email": "joao@example.com",
  "phone": "+5511999998888",
  "mobile": "+5511988887777",
  "creci": "CRECI-SP 12345",
  "bank_name": "Banco do Brasil",
  "bank_account": "12345-6",
  "pix_key": "joao@example.com",
  "company_id": 5,
  "hire_date": "2024-01-01",
  "session_id": "{{session_id}}"
}
```

Esse endpoint criava **apenas** um registro `real.estate.agent` — sem `res.users`, sem `thedevkitchen.estate.profile`, sem login. Chamar essa rota hoje retorna **404** (rota não existe mais).

### Depois

```http
POST /api/v1/profiles
Authorization: Bearer {access_token}

{
  "name": "João Silva",
  "company_id": 5,
  "document": "123.456.789-09",
  "email": "joao@example.com",
  "phone": "+5511999998888",
  "mobile": "+5511988887777",
  "birthdate": "1990-01-01",
  "profile_type_id": 4,
  "creci": "CRECI-SP 12345",
  "bank_name": "Banco do Brasil",
  "bank_account": "12345-6",
  "pix_key": "joao@example.com",
  "session_id": "{{session_id}}"
}
```

`profile_type_id=4` (`code='agent'`, confirme o id atual via `GET /api/v1/profile-types`) faz `profile_api.py::create_profile` **auto-criar** o `real.estate.agent` na mesma transação — já nasce completo, só falta `user_id` (que vem do convite). Resposta inclui `agent_id` e `_links.agent`.

### Mapeamento de campos

| Campo em `POST /api/v1/agents` (removido) | Campo equivalente em `POST /api/v1/profiles` | Observação |
|---|---|---|
| `name` | `name` | sem mudança |
| `cpf` | `document` | mesmo formato/validação (CPF/CNPJ) |
| `email` | `email` | sem mudança |
| `phone` | `phone` | sem mudança |
| `mobile` | `mobile` | sem mudança |
| `creci` | `creci` | **agora só é validado quando `profile_type_id` resolve para `agent`** — ver nota abaixo |
| `bank_name` | `bank_name` | idem |
| `bank_account` | `bank_account` | idem |
| `pix_key` | `pix_key` | idem |
| `company_id` | `company_id` | sem mudança |
| `hire_date` | `hire_date` | opcional; default `today()` se omitido |
| — (não existia) | `birthdate` | **novo campo obrigatório** — vem do modelo unificado de perfil (Feature 010), não existia em `real.estate.agent` |
| — (não existia) | `profile_type_id` | **novo campo obrigatório** — define que este perfil é do tipo `agent` (id=4) em vez de qualquer outro tipo |

**Nota sobre validação condicional (correção 2026-07-23)**: `creci`/`bank_name`/`bank_account`/`pix_key` só são validados quando `profile_type_id` resolve para `agent` — enviá-los (mesmo malformados) em um perfil de outro tipo (`tenant`, `owner`, etc.) não causa erro, o valor é simplesmente ignorado. Detalhes em `spec-idea.md`, seção "Correção de Design: Validação de Campos de Agente Passa a Ser Condicional a `profile_type`".

---

## Migração 2: Convidar um Agente

### Antes (nunca chegou a ficar assim em produção — versão intermediária corrigida em 2026-07-23, ver `spec-idea.md`)

```http
POST /api/v1/users/invite
Authorization: Bearer {access_token}

{
  "profile_id": 1069,
  "agent": {
    "creci": "CRECI-SP 12345",
    "bank_name": "Banco do Brasil",
    "bank_account": "12345-6",
    "pix_key": "joao@example.com"
  },
  "session_id": "{{session_id}}"
}
```

### Depois

```http
POST /api/v1/users/invite
Authorization: Bearer {access_token}

{
  "profile_id": 1069,
  "session_id": "{{session_id}}"
}
```

Sem exceção por `profile_type` — **todo** convite usa esse corpo mínimo. Para um perfil `agent`, o único efeito colateral do convite é vincular o `user_id` recém-criado ao `real.estate.agent` que `POST /api/v1/profiles` já auto-criou (upsert por `profile_id`); nenhum campo de creci/banco é lido, validado ou escrito aqui.

### Consequência para conflito de CRECI duplicado

| | Antes (endpoint removido) | Depois |
|---|---|---|
| Onde o `409` de CRECI duplicado é detectado | No convite (`POST /api/v1/users/invite`) | No cadastro do perfil (`POST /api/v1/profiles`) — mais cedo no fluxo |

---

## Fluxo completo, lado a lado

| Passo | Antes | Depois |
|---|---|---|
| 1. Criar registro base | `POST /api/v1/agents` (sem login) | `POST /api/v1/profiles` (`profile_type_id=agent`, com `creci`/campos de banco) |
| 2. Conceder login | `POST /api/v1/users/invite` com `agent: {...}` completo | `POST /api/v1/users/invite` com só `profile_id` |
| 3. Resultado | `real.estate.agent` + `res.users`, mas sem `thedevkitchen.estate.profile` | `thedevkitchen.estate.profile` + `real.estate.agent` (auto-criado) + `res.users`, os três vinculados |

---

## Checklist para times consumidores

- [ ] Qualquer chamada a `POST /api/v1/agents` deve ser substituída por `POST /api/v1/profiles` com `profile_type_id` do tipo `agent` — chamar a rota antiga hoje retorna `404`.
- [ ] Remover qualquer objeto `agent` do corpo de `POST /api/v1/users/invite` — se enviado, é simplesmente ignorado (não é mais lido pelo controller), então não quebra, mas também não tem efeito.
- [ ] Tratar o `409` de CRECI duplicado como possível resposta de `POST /api/v1/profiles`, não mais de `POST /api/v1/users/invite`.
- [ ] Confirmar `profile_type_id` correto via `GET /api/v1/profile-types` antes de montar o payload — os ids não são garantidos estáveis entre ambientes.
- [ ] Endpoints de leitura/atualização de agente (`GET /api/v1/agents`, `GET/PUT /api/v1/agents/{id}`, `.../deactivate`, `.../reactivate`, `.../properties`, `.../commission-rules`, `.../performance`, `/api/v1/agents/ranking`) **não foram afetados** — continuam funcionando exatamente como antes.

---

## Referências

- `spec-idea.md` — User Story 1 (fluxo unificado), User Story 3 (remoção de `POST /api/v1/agents`), seções "Correção de Design" (2026-07-23, duas correções)
- `design-idea.md` — arquitetura original do fluxo de convite
- Commits: `fef7436` (remoção de `POST /api/v1/agents`), `689a093` (mover campos de agente do invite para o profile), `9e6e320` (validação condicional por `profile_type`)
- `docs/postman/quicksol_api_v1.42_postman_collection.json` — collection atualizada refletindo ambos os fluxos
- `docs/openapi/009-user-onboarding.yaml` + Swagger dinâmico (`/api/v1/openapi.json`) — documentação viva dos dois endpoints
