# Design: Unificar Cadastro de Usuários com Onboarding de Corretores/Agentes

**Feature**: `026-user-agent-registration-unification`
**Criado em**: 2026-07-18
**Baseado em**: [`spec-idea.md`](./spec-idea.md) (fonte de verdade para requisitos funcionais/não-funcionais, critérios de aceitação e cobertura de testes completa — este documento foca em COMO implementar, não repete o QUÊ/POR QUÊ já especificado lá)
**Status**: Rascunho, aguardando revisão do usuário

---

## Contexto em uma frase

`POST /api/v1/users/invite` ganha um objeto `agent` opcional com paridade total de campos com `AGENT_CREATE_SCHEMA` (menos `company_id`/`user_id`, sempre derivados no servidor), passa a criar `real.estate.agent` vinculado tanto a `profile_id` quanto a `user_id` na mesma transação do convite, e `POST /api/v1/agents` é removida diretamente (sem janela de descontinuação) assim que isso estiver validado.

---

## Arquitetura

Nenhum componente novo de infraestrutura, fila ou serviço é introduzido — esta é uma mudança de orquestração dentro de um controller já existente (`invite_controller.py::invite_user`), mais uma migração de schema de um campo (índice) em um model já existente (`real.estate.agent`).

```
Cliente (frontend headless)
    │  POST /api/v1/users/invite { profile_id, agent?: {...} }
    ▼
invite_controller.py::invite_user
    │  1. Carrega profile_record (já existente, Feature 010 — inalterado)
    │  2. Se profile_type == 'agent': valida agent_payload contra AGENT_INVITE_SCHEMA
    │  3. InviteService.create_user_from_profile(...)  (já existente — inalterado)
    │  4. UPSERT (achado 2026-07-19, ver "Correção de Design" abaixo):
    │     search real.estate.agent por profile_id
    │       ├─ existe (caso normal — profile_api.py já o auto-criou, sem user_id)
    │       │    └─ write({user_id, **agent_payload filtrado})
    │       └─ não existe (caso defensivo/legado)
    │            └─ create({profile_id, user_id, **agent_payload filtrado})
    │                └─ agent.py::create() (JÁ EXISTENTE) faz vals.setdefault(...) a
    │                   partir do profile_record — só este ramo depende do fallback
    │  5. Token de convite + e-mail (já existente — inalterado, best-effort)
    ▼
Resposta 201 { id, profile_id, agent_id, ... }
```

**Correção de Design (achado durante a implementação, 2026-07-19)**: `profile_api.py` (`POST /api/v1/profiles`, Feature 010, não faz parte desta feature) já cria automaticamente um `real.estate.agent` (sem `user_id`) sempre que o perfil é do tipo `agent`. Um `create()` cego no passo 4 colidiria com esse registro já existente na restrição `UNIQUE(cpf, company_id)`, vazando um `psycopg2.errors.UniqueViolation` não capturado como 500 — depois que `res.users`/token já teriam sido criados, violando a atomicidade. A correção (confirmada com o usuário) é a semântica de upsert acima: `search` antes de decidir entre `write()`/`create()`. Ver `spec-idea.md`, seção "Achado de Implementação", para o histórico completo.

`POST /api/v1/agents` (`agent_api.py::create_agent`) não é tocado por este fluxo — permanece funcionando exatamente como hoje até ser excluído por completo na Fase 5 da implementação.

---

## Componentes

| Componente | Tipo de mudança | Responsabilidade |
|---|---|---|
| `quicksol_estate/controllers/utils/schema.py::AGENT_INVITE_SCHEMA` | Novo | Valida o objeto `agent` opcional do corpo da requisição. Reaproveita por referência (`AGENT_CREATE_SCHEMA["types"]`/`["constraints"]`) as mesmas funções de restrição de `create_agent` — não duplica as lambdas. Marca `name`/`cpf`/`email`/`phone`/`mobile`/`creci`/`hire_date`/`bank_name`/`bank_account`/`pix_key` como opcionais; `company_id`/`user_id` **fora** do conjunto de chaves aceitas. |
| `thedevkitchen_user_onboarding/controllers/invite_controller.py::invite_user` | Modificado | Ramifica em `profile_type == 'agent'`; valida `agent_payload` contra `AGENT_INVITE_SCHEMA`; filtra `company_id`/`user_id` de qualquer payload recebido (`allowed_keys`); **busca** (`search`) um `real.estate.agent` existente por `profile_id` — se achar, `write({user_id, **filtrado})`; se não, `create({profile_id, user_id, **filtrado})` (semântica de upsert, achado 2026-07-19: `profile_api.py` já auto-cria o registro sem `user_id`). Não reimplementa fallback de campos (só entra em jogo no ramo `create()`). |
| `quicksol_estate/models/agent.py::create()` | **Inalterado** | Mecanismo de reaproveitamento de campos (`vals.setdefault(...)` a partir de `profile_id`) já existe (linhas 436-470) — nenhuma mudança de código aqui, apenas dependência confirmada. |
| `quicksol_estate/models/agent.py::user_id` | Modificado (schema) | Ganha `index=True`. Sem migração de dados; Odoo cria o índice na atualização do módulo. |
| `quicksol_estate/controllers/agent_api.py::create_agent` | Excluído (Fase 5, não nesta primeira entrega de código) | Rota, método e registro `thedevkitchen.api.endpoint` removidos por completo quando as pré-condições da User Story 3 forem satisfeitas. |
| Testes unitários/E2E (`quicksol_estate`/`thedevkitchen_user_onboarding`) | Novos + existentes preservados | Ver seção Testes abaixo e a tabela completa em `spec-idea.md`. |
| OpenAPI/Postman | Regenerados (skills `swagger-updater`/`postman-collection-manager`) | Duas passagens: (1) documentar o novo `agent` node; (2) confirmar ausência de `POST /api/v1/agents` pós-remoção. |

---

## Fluxo de Dados (detalhado)

```python
# invite_controller.py::invite_user — esboço corrigido (upsert, achado 2026-07-19)
agent_payload = data.get("agent")
if profile_type == "agent":
    if agent_payload:
        is_valid, errors = SchemaValidator.validate_agent_invite(agent_payload)
        if not is_valid:
            return self._error_response(400, "validation_error", ", ".join(errors))
    # ... cria o usuário (já existente, InviteService.create_user_from_profile) ...
    allowed_keys = {
        "name", "cpf", "email", "phone", "mobile",
        "creci", "hire_date", "bank_name", "bank_account", "pix_key",
    }
    explicit_fields = {
        k: v for k, v in (agent_payload or {}).items()
        if k in allowed_keys and v is not None
    }
    Agent = request.env["real.estate.agent"].sudo()
    existing_agent = Agent.search([("profile_id", "=", profile_record.id)], limit=1)
    if existing_agent:
        existing_agent.write({"user_id": user.id, **explicit_fields})
        agent = existing_agent
    else:
        agent = Agent.create({
            "profile_id": profile_record.id,
            "user_id": user.id,
            **explicit_fields,
        })
```

**Pontos de decisão de design já resolvidos** (com o "porquê", para quem for implementar):

1. **Por que buscar antes de escrever, em vez de só `create()`?** Porque `profile_api.py` (Feature 010, `POST /api/v1/profiles`) já cria automaticamente um `real.estate.agent` sem `user_id` quando o perfil é do tipo `agent` — achado confirmado ao vivo (`odoo shell`) durante a implementação da Task 4. Um `create()` cego colide com esse registro na restrição `UNIQUE(cpf, company_id)`, vazando um erro não tratado (`UniqueViolation`, não `ValidationError`) como 500 depois que `res.users`/token já existiriam — quebrando a atomicidade que esta spec exige.
2. **Por que o controller não reescreve o fallback de campos?** Porque `real.estate.agent.create()` já faz isso (verificado no código, `agent.py:436-470`) — mas isso só é relevante no ramo `create()` (defensivo); no ramo `write()` (caso normal), os campos de identidade já foram preenchidos por `profile_api.py` no momento da criação do perfil, então `write()` só precisa aplicar `user_id` + eventuais overrides explícitos.
3. **Por que `company_id`/`user_id` são filtrados no controller, e não simplesmente omitidos do schema?** Porque `AGENT_INVITE_SCHEMA["types"]`/`["constraints"]` são reaproveitados por referência do `AGENT_CREATE_SCHEMA` completo (que inclui `company_id`) — o filtro `allowed_keys` no controller é a barreira real que impede esses dois campos de chegar a `explicit_fields`, independente do que o schema de tipos contenha.
4. **Por que a ordem `profile_id` antes de `user_id` importa no ramo `create()` (defensivo)?** Porque `agent.py::create()` processa o bloco de `profile_id` antes do de `user_id`, e o primeiro já preenche `company_id` via `setdefault()` — isso é o que garante, na prática, que `company_id` sempre reflita a empresa do perfil, nunca a do usuário logado, quando os dois são passados juntos. No ramo `write()` (caso normal), `company_id` já está correto no registro existente e não é tocado.

---

## Modelo de Dados

Nenhuma entidade nova. Uma única mudança de schema:

```python
# real.estate.agent (agent.py) — campo existente, ganha index=True
user_id = fields.Many2one(
    "res.users", "Related User", ondelete="restrict", index=True, help="..."
)
```

Sem migração de dados (tabela pequena, dezenas a centenas de linhas por empresa — criação de índice quase instantânea). Justificativa de performance completa em `spec-idea.md` (NFR2).

---

## Contrato de API (resumo — ver `spec-idea.md` para o contrato completo)

**`POST /api/v1/users/invite`** — request body ganha `agent` opcional (10 campos, paridade com `AGENT_CREATE_SCHEMA` menos `company_id`/`user_id`); response 201 ganha `agent_id` + link `agent`.

**`POST /api/v1/agents`** — inalterado até ser removido (404 depois).

---

## Tratamento de Erros

| Código | Quando | Observação de design |
|---|---|---|
| 400 `validation_error` | Campo do `agent` falha validação | Mesma função de restrição de `create_agent` (reaproveitada por referência) |
| 403 `forbidden` | Fora da matriz ADR-024 | Inalterado — matriz de autorização já existente |
| 404 `not_found` | `profile_id` inexistente | Comportamento já existente, inalterado |
| 409 `conflict` | CRECI duplicado OU `user_id` já vinculado a outro agente | `_check_creci_format`/`_check_user_unique`, ambas já existentes |
| 500 `internal_error` | Erro inesperado | Catch-all já existente |
| *(fora de escopo)* 400 acidental para perfil de empresa diferente | Ver "Achado de Segurança Registrado" em `spec-idea.md` — comportamento atual preservado, não corrigido nesta feature (candidato à spec 027) |

Toda falha de validação/constraint no passo 4 (criação do `real.estate.agent`) reverte a transação inteira — nenhum `res.users` parcial fica commitado.

---

## Estratégia de Testes

Ver a tabela completa (19 casos de teste em 3 user stories) em `spec-idea.md`. Resumo por categoria:

- **Unitário**: validação de schema campo a campo (incluindo os 5 campos "novos" de paridade total: `name`/`cpf`/`email`/`phone`/`mobile`), fallback vs. override de campo repetido, filtragem de `company_id`/`user_id`, unicidade de CRECI/`user_id`, ordem de precedência `profile_id`→`company_id`.
- **E2E (API)**: fluxo feliz completo (perfil → convite → usuário+agente+token), os dois testes que fecham a lacuna que a Feature 025 deixou aberta (`test_invited_agent_sees_own_properties`/`leads` — provam que o RBAC realmente reconhece o agente convidado), rollback atômico, isolamento multi-empresa (documentando o comportamento atual, não corrigindo-o), autorização.
- **Integração**: OpenAPI/Postman regenerados corretamente nas duas passagens (com o `agent` node, e depois sem `POST /api/v1/agents`).

Dados de seed com prefixo `seed_`, cobrindo duas empresas e os papéis owner/manager/agent, definidos em `spec-idea.md`.

---

## Fora de Escopo (lembrete)

- Tornar `profile_id` opcional / criar perfil inline a partir do nó `agent` — considerado e descartado explicitamente.
- Corrigir a checagem de `company_id` ausente em `invite_user` (achado de segurança acidental) — registrado, fora de escopo, candidato a `specs/027-...`.
- Qualquer mudança em `tenant`/`property_owner` ou nos demais `profile_type`.
- UI/Cypress (feature é 100% API).

---

## Fases de Implementação (mapeamento para `writing-plans`)

1. **Fundação** — índice + `AGENT_INVITE_SCHEMA` (reaproveitando `AGENT_CREATE_SCHEMA`) + testes de schema.
2. **Camada de API** — `invite_controller.py::invite_user` modificado; `create_agent` intocado.
3. **Testes & Qualidade** — cobertura completa unitária/E2E, lint.
4. **Documentação** — OpenAPI/Postman (passagem 1), fluxogramas, feedback de constituição.
5. **Remoção de `POST /api/v1/agents`** — após pré-condições da User Story 3, exclusão direta + OpenAPI/Postman (passagem 2). Merge em `develop` só com autorização explícita do usuário.

Detalhamento tarefa-a-tarefa fica para o `plan-idea.md` (via `superpowers:writing-plans`).
