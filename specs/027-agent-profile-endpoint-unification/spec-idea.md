# Especificação de Feature: Unificação dos Endpoints de List/Get/Update/Reactivate de Agent em Profiles

**Branch da Feature**: `027-agent-profile-endpoint-unification`
**Criado em**: 2026-07-27
**Status**: Rascunho
**Referências de ADR**: ADR-004, ADR-005, ADR-007, ADR-008, ADR-009, ADR-011, ADR-015, ADR-016, ADR-018, ADR-019, ADR-022, ADR-024 (unificação de perfil, base para esta feature)

---

## Relação com Trabalho Anterior (leia isto primeiro)

Esta spec é a continuação direta de `specs/026-user-agent-registration-unification/spec-idea.md` (unificação de **cadastro**: `POST /api/v1/profiles` já cria e completa o `real.estate.agent` associado, incluindo `creci`/`bank_name`/`bank_account`/`pix_key`, e `POST /api/v1/users/invite` já vincula `user_id`). A 026 deixou explicitamente de fora — e nomeou como candidatos a uma spec futura — dois problemas que esta spec (027) resolve:

1. **Duplicação de list/get** entre `GET /api/v1/agents`(`/<id>`) e `GET /api/v1/profiles`(`/<id>`) — todo `profile_type` além de `agent` já usa exclusivamente os endpoints de `/profiles`; só `agent` mantém um par de endpoints paralelo.
2. **Divergência real de segurança entre `deactivate`/`reactivate` por `/agents` vs. por `/profiles`** — `DELETE /api/v1/profiles/<id>` já cascateia para `real.estate.agent` + `res.users` + invalida sessões Redis ativas; `POST /api/v1/agents/<id>/deactivate` só desativa o `real.estate.agent`, deixando o login e a sessão intactos. Não existe hoje um `POST /api/v1/profiles/<id>/reactivate` — só o soft-delete via `DELETE`.

Esta spec **não** repete a lógica de upsert de agente, o vínculo `user_id`, nem o achado de segurança sobre `invite_user`/isolamento entre empresas (candidato a uma spec própria, ainda não endereçado) — esses seguem exatamente como a 026 os deixou.

### Decisões de Design Confirmadas pelo Solicitante (2026-07-27)

Cinco decisões de escopo foram confirmadas explicitamente antes da elaboração desta spec, e são tratadas como requisitos definitivos, não como questões em aberto:

1. **Correção de deactivate/reactivate — Opção A**: remover `POST /api/v1/agents/<id>/deactivate` e `POST /api/v1/agents/<id>/reactivate`; usar exclusivamente `DELETE /api/v1/profiles/<id>` (já existente, já cascateia) + um novo `POST /api/v1/profiles/<id>/reactivate`.
2. **Remoção direta de `GET /api/v1/agents` e `GET /api/v1/agents/<id>`**, sem janela de descontinuação — mesmo precedente já estabelecido pela Feature 026 (Padrão "Substituição Direta em vez de Janela de Descontinuação") — assim que `GET /api/v1/profiles` ganhar paridade de campos (sub-objeto `agent` embutido) e os filtros `creci_number`/`creci_state`.
3. **Unificação também de `PUT /api/v1/agents/<id>`**: mover `creci`/`bank_name`/`bank_account`/`bank_branch`/`bank_account_type`/`pix_key` para `PUT /api/v1/profiles/<id>` (validados somente quando `profile_type=='agent'`, reaproveitando o mesmo padrão condicional que `create_profile` já usa desde a 026), e remover `PUT /api/v1/agents/<id>` diretamente.
4. **Autorização de deactivate/reactivate — revisada para `owner`/`admin` apenas (mais restritiva que a decisão inicial)**: endurecer `DELETE /api/v1/profiles/<id>` (comportamento já existente) e o novo `POST /api/v1/profiles/<id>/reactivate` para exigir **`owner` OU `base.group_system` (admin)** **para QUALQUER `profile_type`**, não só `agent`. A decisão inicial (2026-07-27, primeira rodada) incluía também `director`/`manager` nessa matriz; foi revisada (2026-07-27, segunda rodada) após um cruzamento com outras specs/ADRs do projeto revelar dois conflitos reais — ver seção dedicada "⚠️ Mudança de Comportamento Breaking" abaixo para a justificativa completa. Isto é uma **mudança de comportamento breaking** em relação ao comportamento atual de `DELETE /profiles/<id>` (que hoje não tem NENHUMA checagem de grupo/role — qualquer usuário autenticado com acesso à empresa pode desativar qualquer perfil, inclusive de um colega de nível superior), e é **mais restritiva** que a matriz de convite já implementada (Feature 009), que permite Manager/Director convidarem vários tipos de perfil — aqui, deliberadamente, nem Director (que herda todas as permissões de Manager sobre profile/agent) ganha autorização para desativar/reativar; só Owner/admin.
5. **MVP**: Não — especificação completa, sem itens marcados `[POST-MVP]`.

---

## ⚠️ Mudança de Comportamento Breaking — Autorização de Deactivate/Reactivate (leia com atenção)

**Comportamento atual (antes desta feature), confirmado no código (`profile_api.py::delete_profile`)**: não existe nenhuma checagem de `user.has_group(...)` — qualquer usuário autenticado com `company_id` compatível pode desativar (soft-delete) **qualquer** perfil da própria empresa, independentemente do seu próprio papel. Um `receptionist` pode hoje desativar o perfil de um `manager`, ou até de um `owner`, por exemplo.

**Comportamento após esta feature**: tanto `DELETE /api/v1/profiles/<id>` quanto o novo `POST /api/v1/profiles/<id>/reactivate` passam a exigir que o solicitante tenha `group_real_estate_owner` **OU** `base.group_system` (admin) — para **qualquer** `profile_type` alvo, não apenas `agent`. **Todo outro papel recebe `403 forbidden`, incluindo Manager e Director** (não só agent/receptionist/prospector/financial/legal/tenant/property_owner, como uma primeira versão desta spec havia definido) — mesmo o próprio Director, que herda todas as permissões de Manager sobre `profile`/`agent` em outras operações (record rules, CRUD), não recebe autorização para desativar ou reativar nenhum perfil. Esta é, deliberadamente, a matriz mais restritiva já usada nesta feature.

**Por que a matriz foi restringida de 4 grupos (owner/director/manager/admin) para 2 (owner/admin) — revisão feita em 2026-07-27, após a primeira versão desta spec já ter sido redigida**: um cruzamento posterior com outras specs/ADRs do projeto revelou dois conflitos reais entre a decisão inicial ("mais ampla") e regras já codificadas e já implementadas em produção:

1. **Gerenciar `res.users` já é uma regra Owner-only, codificada em três lugares independentes**: ADR-019 (linhas 106 e 130, `## Perfis Pré-definidos`) documenta explicitamente, tanto para Manager quanto para Director, "**NÃO** criar/excluir usuários (apenas Owner)"; `security/groups.xml` (comentários das linhas 27 e 35) repete a mesma restrição textualmente para os grupos `group_real_estate_manager` e `group_real_estate_director` ("Cannot create users (only Owner can)"); e `security/ir.model.access.csv` (linha 10, `access_owner_res_users`) contém a **única** linha de ACL do módulo para `base.model_res_users`, atribuída somente a `group_real_estate_owner` — Manager e Director não têm nenhuma linha de ACL sobre `res.users`, nem de leitura nem de escrita. Como `DELETE /profiles/<id>` e `POST /profiles/<id>/reactivate` cascateiam para `res.users.active` (desativar/reativar o login), autorizar Manager/Director a chamar esses endpoints seria, na prática, dar a eles uma via indireta de gerenciar `res.users` — algo que a arquitetura de ACL do projeto proíbe explicitamente para esses dois papéis.
2. **Assimetria com a matriz de convite já implementada** (`specs/009-user-onboarding-password-management/spec.md`, linhas 544-551, `Authorization Matrix`): Manager só pode **convidar** `agent`/`prospector`/`receptionist`/`financial`/`legal` — nunca `owner`/`director`/`manager`. Autorizar Manager a **desativar/reativar** QUALQUER `profile_type` (incluindo `owner`/`director`/outro `manager`) seria estritamente mais permissivo, no sentido oposto (destruição de acesso, não criação), do que a matriz de convite já aceita e testada da Feature 009 — uma incoerência de design que a segunda rodada de revisão eliminou.

**Achado de correção de bug preservado da primeira rodada de revisão**: verificado em `18.0/extra-addons/quicksol_estate/security/groups.xml`, o grupo `group_real_estate_owner` **não** implica (`implied_ids`) `group_real_estate_manager` — só implica `base.group_user`. Isso significa que uma checagem de autorização escrita apenas como `user.has_group('quicksol_estate.group_real_estate_manager')` (como o `agent_api.py` legado faz hoje em `deactivate_agent`/`reactivate_agent`/`update_agent`, texto do erro: *"Only managers can..."*) **exclui silenciosamente o Owner**, que tecnicamente não passa nessa checagem a menos que também tenha o grupo manager atribuído explicitamente. Esta spec **não repete essa omissão** — mesmo com a matriz reduzida a 2 grupos, a checagem verifica `owner` explicitamente (nunca infere Owner a partir de uma checagem de `manager`).

**Por que isso é aceito apesar de ser breaking**: foi uma escolha explícita do solicitante, revisada em uma segunda rodada após confronto com evidência concreta de conflito com regras já codificadas — o objetivo passou a ser eliminar a inconsistência de autorização entre perfis do tipo `agent` (hoje protegidos por `agent_api.py` legado) e todos os demais tipos (hoje desprotegidos em `profile_api.py`), estabelecendo uma única regra para todos, mas essa regra única é agora a mais restritiva possível (`owner`/`admin`) — não a mais permissiva que havia sido cogitada inicialmente — precisamente para não abrir uma via indireta de gerenciamento de `res.users` para Manager/Director, e para não contradizer a matriz de convite já existente da Feature 009.

**Testes obrigatórios explícitos** (ver User Story 1/2, Cobertura de Testes):
- `test_owner_or_admin_can_deactivate_any_profile_type()` — confirma que Owner e admin (`base.group_system`) são autorizados.
- `test_manager_and_director_cannot_deactivate_any_profile_type()` — **novo teste de regressão obrigatório**, dado que Manager era autorizado na primeira versão desta spec: confirma 403 para Manager e para Director (isoladamente, sem também ter o grupo Owner), para pelo menos dois `profile_type` diferentes (`agent` e um tipo não-agent, ex. `tenant`), incluindo a tentativa de desativar o próprio perfil.
- `test_non_manager_cannot_deactivate_any_profile_type()` — mantido: agent/receptionist/prospector/financial/legal continuam recebendo 403.

---

## Resumo Executivo

`real.estate.agent` mantém hoje um par duplicado de endpoints de list/get (`GET /api/v1/agents`, `GET /api/v1/agents/<id>`) que nenhum outro `profile_type` possui — todos os outros 9 tipos já usam exclusivamente `GET /api/v1/profiles`(`/<id>`). Além disso, `deactivate`/`reactivate` de agente por `/agents/<id>` diverge do fluxo já existente e mais completo de `DELETE /api/v1/profiles/<id>` (que cascateia para agente + login + sessão Redis), deixando um agente desativado por essa rota legada com sessão ativa e login funcional. Esta feature: (1) unifica list/get de agente em `/api/v1/profiles`, embutindo um sub-objeto `agent` com paridade total de campos e aceitando `creci_number`/`creci_state` como filtros; (2) unifica update de campos exclusivos de agente em `PUT /api/v1/profiles/<id>`; (3) substitui `POST /api/v1/agents/<id>/deactivate|reactivate` por `DELETE /api/v1/profiles/<id>` (já existente) + um novo `POST /api/v1/profiles/<id>/reactivate`; e (4) endurece a autorização de ambos para **`owner`/`admin` apenas**, para **todos** os `profile_type` — uma correção de segurança deliberada, mais ampla em escopo (todos os tipos, não só agent) mas mais restrita em papéis autorizados (nem Manager nem Director) do que o pedido original, revisada após confronto com ADR-019/`ir.model.access.csv` (gerenciar `res.users` é regra Owner-only) e a matriz de convite já implementada (Feature 009). `GET /api/v1/agents`, `GET /api/v1/agents/<id>`, `PUT /api/v1/agents/<id>`, `POST /api/v1/agents/<id>/deactivate` e `POST /api/v1/agents/<id>/reactivate` são removidos diretamente, sem janela de descontinuação, assim que o fluxo unificado estiver validado — mesmo precedente já estabelecido pela Feature 026.

---

## Fora de Escopo / Não-Objetivos

**Fora de Escopo**:
- `GET /api/v1/agents/<id>/properties`, `/performance`, `/commission-rules`, `GET /api/v1/agents/ranking`, `POST /api/v1/assignments` (e todo o sub-recurso de `assignments`) **permanecem exatamente como estão** — lógica de domínio/negócio exclusiva de agente (comissão, ranking, atribuição de imóveis) sem equivalente em nenhum outro `profile_type`. Nenhuma mudança de rota, autorização ou schema nesses endpoints.
- A lógica de upsert de agente durante o convite (`POST /api/v1/users/invite`), o vínculo `agent.user_id`, e a validação condicional de campos de agente em `POST /api/v1/profiles` — tudo já implementado pela Feature 026 — não são reabertos aqui.
- O achado de segurança sobre ausência de checagem de `company_id` cross-tenant em `invite_user` (documentado na 026 como candidato a uma spec própria) permanece fora de escopo — não é revisitado nesta feature.
- `owner_api.py` (`POST /api/v1/owners`, `/owners/{id}/companies`) — fluxo de bootstrap/auto-registro de imobiliária, semanticamente diferente de list/get/deactivate de perfil já existente; não é list/get duplicado e não é tocado por esta spec.
- Renomear `real.estate.agent` para um nome de modelo com prefixo `thedevkitchen_` continua fora de escopo (exceção legada aceita, constituição §12 item 5).
- Adicionar índice de banco de dados em `real.estate.agent.user_id` — **já existe** (`index=True` confirmado em `models/agent.py`, linha 88); não é uma ação desta spec.
- Prevenir que um `manager`/`owner`/`director` desative o **próprio** perfil (self-lockout) — não solicitado, não introduzido nem corrigido por esta feature; comportamento pré-existente do `DELETE /profiles/<id>` (que já permitia desativar qualquer perfil, incluindo o próprio) simplesmente passa a exigir autorização adequada, mas a possibilidade de autodesativação em si não é endereçada.
- Construir fluxo de UI/Cypress — fora de escopo (Modelo de Acesso: apenas o `admin` do Odoo acessa a UI do Odoo; todos os papéis desta spec usam o frontend headless).

**Comportamentos Proibidos** (a implementação NÃO DEVE introduzir):
- [ ] NÃO DEVE enfraquecer o isolamento multi-tenant (ADR-008) — todas as checagens de empresa (`request.user_company_ids`, anti-enumeração via 404) já existentes em `get_profile`/`delete_profile` DEVEM ser preservadas e replicadas identicamente no novo `POST /profiles/<id>/reactivate`.
- [ ] NÃO DEVE contornar ou remover a cadeia de triplo decorador (`@require_jwt` + `@require_session` + `@require_company`, ADR-011) em nenhum endpoint tocado ou criado.
- [ ] NÃO DEVE substituir a convenção de soft-delete (ADR-015, campo `active`) por exclusão física — nem em `real.estate.profile`, nem em `real.estate.agent`, nem em `res.users`.
- [ ] NÃO DEVE criar estado parcial no reactivate — se o profile for reativado mas a cascata para `real.estate.agent` ou `res.users` falhar (ex.: constraint de unicidade), a transação inteira DEVE reverter (nenhum profile ativo com agente/usuário ainda inativo).
- [ ] NÃO DEVE restaurar sessões Redis previamente invalidadas ao reativar um perfil — reativação restaura `active=True` em profile/agent/user, mas nunca reativa um registro `thedevkitchen.api.session` já marcado `is_active=False`; o usuário deve autenticar novamente para obter uma sessão nova.
- [ ] NÃO DEVE assumir que checar `has_group('quicksol_estate.group_real_estate_manager')` sozinho cobre o Owner — `group_real_estate_owner` não implica `group_real_estate_manager` (verificado em `security/groups.xml`); toda checagem de autorização desta feature verifica os quatro grupos explicitamente.
- [ ] NÃO DEVE fazer merge de branches de implementação em `develop`/`master` sem autorização explícita do usuário (`.claude/rules/git-workflow.md`), mesmo gatilho de processo documentado pela Feature 026 após a reversão da Feature 025.

**Armadilhas Conhecidas**:
- A Feature 025 foi revertida por um merge não autorizado na `develop` — reforçar o gate de confirmação explícita antes de qualquer merge, não repetir o incidente.
- `_serialize_profile` (`profile_api.py`) já faz, para cada perfil do tipo `agent` serializado em uma lista, uma busca (`search()`) individual em `real.estate.agent` — um padrão N+1 pré-existente desde a Feature 010/024, hoje limitado a um único campo (`agent_id`). Esta spec **amplia** o que é embutido (todo o sub-objeto `agent`) e, por isso, tem a obrigação de **corrigir** o N+1 em vez de apenas ampliá-lo (ver FR1.4/NFR2) — não introduzir mais chamadas per-row sem resolver esse padrão.
- Duas HATEOAS links internas hoje referenciam `/api/v1/agents/{id}` fora de `agent_api.py`/`profile_api.py`: `thedevkitchen_user_onboarding/controllers/invite_controller.py:214` (`links["agent"]`, adicionada pela Feature 026) e `quicksol_estate/controllers/sale_api.py:88` (`links["agent"]`). Como `GET /api/v1/agents/<id>` é removido por esta spec, essas duas referências viram links mortos (404) se não forem corrigidas — ver FR6.4.

---

## Cenários de Usuário & Testes

### User Story 1: Owner/Admin desativa qualquer perfil de forma consistente (Prioridade: P1) 🎯

**Como** Owner da imobiliária ou Admin do sistema
**Eu quero** que desativar um perfil (de qualquer tipo, incluindo `agent`) sempre cascateie para o registro de domínio associado, o login e a sessão ativa
**Para que** nunca exista um agente/usuário "desativado" que ainda está logado com uma sessão válida, e que apenas quem já tem autoridade sobre `res.users` (Owner/Admin, per ADR-019/ACL) possa fazer isso

**Critérios de Aceitação**:
- [ ] Dado um perfil do tipo `agent` ativo, com `real.estate.agent` e `res.users` vinculados e uma sessão Redis ativa, quando um Owner chama `DELETE /api/v1/profiles/<id>`, então profile, agent e user ficam `active=False` e a sessão é invalidada (`is_active=False`) — comportamento já existente, preservado sem alteração.
- [ ] Dado o mesmo cenário, quando um usuário do grupo `agent`, `receptionist`, `prospector`, `financial` ou `legal` chama `DELETE /api/v1/profiles/<id>` (para qualquer `profile_type`, não só `agent`), então a resposta é `403 forbidden` — **mudança de comportamento em relação ao estado atual**, onde essa chamada era aceita sem checagem de grupo.
- [ ] Dado um usuário do grupo `manager` OU `director` (sem também ter o grupo `owner`), quando chama `DELETE /api/v1/profiles/<id>` para **qualquer** `profile_type` (incluindo `agent`, e incluindo o próprio perfil do solicitante), então a resposta é `403 forbidden` — **caso de regressão explícito**: Manager e Director eram autorizados numa primeira versão desta spec; a matriz foi restringida a `owner`/`admin` apenas, por conflitar com ADR-019/`ir.model.access.csv` (gerenciar `res.users` é regra Owner-only) e com a matriz de convite já implementada (Feature 009).
- [ ] Dado um Owner (apenas `group_real_estate_owner`, sem nenhum outro grupo adicional), quando chama `DELETE /api/v1/profiles/<id>`, então a operação é autorizada (a checagem verifica `owner` explicitamente, não depende de herança de `manager` — `group_real_estate_owner` não implica `group_real_estate_manager`).
- [ ] Dado que `POST /api/v1/agents/<id>/deactivate` foi removido (User Story 3), quando esse caminho é chamado, então a resposta é `404` padrão (rota inexistente).
- [ ] Dado um perfil já inativo, quando `DELETE /api/v1/profiles/<id>` é chamado novamente, então a resposta é `400` ("Profile is already inactive") — comportamento já existente, preservado.
- [ ] Dado um perfil ativo de **qualquer** `profile_type` com `res.users` vinculado e uma sessão Redis ativa (não só `agent` — também `manager`, `director`, `owner`, `tenant`, `receptionist`), quando um Owner/admin chama `DELETE /api/v1/profiles/<id>`, então o registro `thedevkitchen.api.session` correspondente é marcado `is_active=False` **no mesmo request** (invalidação proativa, não dependente de TTL), e uma chamada de API subsequente autenticada com o `session_id` antigo retorna `401` imediatamente. Este comportamento já existe desde a Feature 023 (Redis Session Cache) para o caso `agent`; esta spec amplia sua cobertura de teste para acompanhar o escopo ampliado de `DELETE /profiles/<id>` a qualquer `profile_type` (FR3.3), sem alterar a implementação em si (`api_session.py::write()`, `session_validator.py::validate()`).
- [ ] Dado um perfil ativo de qualquer `profile_type` **sem** `res.users` vinculado (perfil cadastrado mas nunca convidado — `partner_id` sem `user_ids`, ou sem `partner_id`), quando `DELETE /api/v1/profiles/<id>` é chamado, então a operação conclui normalmente (profile desativado) sem erro e sem nenhuma tentativa de busca/invalidação de sessão — comportamento já existente (`delete_profile` só entra no bloco de cascata de `res.users`/sessão quando `profile.partner_id` existe), preservado.

**Cobertura de Testes** (conforme ADR-003):

| Tipo | Nome do Teste | Descrição | Status |
|------|-----------|-------------|--------|
| Unitário | `test_delete_profile_requires_owner_or_admin()` | Checagem de grupo explícita nos 2 papéis autorizados (`owner`, `base.group_system`) | ⚠️ Obrigatório |
| E2E (API) | `test_owner_or_admin_can_deactivate_any_profile_type()` | Owner e admin autorizados para `agent` e para um tipo não-agent (ex. `tenant`) | ⚠️ Obrigatório |
| E2E (API) | `test_manager_and_director_cannot_deactivate_any_profile_type()` | **Novo teste de regressão obrigatório**: Manager e Director (isoladamente, sem grupo owner) → 403 para `agent` e para `tenant`, incluindo tentativa de desativar o próprio perfil | ⚠️ Obrigatório |
| E2E (API) | `test_non_manager_cannot_deactivate_any_profile_type()` | `agent`/`receptionist`/`prospector`/`financial`/`legal` tentando `DELETE /profiles/<id>` para qualquer `profile_type` → 403 | ⚠️ Obrigatório |
| E2E (API) | `test_owner_deactivates_agent_profile_cascades_fully()` | agent + user + sessão Redis todos ficam inativos/invalidados (regressão do comportamento já existente) | ⚠️ Obrigatório |
| E2E (API) | `test_deactivate_invalidates_active_session_across_all_profile_types()` | **Novo, escopo ampliado por esta spec** — parametrizado (ou casos explícitos) para `agent`, `manager`, `director`, `owner`, `tenant`, `receptionist`: cada perfil ativo com `res.users`+sessão Redis ativa vinculados é desativado via `DELETE /profiles/<id>`; a sessão fica `is_active=False` no mesmo request (invalidação proativa, ver `specs/023-redis-session-cache/spec.md`, Q&A ~linha 33: "Proativa... O mesmo padrão já implementado em `password_service._invalidate_user_sessions()`"); uma chamada subsequente com o `session_id` antigo recebe `401` imediatamente, sem depender do TTL do cache (`api_session.py::write()` dispara a invalidação; `session_validator.py::validate()` já força o fallback ao banco). Inclui também o caso "perfil sem `res.users` vinculado → sem erro, sem tentativa de invalidação" | ⚠️ Obrigatório |
| E2E (API) | `test_deactivate_agent_legacy_route_removed_404()` | `POST /api/v1/agents/<id>/deactivate` → 404 após remoção | ⚠️ Obrigatório |
| E2E (API) | `test_multitenancy_isolation_delete_profile()` | Perfil de empresa diferente → 404 anti-enumeração (comportamento já existente, preservado) | ⚠️ Obrigatório |

### User Story 2: Owner/Admin reativa um perfil previamente desativado (Prioridade: P1) 🎯

**Como** Owner da imobiliária ou Admin do sistema
**Eu quero** reativar um perfil (de qualquer tipo) através de um único endpoint, com cascata completa para o registro de domínio e o login
**Para que** eu não precise usar um endpoint diferente por `profile_type`, e o agente reativado volte a ficar visível em toda checagem de RBAC (`agent_id.user_id`)

**Critérios de Aceitação**:
- [ ] Dado um perfil inativo do tipo `agent` (com `real.estate.agent.active=False` e `res.users.active=False`), quando um Owner chama `POST /api/v1/profiles/<id>/reactivate`, então profile, agent e user voltam a `active=True`, e `deactivation_date`/`deactivation_reason` são limpos em profile e agent.
- [ ] Dado o mesmo cenário, quando a reativação é concluída, então **nenhuma** sessão Redis previamente invalidada é restaurada — o usuário precisa efetuar login novamente para obter um novo JWT/sessão.
- [ ] Dado um perfil de um `profile_type` diferente de `agent` (ex.: `tenant`, `receptionist`), quando reativado, então apenas profile (e `res.users`, se vinculado) são reativados — nenhuma tentativa de tocar `real.estate.agent` é feita.
- [ ] Dado um perfil já ativo, quando `POST /api/v1/profiles/<id>/reactivate` é chamado, então a resposta é `400` ("Profile is already active") — nenhuma escrita ocorre.
- [ ] Dado um solicitante do grupo `manager` OU `director` (sem grupo `owner`), quando chama este endpoint para qualquer `profile_type`, então a resposta é `403 forbidden` — mesma matriz restrita de User Story 1, aplicada simetricamente ao reactivate.
- [ ] Dado um solicitante sem grupo `owner`/admin, quando chama este endpoint para qualquer `profile_type`, então a resposta é `403 forbidden`.
- [ ] Dado um perfil de empresa diferente da do solicitante, quando este endpoint é chamado, então a resposta é `404` (anti-enumeração, mesmo padrão de `get_profile`/`delete_profile`).
- [ ] Dado que a cascata para `real.estate.agent` falha (ex.: constraint `_check_user_unique` disparada por algum estado inconsistente pré-existente), quando `POST /api/v1/profiles/<id>/reactivate` é chamado, então a transação inteira reverte — o profile permanece `active=False` (nenhum estado parcial).

**Cobertura de Testes**:

| Tipo | Nome do Teste | Descrição | Status |
|------|-----------|-------------|--------|
| Unitário | `test_reactivate_already_active_profile_returns_400()` | Idempotência/guarda de estado | ⚠️ Obrigatório |
| Unitário | `test_reactivate_requires_owner_or_admin()` | Mesma matriz de autorização restrita do DELETE (`owner`, `base.group_system`) | ⚠️ Obrigatório |
| E2E (API) | `test_owner_reactivates_agent_profile_cascades_fully()` | profile+agent+user voltam a `active=True`, campos de desativação limpos | ⚠️ Obrigatório |
| E2E (API) | `test_manager_and_director_cannot_reactivate_any_profile_type()` | **Novo teste de regressão obrigatório** (simétrico ao de US1): Manager e Director → 403 no reactivate, para `agent` e para um tipo não-agent | ⚠️ Obrigatório |
| E2E (API) | `test_reactivate_does_not_restore_invalidated_session()` | Sessão Redis previamente invalidada continua `is_active=False` após reativação | ⚠️ Obrigatório |
| E2E (API) | `test_reactivate_non_agent_profile_type_skips_agent_cascade()` | Perfil `tenant` reativado sem nenhuma escrita em `real.estate.agent` | ⚠️ Obrigatório |
| E2E (API) | `test_reactivate_atomic_rollback_on_agent_constraint_failure()` | Falha na cascata do agente reverte a transação inteira | ⚠️ Obrigatório |
| E2E (API) | `test_multitenancy_isolation_reactivate_profile()` | Perfil de empresa diferente → 404 | ⚠️ Obrigatório |
| E2E (API) | `test_reactivate_agent_legacy_route_removed_404()` | `POST /api/v1/agents/<id>/reactivate` → 404 após remoção | ⚠️ Obrigatório |

### User Story 3: Qualquer usuário autorizado consulta list/get de agentes via `/api/v1/profiles` (Prioridade: P1) 🎯

**Como** Manager, Owner, Director, Agent ou qualquer papel com acesso de leitura já existente a perfis
**Eu quero** listar e consultar agentes usando o mesmo endpoint já usado para todos os outros `profile_type`, com paridade total de campos e os mesmos filtros de CRECI que existiam em `/agents`
**Para que** eu não precise manter dois clientes de API diferentes para o mesmo tipo de dado, e a superfície de API pare de ter uma rota duplicada só para `agent`

**Critérios de Aceitação**:
- [ ] Dado um perfil `profile_type=='agent'` com `real.estate.agent` vinculado, quando `GET /api/v1/profiles/<id>` é chamado, então a resposta inclui um sub-objeto `agent` contendo `id`, `creci`, `creci_normalized`, `creci_number`, `creci_state`, `bank_name`, `bank_account`, `bank_account_type`, `pix_key`, `active`, `deactivation_date`, `deactivation_reason`, `user_id` — paridade total com os campos que `GET /api/v1/agents/<id>` expunha, mais os links `properties`/`performance`/`commission-rules` (os únicos sub-recursos de agente que continuam existindo).
- [ ] Dado o mesmo cenário, quando `GET /api/v1/profiles` (lista) é chamado com `profile_type=agent`, então cada item da lista tem o mesmo sub-objeto `agent` embutido, obtido via uma única busca em lote (não uma busca por linha — ver FR1.4/NFR2).
- [ ] Dado o parâmetro `creci_number=<valor>`, quando `GET /api/v1/profiles` é chamado, então o resultado é filtrado para perfis cujo `real.estate.agent.creci_number` casa (`ilike`) com o valor — comportamento equivalente ao que `GET /api/v1/agents?creci_number=...` já fazia.
- [ ] Dado o parâmetro `creci_state=<UF>`, quando `GET /api/v1/profiles` é chamado, então o resultado é filtrado por `creci_state` exato (case-insensitive, normalizado para maiúsculas) — mesmo comportamento de `GET /api/v1/agents?creci_state=...`.
- [ ] Dado `creci_number`/`creci_state` combinados com nenhum agente correspondente, quando `GET /api/v1/profiles` é chamado, então a resposta é uma lista vazia (`count=0`), não um erro.
- [ ] Dado que `GET /api/v1/agents` e `GET /api/v1/agents/<id>` foram removidos (após validação), quando qualquer um é chamado, então a resposta é `404` padrão.
- [ ] Dado um perfil `profile_type` diferente de `agent`, quando `GET /api/v1/profiles/<id>` é chamado, então nenhum sub-objeto `agent` aparece na resposta (comportamento já existente, inalterado).

**Cobertura de Testes**:

| Tipo | Nome do Teste | Descrição | Status |
|------|-----------|-------------|--------|
| Unitário | `test_serialize_profile_embeds_full_agent_subobject()` | Paridade de campos do sub-objeto `agent` | ⚠️ Obrigatório |
| Unitário | `test_serialize_profile_no_agent_subobject_for_non_agent_type()` | Nenhum campo de agente vaza para outros `profile_type` | ⚠️ Obrigatório |
| Unitário | `test_list_profiles_creci_number_filter()` | Filtro `ilike` por `creci_number` | ⚠️ Obrigatório |
| Unitário | `test_list_profiles_creci_state_filter_case_insensitive()` | Filtro exato por `creci_state`, normalizado | ⚠️ Obrigatório |
| Unitário | `test_list_profiles_creci_filters_no_match_returns_empty()` | Nenhum erro, apenas lista vazia | ⚠️ Obrigatório |
| Unitário | `test_list_profiles_agent_subobject_batched_no_n_plus_one()` | Uma única query `real.estate.agent.search()` para toda a página, não uma por linha | ⚠️ Obrigatório |
| E2E (API) | `test_get_profile_agent_full_field_parity_with_legacy_get_agent()` | Resposta de `GET /profiles/<id>` cobre todo campo que `GET /agents/<id>` legado retornava | ⚠️ Obrigatório |
| E2E (API) | `test_list_agents_route_removed_404()` | `GET /api/v1/agents` → 404 após remoção | ⚠️ Obrigatório |
| E2E (API) | `test_get_agent_route_removed_404()` | `GET /api/v1/agents/<id>` → 404 após remoção | ⚠️ Obrigatório |
| E2E (API) | `test_multitenancy_isolation_list_profiles_agent_type()` | Filtro `company_ids` continua isolando corretamente com o sub-objeto `agent` embutido | ⚠️ Obrigatório |

### User Story 4: Manager atualiza dados exclusivos de agente via `PUT /api/v1/profiles/<id>` (Prioridade: P2)

**Como** Manager, Owner ou Director
**Eu quero** atualizar `creci`, dados bancários e `pix_key` de um agente usando o mesmo endpoint de update já usado para os demais campos do perfil
**Para que** eu não precise chamar `PUT /api/v1/agents/<id>` separadamente para um subconjunto de campos

**Critérios de Aceitação**:
- [ ] Dado um perfil `profile_type=='agent'`, quando `PUT /api/v1/profiles/<id>` é chamado com `creci`, `bank_name`, `bank_account`, `bank_account_type`, `bank_branch` e/ou `pix_key`, então o registro `real.estate.agent` vinculado é atualizado com esses valores (além da sincronização já existente de `name`/`email`/`phone`/`mobile`/`hire_date`).
- [ ] Dado um perfil `profile_type` diferente de `agent`, quando `PUT /api/v1/profiles/<id>` é chamado com qualquer um desses campos, então eles são silenciosamente ignorados (sem erro, sem escrita) — mesmo padrão condicional já usado em `create_profile` desde a 026.
- [ ] Dado um `creci` malformado (menos de 4 caracteres), quando `PUT /api/v1/profiles/<id>` é chamado para um perfil `agent`, então a resposta é `400 validation_error` e nenhuma escrita ocorre (nem em profile, nem em agent).
- [ ] Dado um `creci` bem formado mas já usado por outro agente ativo na mesma empresa, quando `PUT /api/v1/profiles/<id>` é chamado, então a resposta é `409 conflict` — profile e agent revertidos (rollback explícito, mesmo padrão de `create_profile`).
- [ ] Dado que `PUT /api/v1/agents/<id>` foi removido, quando chamado, então a resposta é `404` padrão.

**Cobertura de Testes**:

| Tipo | Nome do Teste | Descrição | Status |
|------|-----------|-------------|--------|
| Unitário | `test_update_profile_agent_fields_synced_when_agent_type()` | creci/bank fields propagados ao agente | ⚠️ Obrigatório |
| Unitário | `test_update_profile_agent_fields_ignored_for_non_agent_type()` | Campos irrelevantes ignorados sem erro | ⚠️ Obrigatório |
| Unitário | `test_update_profile_creci_format_validation()` | 400 para creci malformado | ⚠️ Obrigatório |
| E2E (API) | `test_update_profile_creci_conflict_returns_409_with_rollback()` | 409 + nenhuma escrita parcial | ⚠️ Obrigatório |
| E2E (API) | `test_update_agent_legacy_route_removed_404()` | `PUT /api/v1/agents/<id>` → 404 após remoção | ⚠️ Obrigatório |

---

## Requisitos

### Requisitos Funcionais

**FR1: Paridade de List/Get em `GET /api/v1/profiles`**
- FR1.1: `list_profiles` DEVE aceitar os parâmetros de query opcionais `creci_number` (filtro `ilike` sobre `real.estate.agent.creci_number`) e `creci_state` (filtro exato, normalizado para maiúsculas, sobre `real.estate.agent.creci_state`).
- FR1.2: Quando `creci_number`/`creci_state` são fornecidos, o controller DEVE primeiro resolver os `profile_id`s correspondentes via uma única busca em `real.estate.agent.sudo().with_context(active_test=False)`, e então adicionar `("id", "in", <profile_ids>)` (ou `("id", "=", False)` se nenhum agente corresponder) ao domínio de `thedevkitchen.estate.profile` — nunca uma condição direta sobre um campo inexistente em `profile`.
- FR1.3: `_serialize_profile` DEVE embutir um sub-objeto `agent` quando `profile.profile_type_id.code == 'agent'` e existir um `real.estate.agent` vinculado, contendo: `id`, `creci`, `creci_normalized`, `creci_number`, `creci_state`, `bank_name`, `bank_account`, `bank_account_type`, `pix_key`, `active`, `deactivation_date`, `deactivation_reason`, `user_id` (o `res.users.id` vinculado ao agente, se houver) — paridade total com os campos que `GET /api/v1/agents/<id>` legado expunha, exceto `_links.self`/`update`/`deactivate`/`reactivate` (que não fazem mais sentido, pois esses métodos não existem mais em `/agents/<id>` — ver FR6.4).
- FR1.4 (**correção de performance obrigatória, não apenas ampliação do campo**): Ao serializar uma **lista** de perfis (`list_profiles`), o sub-objeto `agent` DEVE ser resolvido via uma única busca em lote — `real.estate.agent.sudo().with_context(active_test=False).search([("profile_id", "in", <profile_ids da página atual>)])` — construindo um dicionário `profile_id → agent` passado para `_serialize_profile`, em vez de uma busca individual por linha (o padrão N+1 pré-existente desde a Feature 010, que esta spec amplia em campos mas corrige em consultas). `get_profile` (registro único) mantém a busca individual existente — sem N+1 possível para um único registro.
- FR1.5: O campo já existente `agent_id` (top-level, adicionado pela Feature 024/010) e o link `_links.agent` continuam presentes por compatibilidade retroativa com consumidores da Feature 026, mas `_links.agent` passa a apontar para `/api/v1/profiles/{profile.id}` (não mais para `/api/v1/agents/{agent.id}`, rota removida — ver FR6.4). Links para sub-recursos de agente que **continuam existindo** (`properties`, `performance`, `commission-rules`) são adicionados dentro do sub-objeto `agent` (usando `agent.id`, não `profile.id`, já que esses sub-recursos são endereçados pelo id do agente).

**FR2: Novo Endpoint — `POST /api/v1/profiles/<int:profile_id>/reactivate`**
- FR2.1: Requer os mesmos decoradores (`@require_jwt`, `@require_session`, `@require_company`) e a mesma checagem de isolamento multi-tenant/anti-enumeração (404 se `profile.company_id` fora de `request.user_company_ids`) já usados em `get_profile`/`delete_profile`.
- FR2.2: Autorização: `owner` OU `base.group_system` (ver FR3 — matriz compartilhada com `DELETE`).
- FR2.3: Se `profile.active == True`, retorna `400` ("Profile is already active") sem qualquer escrita.
- FR2.4: Caso contrário, escreve `profile.write({"active": True, "deactivation_date": False, "deactivation_reason": False})`.
- FR2.5: Se `profile.profile_type_id.code == 'agent'`, busca `real.estate.agent` vinculado (`with_context(active_test=False)`); se existir e estiver inativo, reativa (`active=True`, `deactivation_date=False`, `deactivation_reason=False`) na mesma transação.
- FR2.6: Se `profile.partner_id` tiver um `res.users` vinculado e inativo, reativa-o (`active=True`) na mesma transação — **sem** reativar nenhum registro `thedevkitchen.api.session` previamente marcado `is_active=False` (comportamento deliberadamente assimétrico ao deactivate: o usuário deve autenticar novamente).
- FR2.7: Qualquer falha de constraint durante a cascata (agent ou user) DEVE reverter a transação inteira (nenhum estado parcial — profile ativo com agent/user ainda inativo).
- FR2.8: Resposta de sucesso: `200` com o perfil serializado (`_serialize_profile`, incluindo o sub-objeto `agent` atualizado quando aplicável).

**FR3: Autorização Endurecida e Unificada em `DELETE /profiles/<id>` e `POST /profiles/<id>/reactivate` (mudança de comportamento breaking, restrita a `owner`/`admin` — ver seção dedicada acima)**
- FR3.1: Ambos os endpoints DEVEM checar `user.has_group("quicksol_estate.group_real_estate_owner") or user.has_group("base.group_system")` → caso contrário, `403 forbidden`. **`director` e `manager` NÃO fazem parte desta matriz** — decisão revisada (2026-07-27, segunda rodada) após conflito confirmado com ADR-019 (linhas 106/130: "NÃO criar/excluir usuários — apenas Owner"), `security/groups.xml` (comentários das linhas 27/35, mesma restrição) e `security/ir.model.access.csv` (linha 10: única ACL de `res.users` é `access_owner_res_users`, restrita a `group_real_estate_owner`) — como estes endpoints cascateiam para `res.users.active`, autorizar Manager/Director seria uma via indireta de gerenciar `res.users`, que a arquitetura de ACL do projeto já proíbe para esses dois papéis. Adicionalmente, conflitava com a matriz de convite já implementada (`specs/009-user-onboarding-password-management/spec.md`, linhas 544-551), onde Manager nunca convida `owner`/`director`/`manager` — autorizar Manager a desativar/reativar QUALQUER `profile_type` seria mais permissivo, na direção oposta (remoção/restauração de acesso), do que essa matriz já aceita.
- FR3.2: O grupo `owner` DEVE ser checado explicitamente (nunca inferir Owner a partir de uma checagem de `manager`), dado que `group_real_estate_owner` não implica `group_real_estate_manager` em `security/groups.xml` — mesmo achado de correção de bug já presente no `agent_api.py` legado.
- FR3.3: Esta checagem se aplica a **qualquer** `profile_type`, não apenas `agent` — extensão deliberada além do pedido original, confirmada pelo solicitante; a restrição de papéis (só owner/admin) é, em contrapartida, mais estreita do que a decisão inicial cogitada.
- FR3.4: `DELETE /api/v1/profiles/<id>` (comportamento pré-existente desde a Feature 010, sem checagem de grupo até esta feature) passa a exigir esta mesma autorização — mudança de comportamento que DEVE ser destacada na documentação OpenAPI do endpoint (`breaking change`, versão do módulo incrementada), incluindo uma nota explícita de que Manager/Director, que hoje conseguem chamar este endpoint sem restrição, deixam de conseguir.

**FR4: Remoção de `POST /api/v1/agents/<id>/deactivate` e `POST /api/v1/agents/<id>/reactivate` (direta, sem janela de descontinuação)**
- FR4.1: Excluir os métodos `deactivate_agent`/`reactivate_agent` de `agent_api.py`, suas rotas `@http.route`, e as linhas correspondentes no registro `thedevkitchen.api.endpoint` — em uma única etapa.
- FR4.2: Excluir os testes de integração/unitários que exercitavam exclusivamente esses dois métodos (substituídos pelos testes das User Stories 1/2).
- FR4.3: Pós-remoção, chamar qualquer uma dessas rotas retorna `404` padrão (rota não registrada).

**FR5: Unificação de Update — `PUT /api/v1/profiles/<id>` aceita campos exclusivos de agente**
- FR5.1: `PROFILE_UPDATE_SCHEMA` (ou um novo schema derivado, análogo ao `PROFILE_AGENT_FIELDS_SCHEMA` da Feature 026) passa a aceitar opcionalmente `creci`, `bank_name`, `bank_account`, `bank_account_type`, `bank_branch`, `pix_key`. Esses seis campos (paridade com `allowed_fields` de `update_agent` legado, incluindo os dois — `bank_account_type`, `bank_branch` — que o `AGENT_UPDATE_SCHEMA` legado aceitava sem validação de schema, apenas por lista de campos permitidos no controller; esta spec fecha essa lacuna de validação inconsistente, adicionando-os também ao schema).
- FR5.2: A validação desses 6 campos só roda quando `profile.profile_type_id.code == 'agent'` — reaproveitando exatamente o padrão condicional (`validate_profile_agent_fields`-like) introduzido pela Feature 026 para `create_profile`. Para qualquer outro `profile_type`, esses campos são ignorados silenciosamente, mesmo se presentes e malformados.
- FR5.3: `update_profile` DEVE estender a cascata já existente para `real.estate.agent` (hoje: `name`/`email`/`phone`/`mobile`/`hire_date`) para também incluir `creci`/`bank_name`/`bank_account`/`bank_account_type`/`bank_branch`/`pix_key`, quando presentes no corpo da requisição e o perfil for do tipo `agent`.
- FR5.4: Um conflito de `creci` (já usado por outro agente ativo na mesma empresa) dispara a constraint `_check_creci_format` do modelo (`ValidationError`) — o controller DEVE capturar essa exceção, reverter explicitamente (`request.env.cr.rollback()`, mesmo padrão já usado em `create_profile` desde a 026) e mapear para `409 conflict` (usando a mesma checagem de string `"já cadastrado"` já usada em `create_profile`, ou uma checagem equivalente).
- FR5.5: `PUT /api/v1/agents/<id>` é removido diretamente (ver FR6).

**FR6: Remoção de `GET /api/v1/agents`, `GET /api/v1/agents/<id>`, `PUT /api/v1/agents/<id>` (direta, sem janela de descontinuação — mesmo precedente da Feature 026)**
- FR6.1: Excluir os métodos `list_agents`, `get_agent`, `update_agent` de `agent_api.py`, suas rotas, e as linhas correspondentes no registro `thedevkitchen.api.endpoint`.
- FR6.2: Excluir os testes de integração/unitários substituídos por essas rotas.
- FR6.3: Regenerar OpenAPI (skill `swagger-updater`) e Postman (skill `postman-collection-manager`) confirmando a ausência total dessas operações.
- FR6.4 (**correção obrigatória de links mortos, achado durante a elaboração desta spec**): Atualizar as duas referências internas restantes a `/api/v1/agents/{id}` que quebrariam após esta remoção:
  - `thedevkitchen_user_onboarding/controllers/invite_controller.py:214` (`links["agent"] = f"/api/v1/agents/{agent_id}"`, adicionada pela Feature 026) — DEVE passar a apontar para `/api/v1/profiles/{profile_id}`.
  - `quicksol_estate/controllers/sale_api.py:88` (`links["agent"] = f"/api/v1/agents/{sale.agent_id.id}"`) — DEVE passar a apontar para `/api/v1/profiles/{sale.agent_id.profile_id.id}` (quando `profile_id` estiver definido; se não estiver — agente legado sem `profile_id`, criado antes da Feature 010 — omitir o link `agent` em vez de gerar uma URL inválida).
- FR6.5: Pré-condições de remoção (idênticas ao padrão FR5 da Feature 026): User Stories 1–4 implementadas e com suíte de testes completa passando; verificação de log de acesso de API sem tráfego inesperado nas rotas removidas (ou risco aceito explicitamente); merge na `develop` somente após autorização explícita do usuário.

### Modelo de Dados (conforme ADR-004, knowledge_base/09-database-best-practices.md)

**Nenhuma nova entidade é introduzida.** Esta feature altera exclusivamente a camada de orquestração/serialização em nível de controller entre `thedevkitchen.estate.profile`, `real.estate.agent` e `res.users`, mais uma extensão de schema de validação (nenhuma mudança de coluna de banco de dados).

**Entidade: `real.estate.agent`** (existente, nenhuma mudança de schema)
- Campos já existentes reaproveitados na serialização estendida: `creci`, `creci_normalized` (indexado), `creci_number`, `creci_state`, `bank_name`, `bank_account`, `bank_account_type`, `bank_branch`, `pix_key`, `user_id` (já `index=True`, confirmado — nenhuma migração necessária), `profile_id` (já `index=True`), `active`, `deactivation_date`, `deactivation_reason`.
- Constraints reaproveitadas sem modificação: `_check_creci_format` (unicidade de `creci_normalized` por `company_id`), `_check_user_unique` (um agente por `user_id` por `company_id`).
- `action_deactivate`/`action_reactivate` (métodos já existentes no modelo) continuam existindo e são reaproveitados internamente pelos novos fluxos de `profile_api.py` (guardados por `if agent.active`/`if not agent.active` para evitar o `UserError` que esses métodos disparam ao serem chamados em um estado já correspondente).

**Entidade: `thedevkitchen.estate.profile`** (existente, nenhuma mudança de schema)
- Nenhum campo novo. `profile_type_id.code` continua sendo o discriminador para toda lógica condicional de agente (list, get, update, reactivate).

**Entidade: `res.users`** (existente, nenhuma mudança de schema)
- Cascata de reativação (`active=True`) reaproveita a mesma busca por `partner_id` já usada em `delete_profile`.

**Nova/estendida camada de validação (`quicksol_estate/controllers/utils/schema.py::SchemaValidator`)**:
```python
# Estende o padrão já introduzido pela Feature 026 (PROFILE_AGENT_FIELDS_SCHEMA),
# adicionando os dois campos que o AGENT_UPDATE_SCHEMA legado aceitava sem
# validação de schema (bank_account_type, bank_branch) -- fecha essa lacuna.
PROFILE_AGENT_UPDATE_FIELDS_SCHEMA = {
    "required": [],
    "optional": [
        "creci", "bank_name", "bank_account",
        "bank_account_type", "bank_branch", "pix_key",
    ],
    "types": {
        "creci": str, "bank_name": str, "bank_account": str,
        "bank_account_type": str, "bank_branch": str, "pix_key": str,
    },
    "constraints": {
        "creci": AGENT_CREATE_SCHEMA["constraints"]["creci"],  # reaproveitado por referência
    },
}
```

**Serialização estendida (`profile_api.py::_serialize_profile`, esboço)**:
```python
def _serialize_profile(self, profile, agent_by_profile_id=None):
    data = { ... }  # campos já existentes, inalterados

    if profile.profile_type_id.code == "agent":
        agent = (
            agent_by_profile_id.get(profile.id)  # FR1.4: resolvido em lote na listagem
            if agent_by_profile_id is not None
            else request.env["real.estate.agent"].sudo()
            .with_context(active_test=False)
            .search([("profile_id", "=", profile.id)], limit=1)  # get_profile: busca individual, sem N+1
        )
        if agent:
            data["agent_id"] = agent.id  # compatibilidade retroativa (Feature 026)
            data["agent"] = {
                "id": agent.id,
                "creci": agent.creci,
                "creci_normalized": agent.creci_normalized,
                "creci_number": agent.creci_number,
                "creci_state": agent.creci_state,
                "bank_name": agent.bank_name,
                "bank_account": agent.bank_account,
                "bank_account_type": agent.bank_account_type,
                "pix_key": agent.pix_key,
                "active": agent.active,
                "deactivation_date": agent.deactivation_date.isoformat() if agent.deactivation_date else None,
                "deactivation_reason": agent.deactivation_reason,
                "user_id": agent.user_id.id if agent.user_id else None,
                "_links": {
                    "properties": f"/api/v1/agents/{agent.id}/properties",
                    "performance": f"/api/v1/agents/{agent.id}/performance",
                    "commission_rules": f"/api/v1/agents/{agent.id}/commission-rules",
                },
            }
            data["_links"]["agent"] = f"/api/v1/profiles/{profile.id}"  # FR1.5: não mais /api/v1/agents/{id}

    return data
```

**Record Rules**: Nenhuma nova regra — `rule_agent_own_properties`/`rule_agent_own_assignments` (chaveadas em `agent_id.user_id`) não são afetadas.

### Endpoints de API (conforme ADR-007, ADR-009, ADR-011)

**Endpoint: `GET /api/v1/profiles` (modificado)**

| Atributo | Valor |
|-----------|-------|
| **Método** | GET |
| **Autenticação** | `@require_jwt` + `@require_session` + `@require_company` (inalterado) |
| **Autorização** | Inalterada — qualquer usuário autenticado com acesso à(s) `company_ids` solicitada(s) |
| **Novos parâmetros de query** | `creci_number` (string, `ilike`), `creci_state` (string, 2 caracteres, normalizado para maiúsculas) |

**Endpoint: `GET /api/v1/profiles/<int:profile_id>` (modificado)**

| Atributo | Valor |
|-----------|-------|
| **Autorização** | Inalterada |
| **Resposta 200 (estendida, para `profile_type=='agent'`)** | Inclui sub-objeto `agent` completo (ver esboço acima) |

**Endpoint: `PUT /api/v1/profiles/<int:profile_id>` (modificado)**

| Atributo | Valor |
|-----------|-------|
| **Autorização** | Inalterada (comportamento já existente de `update_profile`, sem checagem de grupo hoje — fora de escopo desta spec endurecer autorização de `PUT`, apenas de `DELETE`/`reactivate`, conforme decisão do usuário) |
| **Corpo da Requisição (campos novos, opcionais, só têm efeito se `profile_type=='agent'`)** | `creci`, `bank_name`, `bank_account`, `bank_account_type`, `bank_branch`, `pix_key` |

**Respostas de Erro (novas, FR5)**:
| Código | Condição | Resposta |
|------|-----------|----------|
| 400 | `creci` malformado (menos de 4 caracteres) para perfil `agent` | `{"success": false, "error": "validation_error", ...}` |
| 409 | `creci` já usado por outro agente ativo na mesma empresa | `{"success": false, "error": "conflict", ...}` |

**Endpoint: `DELETE /api/v1/profiles/<int:profile_id>` (modificado — autorização endurecida, breaking change, FR3)**

| Atributo | Valor |
|-----------|-------|
| **Autorização (NOVA)** | `owner` OU `base.group_system` (admin) — para **qualquer** `profile_type`. Manager e Director NÃO são autorizados (ver FR3.1 para a justificativa — ADR-019/ACL de `res.users` Owner-only + matriz de convite da Feature 009) |
| **Autorização (ANTES desta feature)** | Nenhuma checagem de grupo |
| **Resposta 403 (nova)** | `{"success": false, "error": "forbidden", "message": "Only the company owner or a system admin can deactivate profiles"}` |

**Endpoint: `POST /api/v1/profiles/<int:profile_id>/reactivate` (novo, FR2)**

| Atributo | Valor |
|-----------|-------|
| **Método** | POST |
| **Caminho** | `/api/v1/profiles/<int:profile_id>/reactivate` |
| **Autenticação** | `@require_jwt` + `@require_session` + `@require_company` |
| **Autorização** | `owner` OU `base.group_system` (mesma matriz restrita de `DELETE` — Manager/Director não autorizados) |

**Corpo da Requisição**: nenhum (o reason de deactivation é limpo automaticamente; não há um "reason" de reativação).

**Resposta de Sucesso (200)**:
```json
{
  "success": true,
  "data": {
    "id": 42,
    "active": true,
    "deactivation_date": null,
    "deactivation_reason": null,
    "agent": {
      "id": 88,
      "active": true,
      "deactivation_date": null,
      "deactivation_reason": null,
      "user_id": 15
    },
    "_links": {
      "self": "/api/v1/profiles/42",
      "deactivate": "/api/v1/profiles/42"
    }
  },
  "message": "Profile reactivated successfully"
}
```

**Respostas de Erro**:
| Código | Condição | Resposta |
|------|-----------|----------|
| 400 | Perfil já ativo | `{"success": false, "error": "validation_error", "message": "Profile is already active"}` |
| 403 | Solicitante sem grupo `owner`/admin (inclui Manager e Director) | `{"success": false, "error": "forbidden", ...}` |
| 404 | Perfil não encontrado, ou de empresa diferente (anti-enumeração) | `{"success": false, "error": "not_found", ...}` |
| 500 | Falha inesperada na cascata (agent/user) — rollback completo | `{"success": false, "error": "internal_error", ...}` |

**Endpoints removidos diretamente, sem janela de descontinuação (FR4, FR6)**:

| Endpoint | Status até a remoção | Status após a remoção |
|----------|----------------------|------------------------|
| `GET /api/v1/agents` | Inalterado | Removido — 404 |
| `GET /api/v1/agents/<id>` | Inalterado | Removido — 404 |
| `PUT /api/v1/agents/<id>` | Inalterado | Removido — 404 |
| `POST /api/v1/agents/<id>/deactivate` | Inalterado | Removido — 404 |
| `POST /api/v1/agents/<id>/reactivate` | Inalterado | Removido — 404 |

**Endpoints explicitamente NÃO tocados por esta spec** (fora de escopo, ver seção correspondente): `GET /api/v1/agents/<id>/properties`, `GET /api/v1/agents/<id>/performance`, `GET|POST /api/v1/agents/<id>/commission-rules`, `GET /api/v1/agents/ranking`, `POST /api/v1/assignments` e demais rotas de `assignments`/`commission-rules`/`commission-transactions`.

### Dados de Seed (OBRIGATÓRIO — todos os tipos de solução)

```python
# Empresas (isolamento)
seed_company_a = env['res.company'].create({'name': 'Empresa A (Seed 027)'})
seed_company_b = env['res.company'].create({'name': 'Empresa B (Seed 027)'})

# Usuários por papel (empresa A) — cobre a matriz de autorização restrita (FR3: só owner/admin)
# NOTA: cada entrada abaixo tem tanto um papel de "solicitante" (usado nos testes de
# autorização de US1/US2) quanto, quando aplicável, um "perfil-alvo" com res.users +
# sessão Redis ativa vinculados (usado por test_deactivate_invalidates_active_session_
# across_all_profile_types() -- ver Cobertura de Testes da US1). Um Owner/admin distinto
# (nunca o próprio alvo) é quem chama o DELETE em cada caso desse teste.
seed_users = {
    'owner_a':           {'login': 'seed_owner_a_027@test.com',           'group': 'group_real_estate_owner'},        # SEM group manager explícito -- testa FR3.2; ÚNICO papel (além de admin) autorizado a deactivate/reactivate; TAMBÉM usado como alvo no teste de invalidação de sessão (owner desativando outro owner)
    'director_a':        {'login': 'seed_director_a_027@test.com',        'group': 'group_real_estate_director'},     # NÃO autorizado a deactivate/reactivate (FR3.1) -- usado em test_manager_and_director_cannot_deactivate_any_profile_type; TAMBÉM usado como alvo (perfil director) no teste de invalidação de sessão
    'manager_a':         {'login': 'seed_manager_a_027@test.com',         'group': 'group_real_estate_manager'},      # NÃO autorizado a deactivate/reactivate (FR3.1) -- usado no mesmo teste de regressão que director_a; TAMBÉM usado como alvo (perfil manager) no teste de invalidação de sessão
    'agent_requester_a': {'login': 'seed_agent_requester_a_027@test.com', 'group': 'group_real_estate_agent'},        # usado para testar 403 no delete/reactivate (nunca foi autorizado)
    'receptionist_a':    {'login': 'seed_receptionist_a_027@test.com',    'group': 'group_real_estate_receptionist'}, # usado para testar 403 em profile_type != agent (nunca foi autorizado); TAMBÉM usado como alvo (perfil receptionist) no teste de invalidação de sessão
    'owner_b':           {'login': 'seed_owner_b_027@test.com',           'group': 'group_real_estate_owner'},        # empresa B, isolamento -- Owner de B não pode agir sobre perfis de A
}

# Perfil + agente ATIVO, com res.users e sessão ativa (empresa A) — usado pelo fluxo de deactivate (US1)
# e como o caso "agent" de test_deactivate_invalidates_active_session_across_all_profile_types()
seed_profile_active_agent = env['thedevkitchen.estate.profile'].create({
    'name': 'Seed Active Agent', 'company_id': seed_company_a.id,
    'profile_type_id': agent_profile_type.id,
    'document': '<CPF válido>', 'email': 'seed_active_agent_027@test.com',
    'birthdate': '1990-01-01',
})
# real.estate.agent é auto-criado por profile_api.py (Feature 010/026); vincular user_id
# via fluxo de convite (Feature 026) para simular um agente totalmente funcional.

# Perfil + res.users, sem agente, ATIVO (empresa A) — o caso "tenant" de
# test_deactivate_invalidates_active_session_across_all_profile_types(): perfis
# tenant/property_owner só têm res.users vinculado se de fato convidados (o vínculo é
# opcional para TODO profile_type, não uma regra especial de tenant -- ver invite_service.py,
# create_portal_user() é código morto, tenant/property_owner passam pelo mesmo invite_user()
# genérico). Este seed representa um tenant já convidado, com login e sessão ativos.
seed_profile_tenant_with_user = env['thedevkitchen.estate.profile'].create({
    'name': 'Seed Tenant With User', 'company_id': seed_company_a.id,
    'profile_type_id': tenant_profile_type.id,
    'document': '<CPF válido>', 'email': 'seed_tenant_with_user_027@test.com',
    'birthdate': '1990-01-01',
})
# res.users + thedevkitchen.api.session ativos vinculados via fluxo de convite (Feature 026),
# igual ao seed_profile_active_agent acima.

# Perfil + agente JÁ INATIVO (empresa A) — usado pelo fluxo de reactivate (US2)
seed_profile_inactive_agent = env['thedevkitchen.estate.profile'].create({
    'name': 'Seed Inactive Agent', 'company_id': seed_company_a.id,
    'profile_type_id': agent_profile_type.id,
    'document': '<CPF válido>', 'email': 'seed_inactive_agent_027@test.com',
    'birthdate': '1990-01-01', 'active': False,
    'deactivation_date': '2026-01-01', 'deactivation_reason': 'Seed pré-desativado',
})

# Perfil NÃO-agent, SEM res.users vinculado (empresa A) — usado para provar que a
# autorização endurecida se aplica a QUALQUER profile_type, não só agent (FR3.2), e
# também como o caso "perfil sem res.users vinculado -> sem erro, sem tentativa de
# invalidação de sessão" de test_deactivate_invalidates_active_session_across_all_
# profile_types() -- distinto de seed_profile_tenant_with_user acima, que TEM login.
seed_profile_tenant = env['thedevkitchen.estate.profile'].create({
    'name': 'Seed Tenant', 'company_id': seed_company_a.id,
    'profile_type_id': tenant_profile_type.id,
    'document': '<CPF válido>', 'email': 'seed_tenant_027@test.com',
    'birthdate': '1990-01-01',
})

# Agente existente com CRECI cadastrado (empresa A) — usado no teste de conflito 409 do PUT
seed_agent_existing_creci = env['real.estate.agent'].search(
    [('creci_normalized', '=', 'CRECI/SP 99999')], limit=1
) or env['real.estate.agent'].create({
    'name': 'Seed Agent Existing Creci', 'cpf': '<CPF válido>',
    'email': 'seed_agent_existing_creci_027@test.com',
    'company_id': seed_company_a.id, 'creci': 'CRECI-SP-999999-J',
})

# Perfil + agente em empresa B — isolamento multi-tenant
seed_profile_agent_b = env['thedevkitchen.estate.profile'].create({
    'name': 'Seed Agent B', 'company_id': seed_company_b.id,
    'profile_type_id': agent_profile_type.id,
    'document': '<CPF válido>', 'email': 'seed_agent_b_027@test.com',
    'birthdate': '1990-01-01',
})
```

> **Regras**: prefixo `seed_` em todos os IDs/logins; criação idempotente (`search()` antes de `create()`); cada critério de aceitação acima tem um registro de seed correspondente como ponto de partida.

---

### Requisitos Não-Funcionais

**NFR1: Segurança** (conforme ADR-008, ADR-011, ADR-017, ADR-019)
- `DELETE /profiles/<id>` e `POST /profiles/<id>/reactivate` passam a exigir autorização de grupo explícita (`owner` OU `admin` — **Manager e Director explicitamente excluídos**) para **qualquer** `profile_type` — mudança de comportamento breaking, documentada na seção dedicada acima e no OpenAPI. A exclusão de Manager/Director é intencional e mais restritiva do que a primeira versão desta spec cogitava, por conflitar com (a) ADR-019 + `security/groups.xml` + `security/ir.model.access.csv` (gerenciar `res.users` é regra Owner-only, sem nenhuma ACL de Manager/Director sobre esse modelo) e (b) a matriz de convite já implementada (`specs/009-user-onboarding-password-management/spec.md`), onde Manager nunca atua sobre perfis de nível igual ou superior.
- A checagem de autorização verifica o grupo `owner` explicitamente, nunca dependendo de `implied_ids` de `manager` — fecha a classe de bug já presente no `agent_api.py` legado (Owner sem grupo manager explícito sendo barrado).
- Anti-enumeração entre empresas (404, não 403) preservada em todos os endpoints tocados, idêntica ao padrão já existente de `get_profile`/`delete_profile`.
- Reativação nunca restaura sessões Redis previamente invalidadas — login novo é sempre exigido após reativação, preservando a garantia de segurança que o `delete_profile` original introduziu.
- **Invalidação proativa de sessão em `DELETE /profiles/<id>`, agora coberta por teste para todo `profile_type` com `res.users` vinculado**: este comportamento não é introduzido por esta spec — já existe desde a Feature 023 (Redis Session Cache), documentado em `specs/023-redis-session-cache/spec.md` (Q&A, "Quando um perfil é desativado via API... a invalidação das sessões ativas deve ser imediata (proativa) ou reativa? → Proativa. O endpoint deve buscar e invalidar explicitamente todas as sessões ativas do `res.users` vinculado ao perfil desativado, sem aguardar a próxima requisição"), implementado em `thedevkitchen_apigateway/models/api_session.py::write()` (dispara invalidação de cache Redis no mesmo request quando `is_active`/`company_id` muda) e `services/session_validator.py::validate()` (cache HIT/MISS com fallback ao banco, garantindo `401` imediato sem depender do TTL). O que esta spec (027) faz é **ampliar o escopo do endpoint** que já tinha essa garantia (antes só exercitada por `agent` em testes) para cobrir explicitamente qualquer `profile_type` com login, já que `DELETE /profiles/<id>` agora é o único caminho canônico de deactivate para todos os tipos — ver `test_deactivate_invalidates_active_session_across_all_profile_types()` (User Story 1).

**NFR2: Performance** (conforme `knowledge_base/performance.md` — análise específica desta feature)
- **Volume de dados**: list/get de agentes via `/profiles` é uma operação administrativa de frequência baixa-média (dezenas a centenas de chamadas/dia por empresa), não um hot-path de autenticação por requisição.
- **Padrão de consulta/indexação**: os novos filtros `creci_number` (`ilike`) e `creci_state` (igualdade) atuam sobre campos computados/armazenados **sem índice dedicado** (`creci_number`, `creci_state` — apenas `creci_normalized` tem `index=True`). Dado o volume esperado (dezenas a poucas centenas de linhas de `real.estate.agent` por empresa) e a baixa frequência de uso desses filtros (busca administrativa pontual, não um filtro de toda listagem), **não** se justifica adicionar índice novo nesses dois campos agora — mesma lógica de dimensionamento já usada pela Feature 026 para `user_id`. Reconsiderar apenas se o volume por empresa crescer para milhares de linhas ou se o profiling mostrar uso frequente desse filtro.
- **Risco de N+1 (achado real, corrigido nesta spec, não apenas descrito)**: `_serialize_profile` já fazia, desde a Feature 010/024, uma busca (`search()`) individual em `real.estate.agent` por linha ao montar `agent_id`/`_links.agent` para cada perfil do tipo `agent` em uma lista paginada — um N+1 latente de até 100 queries extras por página (limite máximo de paginação). Esta spec **amplia** o que é embutido (todo o sub-objeto `agent`, FR1.3) e, por isso, tem a obrigação de resolver esse N+1 em vez de apenas piorá-lo: FR1.4 exige uma única busca em lote (`profile_id in [...]`) por chamada de `list_profiles`, com um dicionário `profile_id → agent` repassado para `_serialize_profile`. `get_profile` (registro único) não tem esse risco — mantém a busca individual já existente.
- **Aplicabilidade de cache-aside Redis**: não aplicável — leituras administrativas de baixa frequência, não um hot-path de autenticação por requisição (não se qualifica para o padrão de cache JWT/sessão da Feature 023).
- **Offload assíncrono/Celery**: não aplicável — todas as operações desta feature (list/get/put/delete/reactivate) são CRUD síncrono simples, sem processamento pesado ou de longa duração; a cascata de reactivate (profile→agent→user) deve permanecer **síncrona** e na mesma transação (garantia de atomicidade, FR2.7) — mover para Celery quebraria essa garantia (mesmo raciocínio já aplicado pela Feature 026 à criação de agente durante o convite).
- Meta: tempo de resposta p95 de `GET /profiles`/`GET /profiles/<id>` permanece `< 200ms` mesmo com o sub-objeto `agent` embutido, graças à correção de N+1 (FR1.4); `DELETE`/`POST reactivate` permanecem `< 300ms` (cascata de até 3 escritas + 1-2 buscas indexadas).

**NFR3: Qualidade** (conforme ADR-022)
- Código deve passar: black, isort, flake8 (`18.0/lint.sh`).
- Pylint ≥ 8.0/10.
- 100% de cobertura de testes nas validações novas/modificadas (schema de campos de agente em update, matriz de autorização restrita owner/admin — incluindo os testes de regressão de Manager/Director, cascata de reactivate).

**NFR4: Integridade de Dados** (conforme knowledge_base/09-database-best-practices.md)
- 3FN preservada — nenhuma nova coluna, nenhuma duplicação de dado.
- Soft delete (ADR-015) reforçado: agora `deactivate`/`reactivate` têm um único caminho canônico por perfil (`/profiles/<id>`), eliminando o caminho paralelo divergente (`/agents/<id>/deactivate|reactivate`) que não cascateava corretamente.
- Atomicidade: FR2.7 é a garantia central para o novo endpoint de reactivate — nenhum estado parcial profile-ativo-mas-agent/user-inativo.

**NFR5: Compatibilidade com Frontend**
- Não aplicável — feature apenas de API (Modelo de Acesso: apenas o usuário `admin` do Odoo acessa a UI do Odoo). Nenhuma view/menu introduzido ou modificado. Nenhum teste Cypress necessário.

---

## Restrições Técnicas

### Deve Seguir (das ADRs & Knowledge Base)

| Fonte | Requisito | Aplicado a |
|--------|-------------|------------|
| ADR-004 | `quicksol_estate`/`real.estate.agent` seguem a exceção legada já documentada — não renomeados | Nomes de modelo |
| ADR-005 | Regeneração de OpenAPI confirmando ausência total das 5 rotas removidas e presença do novo `POST /profiles/<id>/reactivate`, com a mudança de autorização do `DELETE` documentada como breaking | `docs/openapi/` |
| ADR-007 | HATEOAS — `_links.agent` corrigido para apontar a `/api/v1/profiles/{id}`, sub-recursos de agente ainda válidos (`properties`/`performance`/`commission-rules`) linkados dentro do sub-objeto `agent` | Serialização |
| ADR-008 | Isolamento entre empresas preservado em todos os endpoints tocados (404 anti-enumeração) | Controllers |
| ADR-009 | Modelo de autenticação headless — endpoints conduzidos via frontend headless (list/get/update por owner/manager/director/agent conforme a operação; deactivate/reactivate restrito a owner/admin, FR3) | Modelo de Acesso |
| ADR-011 | Triplo decorador em todos os endpoints tocados e no novo `reactivate` | Controllers |
| ADR-015 | Soft delete — caminho único e consistente (profile→agent→user) | `DELETE`/`reactivate` |
| ADR-016 | Atualização de coleção Postman — remoção direta dos requests legados de agent, adição do novo request "Reactivate Profile" | `docs/postman/` |
| ADR-018 | Validação de schema para os novos campos de `PUT /profiles/<id>` | `SchemaValidator` |
| ADR-019 | RBAC — matriz de autorização unificada e endurecida (owner/admin apenas, alinhada à regra Owner-only de gestão de `res.users` que a própria ADR-019 já documenta para Manager/Director), aplicada uniformemente a todo `profile_type` | Autorização |
| ADR-022 | Padrões de lint | Todo código modificado |
| ADR-024 | Perfil como fonte única de verdade — esta spec completa a migração de list/get/update/deactivate/reactivate para `/profiles`, deixada pendente pela unificação de cadastro (Feature 026) | Arquitetura |
| Constituição §"Padrão de Identidade com Vínculo Duplo" (introduzido na 026) | Reactivate deve definir/preservar tanto `profile_id` quanto `user_id` corretamente na cascata | `POST /profiles/<id>/reactivate` |
| Constituição §"Substituição Direta em vez de Janela de Descontinuação" (introduzido na 026) | Reaproveitado para a remoção das 5 rotas de `/agents` desta spec | FR4/FR6 |
| `.claude/rules/git-workflow.md` | Merge em `develop`/`master` só com autorização explícita do usuário | Processo de implementação/rollout |

### Padrões Arquiteturais

- **Padrão de Controller**: Conforme `.github/instructions/controllers.instructions.md`
- **Padrão de Testes**: Conforme `.github/instructions/test-strategy.instructions.md`
- **Implementação de Referência**: Feature 010/024 (perfil unificado, `_serialize_profile`, cascata de `update_profile`/`delete_profile`) + Feature 026 (validação condicional de campos de agente por `profile_type`, upsert atômico, padrão de identidade com vínculo duplo, substituição direta sem janela de descontinuação) — os padrões mais próximos que esta feature reaproveita e estende, não reescreve.

---

## Critérios de Sucesso

### Backend
- [ ] As 4 user stories implementadas e testadas
- [ ] Autorização endurecida de `DELETE`/`reactivate` coberta por teste explícito para não-manager em QUALQUER `profile_type` (não só agent) — o teste que documenta a mudança breaking
- [ ] Owner sem grupo manager explícito consegue desativar/reativar perfis (fecha a classe de bug do `agent_api.py` legado)
- [ ] Sub-objeto `agent` em `GET /profiles`/`GET /profiles/<id>` com paridade total de campos com o `GET /agents`/`GET /agents/<id>` legado
- [ ] N+1 de `_serialize_profile` corrigido para listagem (busca em lote), não apenas ampliado
- [ ] Filtros `creci_number`/`creci_state` funcionando em `GET /profiles`
- [ ] `PUT /profiles/<id>` sincroniza campos exclusivos de agente condicionalmente a `profile_type=='agent'`
- [ ] Novo `POST /profiles/<id>/reactivate` com cascata completa e atômica, sem restaurar sessões
- [ ] `GET /agents`, `GET /agents/<id>`, `PUT /agents/<id>`, `POST /agents/<id>/deactivate`, `POST /agents/<id>/reactivate` removidos diretamente e retornando 404
- [ ] Links mortos em `invite_controller.py`/`sale_api.py` corrigidos para apontar a `/api/v1/profiles/{id}`
- [ ] Isolamento multi-empresa verificado em todos os endpoints tocados
- [ ] Qualidade de código: Pylint ≥ 8.0, todos os linters passando (ADR-022)
- [ ] Merge na `develop` somente após autorização explícita do usuário

### Frontend
- Não aplicável (feature apenas de API; ver NFR5).

### Seeds
- [ ] Seed cobre owner (sem grupo manager explícito, único autorizado a deactivate/reactivate além do admin), director e manager (usados nos testes de regressão de 403), agent-solicitante, receptionist, em duas empresas (owner_a/owner_b para isolamento)
- [ ] Seed inclui perfil+agente ativo, perfil+agente já inativo, perfil não-agent com login (`tenant_with_user`), perfil não-agent sem login (`tenant`), agente com CRECI cadastrado (conflito)
- [ ] Seed cobre, com `res.users` + sessão Redis ativa vinculados, pelo menos um perfil de cada `profile_type` exercitado em `test_deactivate_invalidates_active_session_across_all_profile_types()`: `agent`, `manager`, `director`, `owner`, `tenant`, `receptionist`
- [ ] Seed é idempotente
- [ ] Testes de API usam os registros de seed como estado inicial

### Documentação
- [ ] Swagger/OpenAPI regenerado (ADR-005), com a mudança de autorização do `DELETE /profiles/<id>` documentada como breaking change — skill `swagger-updater`
- [ ] Coleção Postman atualizada (ADR-016): requests legados de agent removidos, novo request "Reactivate Profile" adicionado — skill `postman-collection-manager`
- [ ] Fluxogramas de jornada em `specs/027-agent-profile-endpoint-unification/flowcharts.md` (um por user story)

---

## Feedback de Constituição

### Novos Padrões Introduzidos

| Padrão | Descrição | Seção da Constituição | Prioridade |
|---------|-------------|---------------------|----------|
| **Checagem de Grupo Explícita para Owner (Owner ≠ implica Manager)** | Ao autorizar uma ação restrita ao Owner, checar `owner OR admin` explicitamente, nunca assumir que checar apenas `manager` cobre `owner` via `implied_ids` — `group_real_estate_owner` não implica `group_real_estate_manager` neste projeto | Nova subseção em "RBAC/Multi-Tenancy by Design" | Alta — esta classe de bug (autorização incompleta por herança de grupo assumida) já existe hoje em `agent_api.py` legado e pode recorrer em outros endpoints |
| **Gestão de `res.users` é Owner-only, mesmo indiretamente (via cascata)** | Qualquer endpoint que cascateie para `res.users.active` (ou outro campo de `res.users`) herda a mesma restrição de autorização já codificada para gestão direta de usuários (ADR-019 + `security/ir.model.access.csv`: só Owner/admin) — Manager e Director, mesmo com CRUD amplo sobre `profile`/`agent`, não ganham autorização sobre `res.users` só porque o endpoint é nominalmente sobre "profile" | Nova subseção em "RBAC/Multi-Tenancy by Design" | Alta — regra a aplicar a qualquer futuro endpoint que toque `res.users` transitivamente |
| **Endurecimento Deliberado de Autorização como Correção Transversal (com verificação cruzada de matrizes já existentes)** | Quando uma inconsistência de autorização é encontrada entre um caminho já protegido (agent) e um caminho legado desprotegido (profile genérico), a correção pode legitimamente ser aplicada de forma ampla (a todos os tipos afetados) — mas a matriz de papéis resultante DEVE ser cruzada com toda ACL (`ir.model.access.csv`) e matriz de autorização já implementada (ex.: convite, Feature 009) que toquem as mesmas entidades, antes de ser fechada; um "endurecimento amplo" ingênuo pode reintroduzir uma permissão que outra parte do sistema já nega deliberadamente | Nova subseção em "Padrões Arquiteturais" | Média |

### Novas Entidades/Relacionamentos

Nenhuma — esta feature completa a consolidação de list/get/update/deactivate/reactivate na entidade já unificada `thedevkitchen.estate.profile`.

### Decisões Arquiteturais

| Decisão | Justificativa | ADR Necessária? |
|----------|-----------|---------------|
| Autorização de `DELETE`/`reactivate` de perfil endurecida para TODOS os `profile_type`, não só `agent` | Decisão explícita do solicitante — eliminar a inconsistência de segurança entre agent (protegido) e demais tipos (desprotegidos) de uma vez, aceitando o custo de uma mudança breaking documentada | Não — capturado nesta spec (FR3); comportamento documentado como breaking no OpenAPI |
| Reactivate nunca restaura sessões Redis invalidadas | Mantém a garantia de segurança original do `delete_profile` (Feature 015/017) — reativação de conta não deve reviver um token/sessão potencialmente comprometido | Não — extensão do princípio já estabelecido de invalidação de sessão |
| Remoção direta (sem janela de descontinuação) de 5 rotas de `/agents` | Mesmo precedente já aceito pela Feature 026 ("Substituição Direta em vez de Janela de Descontinuação") | Não — padrão já documentado, reaplicado |

### Recomendação de Atualização da Constituição

- **Atualização Necessária**: Sim (após implementação validada)
- **Bump de Versão Sugerido**: MINOR
- **Seções a Atualizar**:
  - [ ] RBAC/Multi-Tenancy by Design → adicionar "Checagem de Grupo Explícita para Owner (Owner ≠ implica Manager)"
  - [ ] RBAC/Multi-Tenancy by Design → adicionar "Gestão de `res.users` é Owner-only, mesmo indiretamente (via cascata)"
  - [ ] Padrões Arquiteturais → adicionar "Endurecimento Deliberado de Autorização como Correção Transversal (com verificação cruzada de matrizes já existentes)"
  - [ ] Implementações de Referência → adicionar entrada da Feature 027

---

## Suposições & Dependências

**Suposições**:
- A Feature 026 está implementada e mesclada (ou pelo menos totalmente disponível no branch base desta feature) — esta spec depende do upsert de agente, do vínculo `user_id`, e da validação condicional de campos de agente em `create_profile`/`update_profile` já existirem.
- `PUT /api/v1/profiles/<id>` em si não recebe endurecimento de autorização nesta spec — só `DELETE`/`reactivate` — por decisão explícita do usuário (a pergunta de esclarecimento foi restrita a deactivate/reactivate).
- O achado de segurança sobre isolamento cross-company em `invite_user` (candidato a spec própria, documentado na 026) permanece aberto e não é resolvido aqui.

**Dependências**:
- Módulos existentes: `quicksol_estate` (`profile_api.py`, `agent_api.py`, `models/agent.py`, `models/profile.py`), `thedevkitchen_user_onboarding` (`invite_controller.py`, link a corrigir), `thedevkitchen_apigateway` (decoradores de autenticação, geração de OpenAPI, registro de endpoints, sessões Redis)
- Serviços externos: PostgreSQL 16 (transações atômicas), Redis 7 (invalidação de sessão, já usada por `delete_profile`, não estendida por esta feature — só sua cobertura de teste é ampliada)
- Trabalho prévio: `specs/026-user-agent-registration-unification/spec-idea.md` (base direta desta spec); `specs/023-redis-session-cache/spec.md` (decisão de invalidação proativa de sessão, reaproveitada e agora testada para todo `profile_type`)

---

## Fases de Implementação

### Fase 1: Fundação
- Estender `SchemaValidator` com `PROFILE_AGENT_UPDATE_FIELDS_SCHEMA` (reaproveitando constraints de `AGENT_CREATE_SCHEMA` por referência)
- Testes unitários de schema (sucesso + falha por campo)

### Fase 2: Camada de API — List/Get (User Story 3)
- Estender `_serialize_profile` com sub-objeto `agent` (paridade de campos) e correção de N+1 via busca em lote em `list_profiles`
- Adicionar filtros `creci_number`/`creci_state` a `list_profiles`
- Corrigir `_links.agent` para apontar a `/api/v1/profiles/{id}`

### Fase 3: Camada de API — Update (User Story 4)
- Estender `update_profile` para validar/sincronizar campos exclusivos de agente condicionalmente a `profile_type=='agent'`
- Rollback explícito + mapeamento 409 para conflito de `creci`

### Fase 4: Camada de API — Deactivate/Reactivate (User Stories 1 e 2)
- Adicionar checagem de autorização restrita a `owner`/`admin` a `delete_profile` (breaking change — remove Manager/Director do acesso hoje irrestrito)
- Implementar `POST /profiles/<id>/reactivate` com cascata atômica profile→agent→user, sem restaurar sessão

### Fase 5: Correção de Links Mortos
- Atualizar `invite_controller.py:214` e `sale_api.py:88` para apontar a `/api/v1/profiles/{id}`

### Fase 6: Testes & Qualidade
- Suíte completa das 4 user stories (unitário + E2E de API), incluindo o teste explícito de autorização breaking
- Gates de lint/qualidade (ADR-022)

### Fase 7: Documentação & Artefatos
- Regeneração de OpenAPI (documentando a mudança breaking de autorização) — skill `swagger-updater`
- Atualização de coleção Postman — skill `postman-collection-manager`
- Fluxogramas de jornada (`flowcharts.md`)
- Atualização de constituição

### Fase 8: Remoção de Rotas Legadas de `/agents` (após pré-condições — FR6.5)
- Confirmar pré-condições de remoção (User Stories 1–4 totalmente testadas; log de acesso de API sem tráfego inesperado)
- Excluir `list_agents`, `get_agent`, `update_agent`, `deactivate_agent`, `reactivate_agent` + rotas + registro `thedevkitchen.api.endpoint`
- Excluir testes substituídos
- Regenerar OpenAPI/Postman confirmando ausência
- **Merge na `develop` somente após confirmação explícita do usuário**

---

## Artefatos a Gerar

> **⚠️ OBRIGATÓRIO**: Consultar `.claude/skills/development-best-practices/SKILL.md` antes de implementar. Usar `.claude/skills/swagger-updater/SKILL.md` e `.claude/skills/postman-collection-manager/SKILL.md` para os respectivos artefatos — nunca editar manualmente os arquivos estáticos.

Após a aprovação da especificação, gerar:

1. **Atualização de Constituição** — "Checagem de Grupo Explícita para Owner", "Gestão de `res.users` é Owner-only, mesmo indiretamente" e "Endurecimento Deliberado de Autorização como Correção Transversal (com verificação cruzada de matrizes já existentes)"; recomenda-se rodar o subagente `thedevkitchen-speckit-project-constitution` assim que a implementação estiver validada.
2. **Tarefas Pós-Desenvolvimento**: OpenAPI (`docs/openapi/`) via `swagger-updater`; Coleção Postman via `postman-collection-manager`; Fluxogramas de jornada em `specs/027-agent-profile-endpoint-unification/flowcharts.md`.

---

## Checklist de Validação

### Validação de Backend
- [ ] "Fora de Escopo / Não-Objetivos" preenchido com itens específicos da feature
- [ ] Mudança de comportamento breaking (autorização) documentada de forma destacada e coberta por teste explícito
- [ ] Todos os requisitos de ADR referenciados e seguidos
- [ ] Padrões da knowledge base aplicados — análise de performance completa e baseada em código (N+1 real identificado e corrigido, não apenas descrito)
- [ ] Multi-tenancy corretamente especificada (ADR-008) — anti-enumeração preservada em todos os endpoints tocados
- [ ] Segurança devidamente definida (ADR-011, ADR-019) — checagem de grupo explícita restrita a `owner`/`admin`, cruzada com ACL de `res.users` e matriz de convite da Feature 009, sem depender de herança de grupo
- [ ] Estratégia de testes completa — unitário + E2E de API (ADR-003)
- [ ] Design de banco de dados normalizado — nenhuma nova coluna, 3NF preservada
- [ ] Tratamento de erros especificado (ADR-018) — 400/403/404/409/500 mapeados
- [ ] Requisitos de qualidade de código definidos (ADR-022)
- [ ] Links HATEOAS mortos identificados e corrigidos (`invite_controller.py`, `sale_api.py`)

### Validação de Frontend
- Não aplicável (feature apenas de API, nenhuma view/menu introduzido).
