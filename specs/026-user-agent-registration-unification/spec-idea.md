# Especificação de Feature: Unificar Cadastro de Usuários com o Onboarding de Corretores/Agentes

**Branch da Feature**: `026-user-agent-registration-unification`
**Criado em**: 2026-07-18
**Status**: Rascunho
**Referências de ADR**: ADR-004, ADR-005, ADR-007 (planejada, ainda não implementada nesses endpoints), ADR-008, ADR-009, ADR-011, ADR-012, ADR-015, ADR-016, ADR-018, ADR-019, ADR-022, ADR-024 (unificação de perfil)

---

## Relação com Trabalho Anterior (leia isto primeiro)

Este pedido ("Unificar cadastro de Usuários com as funcionalidades de corretores") mira **exatamente** a lacuna já analisada em `specs/025-agent-invite-unification/spec-idea.md`. Aquela spec foi totalmente desenhada, sua implementação foi mesclada (merge) na `develop`, e então foi **revertida no mesmo dia** — conforme o próprio histórico git do projeto (`d00211f chore(specs): remove feature 025 agent-invite-unification docs`): *"The feature was implemented, merged, and reverted the same day ... after being merged into develop without authorization ... net code effect was already zero."* Isso foi uma **falha de processo/governança** (um merge não autorizado na `develop`), não uma rejeição do design técnico. A inspeção de código realizada para esta spec (2026-07-18) confirma que a lacuna descrita em 025 ainda está **presente e inalterada no código atual** — `POST /api/v1/agents` ainda existe, e `POST /api/v1/users/invite` ainda não cria um registro `real.estate.agent`.

Esta spec (026) substitui a 025. Ela reaproveita a análise técnica da 025 (ainda válida) onde verificada contra o código atual, e **corrige uma lacuna materialmente importante que os próprios requisitos funcionais da 025 deixaram passar** (ver "Nova Descoberta" abaixo) — portanto não é uma reapresentação cega.

### Nova Descoberta ausente nos FRs da Feature 025 (verificado no código, 2026-07-18)

`real.estate.agent` tem **dois** campos distintos de vínculo com a identidade: `profile_id` (Many2one → `thedevkitchen.estate.profile`, Feature 010/024) e `user_id` (Many2one → `res.users`, "Link to user account if agent has system access"). O FR2 da Feature 025 ("Atomic Agent Record Creation During Invite") planejava definir apenas `profile_id` ao criar o registro `real.estate.agent` a partir do fluxo de convite — **nunca definia `user_id`**. Uma busca (grep) na base de código mostra que `agent_id.user_id` (NÃO `agent_id.profile_id`) é o campo efetivamente consultado por todo caminho de código de RBAC/notificação que restringe dados ao "agente atualmente logado":

- `quicksol_estate/controllers/property_api.py` (listagem de imóveis): `real.estate.agent.search([('user_id','=', user.id)])` → se vazio, **"Agent without agent record sees nothing"** (comentário do próprio código).
- `quicksol_estate/controllers/lead_api.py` (3 pontos de chamada): `domain.append(('agent_id.user_id', '=', user.id))` para o escopo de RBAC de listagem/detalhe de leads.
- `quicksol_estate/controllers/utils/serializers.py:641`: `property_record.agent_id.user_id == user` (checagem de propriedade usada na serialização).
- `quicksol_estate/models/proposal.py` (4 pontos de chamada): `comp.agent_id.user_id.partner_id.id` / `self.agent_id.user_id.partner_id.id` — destinatários de notificação de negociação de proposta/promoção de fila.
- `quicksol_estate/security/record_rules.xml`: `rule_agent_own_properties` (`agent_id.user_id = user.id`) e `rule_agent_own_assignments` (`agent_id.user_id = user.id`) — regras de registro (record rules) da UI Web do Odoo para acesso adjacente a `base.group_system`.

**Consequência se esta spec repetisse o FR2 da 025 ao pé da letra**: um agente convidado pelo fluxo unificado teria um login funcional (`res.users`) e um registro `real.estate.agent` (dados de CRECI/banco corretos, `profile_id` definido) — mas veria **zero imóveis, zero leads e receberia zero notificações de negociação de proposta**, porque toda consulta acima em `user_id` retornaria vazio. O bug que a 025 pretendia corrigir ("agentes com acesso de login mas sem registro de agente funcional") seria corrigido apenas *parcialmente*: o registro existiria, mas não seria *reconhecido* por nenhum código de RBAC/notificação que já depende dele. Esta spec torna `agent.user_id = new_user.id` um requisito de primeira classe, testado (FR2.1b abaixo), não uma consideração posterior.

---

## Correções de Escopo Direcionadas pelo Usuário (2026-07-18)

Duas decisões de escopo foram definidas explicitamente pelo solicitante para esta spec, substituindo os padrões correspondentes herdados do design da Feature 025 (e do primeiro rascunho desta própria spec), e são tratadas como requisitos definitivos a partir deste ponto do documento, não como questões em aberto:

1. ~~**Paridade total de campos para o nó `agent`.** O objeto aninhado `agent` em `POST /api/v1/users/invite` deve aceitar o MESMO conjunto de campos que `AGENT_CREATE_SCHEMA` (verificado literalmente em `quicksol_estate/controllers/utils/schema.py`, linhas 25-55) — não apenas `creci`/`hire_date`/`bank_name`/`bank_account`/`pix_key`, mas também `name`, `cpf`, `email`, `phone`, `mobile` — cada um validado com as mesmas restrições que `create_agent` já aplica.~~ **REVERTIDO (2026-07-23, correção direcionada pelo solicitante — de novo, após duas tentativas anteriores de esclarecimento nesta mesma conversa não terem sido suficientes):** o nó `agent` deve conter **apenas os campos exclusivos do registro `real.estate.agent` que não têm equivalente no perfil** — `creci`, `bank_name`, `bank_account`, `pix_key`. Os campos `name`, `cpf`, `email`, `phone`, `mobile` **e `hire_date`** foram removidos do nó: todos os seis já existem no `thedevkitchen.estate.profile` referenciado por `profile_id` (o "nó principal" do convite, verificado em `profile.py:80` para `hire_date`), que é a fonte de identidade compartilhada por **todos os `profile_type`** convidados por este mesmo endpoint (`owner`, `director`, `manager`, `agent`, `prospector`, `receptionist`, `financial`, `legal`, `property_owner`, `tenant`) — repeti-los dentro de um nó nominalmente "só de agente" não fazia sentido dado que o endpoint nunca foi exclusivo de agente. A justificativa original de "paridade total com `create_agent`" tratava o payload do endpoint legado como o modelo a replicar; a justificativa correta é o contrato do PRÓPRIO `POST /api/v1/users/invite`, que já resolve identidade via `profile_id` para qualquer tipo de perfil — `create_agent` não é (e nunca foi) esse contrato. Os únicos campos ainda excluídos do nó por razão de segurança (ADR-008) continuam sendo `company_id`/`user_id`, sempre derivados no servidor. Implementação: `SchemaValidator.AGENT_INVITE_SCHEMA` (`schema.py`) e `allowed_agent_keys` em `invite_controller.py::_upsert_agent_for_invite` restritos aos 4 campos exclusivos; testes unitários/integração atualizados; um cenário de teste (colisão de CPF via override) que dependia da capacidade removida foi redesenhado para semear um agente legado via SQL direto em vez de depender do payload do cliente.
2. **Remoção direta, sem janela de descontinuação (deprecation).** `POST /api/v1/agents` é removida definitivamente assim que o fluxo unificado (User Story 1) estiver implementado e validado — não há fase de headers `Deprecation`/`Sunset`, não há fase de `deprecated: true` no OpenAPI, e não há estágio de request do Postman re-rotulado mas ainda presente. Isso reverte a abordagem de descontinuar-depois-remover da Feature 025 (e do primeiro rascunho desta própria spec). O comportamento do endpoint permanece inalterado até o único passo de remoção definido na User Story 2 abaixo.

---

## Achado de Segurança Registrado Durante a Elaboração desta Spec (Fora de Escopo — 2026-07-18)

Ao investigar o fluxo de `invite_user` para responder a uma pergunta do solicitante sobre isolamento entre empresas, foi descoberto — e confirmado no código atual, não em suposição — que **`invite_user` não faz nenhuma checagem intencional entre o `company_id` do `profile_id` convidado e a(s) empresa(s) do solicitante**, para **nenhum** `profile_type` (não é específico de `agent` — é o mesmo endpoint genérico para todos: `owner`, `director`, `manager`, `agent`, `prospector`, `receptionist`, `financial`, `legal`, `property_owner`, `tenant`, governados pela mesma matriz `INVITE_AUTHORIZATION`, `invite_service.py:15-20`).

- `ProfileModel.sudo().search([("id", "=", int(profile_id))], limit=1)` (`invite_controller.py:56`) busca o perfil só pelo `id`, sem filtro de `company_id`.
- `create_user_from_profile` (`invite_service.py:189-256`) cria o `res.users` com `sudo()`, definindo `company_ids: [(4, profile.company_id.id)]`, mas **nunca define `company_id`** (singular) — que cai no padrão do Odoo (`self.env.company`, a empresa ativa **de quem está chamando**, não a do perfil).
- Isso faz com que `company_id` (empresa do solicitante) e `company_ids` (empresa do perfil-alvo) fiquem inconsistentes sempre que as duas empresas diferem, o que aciona a constraint nativa do Odoo `_check_company` (`res_users.py`, `@api.constrains('company_id', 'company_ids', ...)`) e a requisição falha com `ValidationError` → **HTTP 400** — rollback completo, nenhum estado parcial.
- **Isso não é uma proteção de aplicação intencional.** É um efeito colateral de um bug de preenchimento inconsistente de `company_id`/`company_ids`. Se um dia esse "bug" for corrigido de forma ingênua (ex.: também definir `user_vals['company_id'] = profile.company_id.id`, o que parece um ajuste razoável), os dois campos passam a bater, a constraint do Odoo para de disparar, e um convite entre empresas passa a **funcionar silenciosamente** — criando um login cross-tenant funcional sem nenhuma barreira. Nenhum campo `check_company=True` existe em `real.estate.agent`/`thedevkitchen.estate.profile` que ofereça uma segunda linha de defesa.

**Decisão do solicitante (2026-07-18)**: este achado é registrado aqui para visibilidade, mas fica **fora de escopo da spec 026** — não será corrigido como parte desta feature. Recomenda-se abrir uma spec própria (candidata a `specs/027-...`) para adicionar uma checagem explícita e intencional em `invite_user` (validar `profile_record.company_id` contra as empresas do solicitante antes de chamar `create_user_from_profile`, retornando 404 por anti-vazamento conforme ADR-008), cobrindo todos os `profile_type`, já que é o mesmo endpoint para todos. Até lá, o comportamento atual (bloqueio acidental via `ValidationError`/400, não um 404 intencional) permanece como está, inclusive para o fluxo de `agent` construído por esta spec.

---

## Achado de Implementação: `profile_api.py` Já Auto-Cria o `real.estate.agent` (Correção de Design — 2026-07-19)

Durante a implementação (Task 4 do plano), descobriu-se — e confirmou-se ao vivo via `odoo shell`, não apenas por leitura de código — que **`profile_api.py`** (`POST /api/v1/profiles`, código pré-existente da Feature 010, linhas 236-255, **não faz parte desta feature**) já cria automaticamente um registro `real.estate.agent` (com `profile_id`, `name`, `cpf`, `email`, `phone`, `mobile`, `company_id`, `hire_date` — mas `user_id` nulo) sempre que o perfil criado é do tipo `agent`. Isso invalidava uma suposição presente em todos os rascunhos anteriores desta spec (e do `design-idea.md`/`plan-idea.md` correspondentes): a de que `POST /api/v1/users/invite` seria o único ponto de criação do registro `real.estate.agent` para perfis do tipo `agent`.

**Consequência do design anterior**: um `real.estate.agent.create()` cego em `invite_user` (como as versões anteriores de FR2.1 especificavam) colide com o registro já existente na restrição `UNIQUE(cpf, company_id)` (`_sql_constraints`, `agent.py:218-224`) — gerando `psycopg2.errors.UniqueViolation`, que não é um `ValidationError` e portanto vazaria como 500 depois que `res.users`/token já tivessem sido criados na mesma transação, violando a garantia de atomicidade (FR2.2) que a própria spec exige.

**Correção adotada (confirmada pelo solicitante, 2026-07-19)**: FR2.1 passa a exigir semântica de **upsert** — buscar um `real.estate.agent` existente por `profile_id` antes de qualquer escrita; se encontrado (caso normal, dado o auto-create de `profile_api.py`), fazer `write()` com `user_id` + campos explícitos do objeto `agent`; se não encontrado (caso defensivo — perfil legado, ou comportamento futuro de `profile_api.py` alterado), criar do zero como o design original previa, reaproveitando o fallback de `create()` (FR1.4c). Ver FR2 (Requisitos), o esboço de código atualizado na seção Modelo de Dados, e `design-idea.md`/`plan-idea.md` (Task 4) para os detalhes completos. Alternativas consideradas e descartadas: remover o auto-create de `profile_api.py` (mudaria comportamento de um endpoint independente, fora de escopo) e apenas capturar `UniqueViolation`/retornar 409 (pararia o 500 mas não resolveria o problema real — o registro auto-criado continuaria sem `user_id`, falhando o propósito central desta feature).

---

## Correção de Design: Campos Exclusivos de Agente Movidos para `POST /api/v1/profiles` (2026-07-23)

**Nova percepção do solicitante, após a implementação já estar completa e testada**: o nó `agent` em `POST /api/v1/users/invite` (FR1/FR1.4, acima) não fazia sentido, ao se considerar que `POST /api/v1/profiles` é quem de fato cadastra os dados do indivíduo — inclusive, como já documentado na seção "Achado de Implementação" acima, `profile_api.py` **já cria automaticamente** o registro `real.estate.agent` no momento do cadastro do perfil. Os campos exclusivos de agente (`creci`, `bank_name`, `bank_account`, `pix_key`) não dependem de nada que só existe no momento do convite — eles não precisam do `user_id`/login. A única coisa que o convite genuinamente precisa fazer para um perfil do tipo `agent` é vincular o `user_id` ao registro `real.estate.agent` já existente.

**Mudança de arquitetura resultante:**
1. `POST /api/v1/profiles` passa a aceitar `creci`/`bank_name`/`bank_account`/`pix_key` como campos opcionais (sem efeito para qualquer `profile_type` que não seja `agent`) — o registro `real.estate.agent` auto-criado nasce **já completo**, exceto por `user_id`.
2. `POST /api/v1/users/invite` **perde o nó `agent` inteiramente**. O corpo da requisição passa a ser, para **todo** `profile_type` sem exceção, apenas `{"profile_id": <int>}`. A única coisa que este endpoint faz para um perfil do tipo `agent` é definir `user_id` no registro `real.estate.agent` já existente (achado via `profile_id`) — nenhum campo de creci/banco é lido, validado ou escrito por este endpoint.
3. Conflito de CRECI duplicado passa a ser detectado no **cadastro do perfil** (409 em `POST /api/v1/profiles`), não mais no convite — mais cedo no fluxo, mais perto do ponto de entrada do dado.
4. Se o CRECI não for conhecido no momento do cadastro, pode ser adicionado depois via `PUT /api/v1/agents/{id}` (endpoint de atualização, não removido — apenas o `POST` de criação legado foi removido nesta feature).

**Achado colateral corrigido durante esta mudança**: `profile_api.py::create_profile` não fazia rollback explícito em seu `except ValidationError` — inofensivo antes desta mudança (nenhum `@api.constrains` de `real.estate.agent` era exercitado no auto-create, já que nenhum campo com restrição própria como `creci` era passado). Ao mover a validação de CRECI para cá, um conflito de CRECI durante o auto-create do agente passaria a deixar o perfil já criado comitado mesmo com a resposta de erro (o commit implícito do Odoo ao final da requisição só é evitado quando uma exceção escapa sem ser capturada). Corrigido adicionando `request.env.cr.rollback()` no mesmo bloco, espelhando o padrão já usado em `invite_controller.py`.

**Consequência para os Requisitos abaixo**: FR1 (parágrafos sobre o nó `agent`) e a maior parte de FR2 (upsert com campos explícitos) descrevem a arquitetura ANTERIOR a esta correção — mantidos no documento por completude histórica, mas **substituídos** por esta seção onde conflitarem. O código, os testes e a documentação de Swagger/Postman já refletem a versão corrigida (verificado ao vivo, 2026-07-23) — ver `plan-idea.md` para o detalhamento tarefa-a-tarefa desta correção.

---

## Correção de Design: Validação de Campos de Agente Passa a Ser Condicional a `profile_type` (2026-07-23, segunda correção)

**Bug encontrado durante revisão do solicitante**, na correção acima: ao mover `creci`/`bank_name`/`bank_account`/`pix_key` para `PROFILE_CREATE_SCHEMA` (o schema genérico de `POST /api/v1/profiles`), a validação desses campos passou a rodar **incondicionalmente** para qualquer `profile_type` — `SchemaValidator.validate_request(body, PROFILE_CREATE_SCHEMA)` é chamado ANTES de `profile_type_id` ser resolvido para seu `code`. Consequência: um perfil `tenant` (ou qualquer tipo não-agent) com um `creci` malformado no payload era incorretamente rejeitado com 400, mesmo esse campo sendo irrelevante para esse `profile_type`.

**Correção aplicada:**
1. `PROFILE_CREATE_SCHEMA` voltou a NÃO conter `creci`/`bank_name`/`bank_account`/`pix_key` (nem em `optional`, `types` ou `constraints`).
2. Novo schema separado, `PROFILE_AGENT_FIELDS_SCHEMA` (e o método `SchemaValidator.validate_profile_agent_fields(data)`), contendo apenas esses 4 campos — reaproveitando as mesmas regras de `AGENT_CREATE_SCHEMA` por referência (não cópia), evitando divergência silenciosa entre as duas.
3. `profile_api.py::create_profile` agora só invoca `validate_profile_agent_fields` **depois** de confirmar `profile_type.code == "agent"` (e antes de qualquer escrita no banco, preservando fail-fast) — para qualquer outro `profile_type`, esses campos são simplesmente ignorados, mesmo se presentes e malformados no payload.

**Verificado ao vivo (2026-07-23)**: perfil `tenant` com `creci: "ab"` → 201 (aceito, campo ignorado, nenhum `real_estate_agent` criado); perfil `agent` com `creci: "ab"` → 400 (constraint de tamanho ainda aplicada); perfil `agent` com CRECI válido → 201 com `agent_id` criado normalmente. Coberto por `tests/unit/test_profile_create_agent_fields_unit.py` (reescrito para testar o novo schema) e por um novo cenário em `integration_tests/test_us026_s1_invite_other_profile_types.sh`.

---

## Resumo Executivo

**(Nota: este resumo descreve a versão JÁ CORRIGIDA do fluxo — ver "Correção de Design" acima para o que mudou e por quê.)**

Hoje, convidar um novo perfil "agent" via `POST /api/v1/users/invite` cria um login `res.users` vinculado a um registro `thedevkitchen.estate.profile`. Um registro de domínio `real.estate.agent` **já existe** nesse ponto — `profile_api.py` (Feature 010) o cria automaticamente no momento em que o perfil é criado, agora já incluindo `creci`/`bank_name`/`bank_account`/`pix_key` quando fornecidos no cadastro — mas fica **sem `user_id`**. Esta feature unifica os dois caminhos de onboarding — `POST /api/v1/agents` (registro apenas, sem login, removido ao final desta feature) e `POST /api/v1/users/invite` (login apenas, registro órfão sem `user_id`) — vinculando `user_id` ao registro `real.estate.agent` já existente no momento do convite. `POST /api/v1/users/invite` aceita **apenas `profile_id`**, para qualquer `profile_type`, sem exceção — não existe mais um objeto `agent` no corpo desta requisição. `POST /api/v1/agents` é removida definitivamente (sem janela de descontinuação) assim que o fluxo unificado estiver implementado e validado.

---

## Fora de Escopo / Não-Objetivos

**Fora de Escopo**:
- Tipos de perfil que não sejam `agent` (`owner`, `director`, `manager`, `prospector`, `receptionist`, `financial`, `legal`, `property_owner`, `tenant`) não são afetados — seu fluxo de convite permanece inalterado por esta feature. **Correção em relação a uma suposição anterior desta spec**: `tenant`/`property_owner` NÃO passam por um caminho separado já atômico — o método `create_portal_user` (`invite_service.py:116-187`) que faria isso é código morto, nunca chamado (verificado via grep em toda a base, 2026-07-18); `tenant`/`property_owner` passam pelo mesmíssimo `invite_user`/`create_user_from_profile` que `agent`, sem criação de nenhuma entidade de domínio adicional (o que é esperado, já que esses perfis não têm um registro de domínio equivalente a `real.estate.agent` a ser criado). Uma unificação futura para esses tipos, se necessária, é uma questão separada e não faz parte deste trabalho.
- Renomear `real.estate.agent` para um nome de modelo com prefixo `thedevkitchen_` está explicitamente fora de escopo (exceção legada aceita, constituição §12 item 5; uma renomeação é uma mudança não relacionada, de risco maior, que esta feature não deve incluir).
- Alterar as regras de registro (RBAC) de `real.estate.agent` ou a autorização de `group_real_estate_manager`-ou-admin no `create_agent` legado está fora de escopo antes da remoção (FR4.2) — os dois endpoints intencionalmente têm escopos de autorização diferentes pelo curto período em que ambos existem, até a remoção.
- Construir um fluxo de UI/Cypress para esta feature está fora de escopo — ambos os endpoints são apenas de API, consumidos exclusivamente pelo frontend headless (Modelo de Acesso: apenas o usuário `admin` do Odoo acessa a UI do Odoo).
- Preencher retroativamente o `user_id` em registros `real.estate.agent` criados pelo caminho legado `create_agent` (que nunca define `user_id`) está fora de escopo para esta spec — esses registros permanecem apenas-registro por design, a menos/até que uma feature separada de migração de dados seja especificada.

**Comportamentos Proibidos** (a implementação NÃO DEVE introduzir):
- [ ] NÃO DEVE enfraquecer o isolamento multi-tenant (ADR-008) — o novo objeto `agent` na requisição de convite NÃO DEVE aceitar `company_id`; ele é sempre derivado do perfil já validado (fecha um vetor de spoofing entre empresas).
- [ ] NÃO DEVE contornar ou remover a cadeia de triplo decorador (`@require_jwt` + `@require_session` + `@require_company`, ADR-011) em nenhum dos dois endpoints.
- [ ] NÃO DEVE substituir a convenção de soft-delete de `real.estate.agent` (ADR-015, campo `active`) por exclusão física (hard delete).
- [ ] NÃO DEVE criar um estado parcial — um `res.users` sem um `real.estate.agent` correspondente para um perfil do tipo `agent`, ou um `real.estate.agent` criado sem `profile_id` e `user_id` preenchidos quando o caminho de convite é usado (a garantia de rollback atômico, FR2.2, é inegociável).
- [ ] NÃO DEVE fazer merge de branches de implementação em `develop`/`master` sem autorização explícita do usuário (conforme a regra `git-workflow.md` deste repositório e a causa direta da reversão da Feature 025) — este é um requisito de processo, não de código, mas é o "known pitfall" mais relevante para esta feature exata e deve ser respeitado por quem implementar este plano.

**Armadilhas Conhecidas** (da tentativa revertida da Feature 025 e da própria revisão de código desta spec):
- A implementação da Feature 025 foi revertida por um **merge não autorizado na `develop`**, não por uma falha de design — não reinterprete a reversão como evidência de que a abordagem técnica está errada; a abordagem central daquela spec (objeto opcional aninhado `agent`, criação atômica) era sólida e é mantida aqui. O sequenciamento de descontinuar-depois-remover de `POST /api/v1/agents` da Feature 025 **não** é mantido aqui — esta spec remove o endpoint diretamente, por instrução explícita do solicitante (ver "Cenários de Usuário & Testes" e "Requisitos" abaixo).
- O FR2 da Feature 025 planejava definir apenas `real.estate.agent.profile_id` nos registros de agente criados pelo convite. Conforme documentado acima em "Nova Descoberta", isso sozinho deixa o agente invisível para toda checagem de RBAC/notificação baseada em `agent_id.user_id` em `property_api.py`, `lead_api.py`, `serializers.py`, `proposal.py` e `record_rules.xml`. **Qualquer implementação desta spec DEVE definir tanto `profile_id` quanto `user_id`** — não repita a omissão.
- `real.estate.agent.user_id` atualmente **não tem índice de banco de dados** (`fields.Many2one("res.users", ..., ondelete="restrict")`, sem `index=True`), apesar de ser lido em toda chamada de API de listagem de imóveis e leads por todo usuário do papel "agent" (`property_api.py`, `lead_api.py` ×3). A seção Modelo de Dados desta spec adiciona `index=True` para fechar essa lacuna — não pule isso como "apenas uma anotação de metadado".

---

## Cenários de Usuário & Testes

### User Story 1: Gestor convida um novo Agente com dados cadastrais + de licença completos, e o agente fica imediatamente totalmente funcional (Prioridade: P1) 🎯 MVP

**Como** Gestor (Manager), Proprietário (Owner) ou Diretor (Director) (conforme a matriz de autorização da ADR-024)
**Eu quero** convidar um novo agente e ter sua licença CRECI e dados bancários/de comissão capturados no mesmo fluxo, com o registro de agente resultante totalmente vinculado ao seu login
**Para que** o agente tenha acesso ao sistema E veja seus próprios imóveis/leads/notificações de proposta desde o momento em que definir sua senha — sem uma segunda etapa manual ou uma lacuna silenciosa de RBAC

**Critérios de Aceitação**:
- [ ] Dado um perfil com `profile_type_id.code == 'agent'` já criado via `POST /api/v1/profiles`, quando `POST /api/v1/users/invite` é chamado com `profile_id` e um objeto aninhado `agent` válido (`name`, `cpf`, `email`, `phone`, `mobile`, `creci`, `hire_date`, `bank_name`, `bank_account`, `pix_key` — todos opcionais, espelhando 1:1 o conjunto completo de campos de `AGENT_CREATE_SCHEMA`, exceto `company_id`/`user_id`, que nunca são aceitos do cliente), então a resposta é 201 e inclui `user.id`, `profile_id` e `agent_id`; existe um registro `real.estate.agent` com **tanto** `profile_id` definido para o perfil convidado **quanto** `user_id` definido para o id do `res.users` recém-criado.
- [ ] Dado o mesmo cenário, quando o objeto `agent` fornece `name`/`cpf`/`email`/`phone`/`mobile` explicitamente (substituindo os valores já presentes no perfil vinculado), então esses valores explícitos — não os do perfil — são os que ficam gravados no registro `real.estate.agent` criado, cada um validado com a mesma restrição usada por `create_agent` (`name` com 3-255 caracteres, `cpf` com verificação de 11 dígitos após remover `.`/`-`, `email` contendo `@` e `.`).
- [ ] Dado que o objeto `agent` está totalmente ausente OU presente mas omite parte ou todos de `name`/`cpf`/`email`/`phone`/`mobile`, quando `POST /api/v1/users/invite` é chamado, então esses campos omitidos usam como padrão os valores já validados no perfil vinculado (`profile_record.name`/`document`/`email`/`phone`/`mobile`) — o convite nunca falha por falta de campos de identidade, já que o perfil já os garante.
- [ ] Dado que o objeto `agent` inclui uma chave `company_id` ou `user_id`, quando `POST /api/v1/users/invite` é chamado, então essas chaves são silenciosamente ignoradas (não gera 400) — `company_id` é sempre derivado do `company_id` do perfil vinculado, e `user_id` é sempre o `res.users.id` recém-criado; nenhum valor enviado pelo cliente para qualquer um desses campos é persistido.
- [ ] Dado o mesmo cenário, quando o login do agente criado subsequentemente chama `GET /api/v1/properties` ou `GET /api/v1/leads`, então a consulta de escopo de RBAC (`real.estate.agent.search([('user_id','=', user.id)])` em `property_api.py`; `domain.append(('agent_id.user_id','=', user.id))` em `lead_api.py`) resolve para o novo registro de agente — o agente vê seus próprios imóveis/leads atribuídos, não uma lista vazia.
- [ ] Dado que `agent.creci` falha na validação de formato do `CreciValidator`, quando `POST /api/v1/users/invite` é chamado, então a resposta é 400 `validation_error` e **nenhum** registro `res.users`, token de convite ou `real.estate.agent` é criado (rollback atômico — reproduz a garantia atual de `create_agent`).
- [ ] Dado que `agent.creci` está bem formado mas já é usado por outro agente ativo na **mesma** `company_id`, quando `POST /api/v1/users/invite` é chamado, então a resposta é 409 `conflict` e nenhum registro é criado.
- [ ] Dado um perfil do tipo `agent` e nenhum objeto `agent` no corpo da requisição, quando `POST /api/v1/users/invite` é chamado, então um registro `real.estate.agent` ainda é criado (dados cadastrais obtidos do perfil; `user_id` ainda é vinculado) — a criação do registro de agente não pode ser pulada para perfis do tipo `agent`.
- [ ] Dado um perfil de uma empresa **diferente** da empresa ativa do solicitante (header `X-Company-ID`), quando `POST /api/v1/users/invite` é chamado, então a resposta é 400 `validation_error` — **não** um 404 intencional (ver "Achado de Segurança Registrado" acima: hoje isso falha apenas por acidente, via `ValidationError` nativa do Odoo de `company_id`/`company_ids` inconsistentes em `res.users`, não por uma checagem de aplicação; corrigir isso para um 404 real de anti-vazamento (ADR-008) está **fora de escopo** desta spec, por decisão do solicitante — ver spec candidata `027`). Este critério documenta o comportamento atual, não introduz uma correção.
- [ ] Dado que o solicitante é um usuário do grupo `agent` (não owner/director/manager), quando `POST /api/v1/users/invite` visa um perfil `agent`, então a resposta é 403 `forbidden` (ADR-024 inalterada — agentes não podem convidar outros agentes).

**Cobertura de Testes** (conforme ADR-003):

| Tipo | Nome do Teste | Descrição | Status |
|------|-----------|-------------|--------|
| Unitário | `test_invite_agent_creci_format_invalid()` | Validação de formato de CRECI rejeita o convite, nenhum registro é criado | ⚠️ Obrigatório |
| Unitário | `test_invite_agent_creci_uniqueness_same_company()` | CRECI duplicado dentro da mesma empresa é bloqueado (409) | ⚠️ Obrigatório |
| Unitário | `test_invite_agent_creci_allowed_across_companies()` | O mesmo número de CRECI é permitido em `company_id` diferente | ⚠️ Obrigatório |
| Unitário | `test_invite_agent_bank_fields_optional()` | Campos bancários ausentes → agente ainda é criado com valores em branco | ⚠️ Obrigatório |
| Unitário | `test_invite_agent_required_fields_from_profile()` | name/cpf/email/company_id usam o perfil como padrão via sincronização `setdefault()` quando o objeto `agent` os omite | ⚠️ Obrigatório |
| Unitário | `test_invite_agent_sets_user_id_link()` | **Novo**: o `real.estate.agent.user_id` criado é igual ao `res.users.id` recém-criado (não apenas `profile_id`) | ⚠️ Obrigatório |
| Unitário | `test_invite_agent_user_id_uniqueness_enforced()` | A restrição `_check_user_unique` ainda rejeita um segundo registro de agente para o mesmo `user_id`+`company_id` | ⚠️ Obrigatório |
| Unitário | `test_invite_non_agent_profile_unaffected()` | Tipos de perfil diferentes de `agent` pulam completamente o ramo de criação de agente | ⚠️ Obrigatório |
| Unitário | `test_invite_agent_full_field_parity_with_create_agent()` | **Novo**: o objeto `agent` aceita `name`/`cpf`/`email`/`phone`/`mobile` além dos campos bancários/CRECI, cada um validado com a mesma função de restrição que `AGENT_CREATE_SCHEMA` usa | ⚠️ Obrigatório |
| Unitário | `test_invite_agent_name_length_constraint()` | **Novo**: `agent.name` fora de 3-255 caracteres → 400, espelha a restrição de `name` do `create_agent` | ⚠️ Obrigatório |
| Unitário | `test_invite_agent_cpf_digit_count_constraint()` | **Novo**: `agent.cpf` sem exatamente 11 dígitos (após remover `.`/`-`) → 400, espelha a restrição de `cpf` do `create_agent` | ⚠️ Obrigatório |
| Unitário | `test_invite_agent_email_format_constraint()` | **Novo**: `agent.email` sem `@`/`.` → 400, espelha a restrição de `email` do `create_agent` | ⚠️ Obrigatório |
| Unitário | `test_invite_agent_overrides_profile_identity_fields()` | **Novo**: valores explícitos de `agent.name`/`cpf`/`email`/`phone`/`mobile` prevalecem sobre os valores do perfil vinculado no registro `real.estate.agent` criado | ⚠️ Obrigatório |
| Unitário | `test_invite_agent_company_id_and_user_id_ignored_in_node()` | **Novo**: as chaves `company_id`/`user_id` dentro do objeto `agent` são silenciosamente ignoradas — o `company_id` do registro criado corresponde ao do perfil, o `user_id` corresponde ao novo login, independentemente do que o cliente enviou | ⚠️ Obrigatório |
| Unitário | `test_invite_agent_company_id_derives_from_profile_not_user()` | **Novo**: quando `profile_id` e `user_id` são passados juntos a `create()` (caso desta feature), `company_id` reflete `profile.company_id`, não `user.company_ids[0]` — confirma a ordem de precedência entre os dois blocos de sincronização em `agent.py:436-470` (FR1.4c) | ⚠️ Obrigatório |
| E2E (API) | `test_manager_invites_agent_full_flow()` | criação de perfil → convite com objeto agent → usuário + agente + token existem, `agent.user_id == user.id` | ⚠️ Obrigatório |
| E2E (API) | `test_invited_agent_sees_own_properties()` | **Novo**: após definir a senha, `GET /api/v1/properties` do agente convidado retorna apenas seus imóveis atribuídos (não vazio) | ⚠️ Obrigatório |
| E2E (API) | `test_invited_agent_sees_own_leads()` | **Novo**: após definir a senha, `GET /api/v1/leads` do agente convidado retorna apenas seus próprios leads (não vazio) | ⚠️ Obrigatório |
| E2E (API) | `test_invite_agent_atomic_rollback_on_validation_failure()` | CRECI inválido → nenhum registro de `res.users` é confirmado (commit) | ⚠️ Obrigatório |
| E2E (API) | `test_multitenancy_isolation_invite_cross_company()` | Perfil da empresa B convidado por usuário da empresa A → 400 `validation_error` (bloqueio acidental atual via `_check_company` do Odoo, não um 404 intencional — ver "Achado de Segurança Registrado", fora de escopo desta spec) | ⚠️ Obrigatório |
| E2E (API) | `test_agent_cannot_invite_agent()` | 403 para solicitante em `group_real_estate_agent` | ⚠️ Obrigatório |

### User Story 2: Gestor reenvia um convite para um perfil de agente sem precisar reenviar os dados do agente (Prioridade: P2)

**Como** Gestor (Manager)
**Eu quero** reenviar um e-mail de convite para um agente cujo registro `real.estate.agent` já existe
**Para que** eu não precise saber ou reenviar novamente os dados de CRECI/banco

**Critérios de Aceitação**:
- [ ] Dado um `res.users` com `signup_pending=True` já vinculado a um perfil de agente (e seu registro `real.estate.agent` já existe, `user_id` já definido), quando `POST /api/v1/users/resend-invite` é chamado, então apenas o token/e-mail são regenerados — nenhuma lógica de criação de agente roda novamente (idempotente, sem registro `real.estate.agent` duplicado, sem 409, `user_id` inalterado).
- [ ] Dado que `resend-invite` é chamado para um usuário cujo registro de agente NÃO existe (caso extremo: o registro de agente foi excluído manualmente após o convite), quando chamado, o comportamento permanece inalterado em relação ao atual (o reenvio só toca a camada de token/e-mail) — caso extremo já existente, não introduzido por esta feature.

**Cobertura de Testes**:

| Tipo | Nome do Teste | Descrição | Status |
|------|-----------|-------------|--------|
| Unitário | `test_resend_invite_does_not_recreate_agent()` | Nenhum novo registro `real.estate.agent` após o reenvio | ⚠️ Obrigatório |

### User Story 3: `POST /api/v1/agents` é removida definitivamente assim que o fluxo unificado é validado — sem janela de descontinuação (Prioridade: P1) 🎯 MVP

**Como** equipe de plataforma responsável pela superfície de API
**Eu quero** remover fisicamente `POST /api/v1/agents` assim que `POST /api/v1/users/invite` cobrir totalmente a criação de agentes (registro + login + vínculo de RBAC), sem estágio intermediário de descontinuação
**Para que** a superfície de API tenha um único caminho validado para o onboarding de agentes e nenhuma lógica de validação duplicada para manter — conforme instrução explícita do solicitante, esta é uma remoção direta, não um processo de descontinuar-depois-remover

**Critérios de Aceitação**:
- [ ] Dado que as User Stories 1–2 estão implementadas, testadas e passando (unitário + E2E conforme ADR-003), quando o passo de remoção desta feature é executado, então o método/rota `create_agent` em `quicksol_estate/controllers/agent_api.py` é excluído (não apenas desabilitado), e sua linha no registro `thedevkitchen.api.endpoint` é excluída — em uma única etapa, sem fase prévia de headers `Deprecation`/`Sunset`.
- [ ] Dado que o endpoint foi removido, quando `POST /api/v1/agents` é chamado, então a resposta é um 404 padrão (rota não mais registrada).
- [ ] Dado que o endpoint foi removido, quando a spec OpenAPI é regenerada, então a operação `POST /api/v1/agents` não aparece mais na spec.
- [ ] Dado que o endpoint foi removido, quando a coleção Postman é regenerada, então o request legado `"Create Agent"` é excluído, restando apenas o request unificado `"Invite Agent"`.
- [ ] Dado que o endpoint foi removido, quando a suíte de testes de integração existente de `create_agent` é inspecionada, então esses arquivos de teste são excluídos (substituídos pela suíte de testes da User Story 1) em vez de deixados falhando contra uma rota inexistente.
- [ ] Em nenhum momento do rollout desta feature `POST /api/v1/agents` emite um header `Deprecation` ou `Sunset`, ou ganha um marcador `"deprecated": true` no OpenAPI — seu comportamento permanece inalterado até a única etapa de remoção acima.

**Cobertura de Testes**:

| Tipo | Nome do Teste | Descrição | Status |
|------|-----------|-------------|--------|
| E2E (API) | `test_create_agent_route_returns_404_after_removal()` | Confirma que a rota foi removida | ⚠️ Obrigatório |
| Integração | `test_openapi_agents_post_absent_after_removal()` | `POST /api/v1/agents` não está mais presente na spec OpenAPI gerada | ⚠️ Obrigatório |
| Integração | `test_postman_collection_legacy_agent_request_removed()` | Request legado não está mais presente na coleção Postman regenerada | ⚠️ Obrigatório |

**Pré-condições de remoção (todas devem ser atendidas antes de executar esta história)**:
1. A User Story 1 (fluxo de convite unificado, incluindo a correção de vínculo de `user_id` e a paridade total de campos) está implementada e sua suíte de testes completa passa.
2. Uma verificação do log de acesso de API do `thedevkitchen_apigateway` confirma que não há tráfego de produção inesperado ainda acessando `POST /api/v1/agents`, ou a equipe aceitou explicitamente o risco de migração para quaisquer chamadores remanescentes.
3. **Desta vez, o merge na `develop` requer autorização explícita do usuário antes de acontecer** (a correção concreta de processo para o incidente que causou a reversão da Feature 025).

---

## Requisitos

### Requisitos Funcionais

**FR1: Validação Unificada de Campos — paridade total com `AGENT_CREATE_SCHEMA` (conforme diretriz explícita do solicitante, 2026-07-18)**
- FR1.1: Quando `POST /api/v1/users/invite` visa um perfil com `profile_type_id.code == 'agent'`, o corpo da requisição PODE incluir um objeto `agent` opcional.
- FR1.2: Se presente, `agent.creci` DEVE passar pela mesma validação que `AGENT_CREATE_SCHEMA` aplica hoje: `len(creci) >= 4`, normalizado via `CreciValidator.normalize()`, e único por `company_id` entre agentes ativos (espelha `real.estate.agent._check_creci_format`, ADR-012).
- FR1.3: Se presentes, `agent.bank_account`, `agent.bank_name`, `agent.pix_key`, `agent.hire_date` DEVEM ser validados por tipo de forma idêntica às regras de campos opcionais de `AGENT_CREATE_SCHEMA`.
- FR1.4 (**alterado — paridade total de campos, não um subconjunto reduzido**): `agent.name`, `agent.cpf`, `agent.email`, `agent.phone`, `agent.mobile` TAMBÉM PODEM ser fornecidos no objeto `agent`, cada um validado com a restrição IDÊNTICA que `AGENT_CREATE_SCHEMA`/`create_agent` já aplica (`name`: `len(v) >= 3 and len(v) <= 255`; `cpf`: exatamente 11 dígitos após remover `.`/`-`; `email`: contém `@` e `.`; `phone`/`mobile`: validado por tipo `str`, sem restrição adicional, igual ao `create_agent`). Quando fornecidos, esses valores são usados literalmente para o registro `real.estate.agent` criado (substituindo os valores do perfil vinculado apenas para esse registro — o perfil em si não é alterado).
- FR1.4c (**reaproveitamento de campos já existentes — confirmado pelo solicitante, 2026-07-18; mecanismo já implementado, verificado no código**): Para todo campo do objeto `agent` que já existe/é conhecido através do perfil vinculado (`name`, `cpf`↔`document`, `email`, `phone`, `mobile`, `hire_date`, `company_id`) — ou seja, todo campo "repetido" entre o `agent` node e os dados já cadastrados no `thedevkitchen.estate.profile` — quando o campo é omitido no `agent` node, ele NÃO é solicitado novamente nem revalidado do zero: o valor já existente e já validado no perfil é reaproveitado automaticamente. Isso já está implementado hoje em `real.estate.agent.create()` (`quicksol_estate/models/agent.py`, linhas 436-470), verificado no código atual: sempre que `vals` contém `profile_id`, o método faz `vals.setdefault("name", profile.name)`, `vals.setdefault("cpf", profile.document)` (mapeamento explícito `document → cpf`, comentário do próprio código), `vals.setdefault("email", profile.email)`, `vals.setdefault("phone", profile.phone)`, `vals.setdefault("mobile", profile.mobile)`, `vals.setdefault("company_id", profile.company_id.id)` e, se `profile.hire_date` existir, `vals.setdefault("hire_date", profile.hire_date)` — `setdefault()` garante que um valor explicitamente enviado no `agent` node sempre prevalece sobre o valor reaproveitado do perfil, nunca o contrário. **Consequência para a implementação desta feature**: o controller (`invite_controller.py::invite_user`) NÃO deve reimplementar essa lógica de fallback/reaproveitamento — ele só precisa garantir que `profile_id` esteja presente em `agent_vals` antes de chamar `real.estate.agent.create()`; o reaproveitamento dos campos repetidos acontece automaticamente na camada de modelo, sem necessidade de código novo. Reescrever esse fallback no controller duplicaria uma lógica que já existe e poderia divergir dela com o tempo — não fazer isso.
- FR1.4b (**exceção de segurança, confirmada via `AskUserQuestion`, 2026-07-18**): `agent.company_id` e `agent.user_id` são os ÚNICOS dois campos de `AGENT_CREATE_SCHEMA` NÃO espelhados no schema aceito do objeto `agent`. Se um cliente incluir qualquer uma dessas chaves, ela DEVE ser silenciosamente ignorada (não gera 400) — `company_id` é sempre obtido do `company_id` do perfil vinculado; `user_id` é sempre o id do registro `res.users` criado anteriormente na mesma requisição. Esta é uma exceção deliberada e mais restrita à "paridade total de campos", não um descuido — aceitar qualquer um deles do cliente permitiria que o solicitante de uma empresa vinculasse um registro de agente ao perfil de outra empresa ou ao login de outro usuário (ADR-008).
- FR1.5: A validação do objeto `agent` DEVE ocorrer ANTES da criação de qualquer registro `res.users` (falhar rápido, sem estado parcial).

**FR2: Vínculo/Criação Atômica do Registro de Agente Durante o Convite (vinculado tanto ao perfil quanto ao login) — semântica de upsert (corrigido em 2026-07-19, achado durante a implementação da Task 4)**

**Achado que motiva a correção**: `profile_api.py` (código pré-existente da Feature 010, `POST /api/v1/profiles`, linhas 236-255 — NÃO faz parte desta feature) **já cria automaticamente** um registro `real.estate.agent` (com `profile_id`, `name`, `cpf`, `email`, `phone`, `mobile`, `company_id`, `hire_date` — mas `user_id` nulo) sempre que o perfil criado é do tipo `agent`. Isso significa que, no momento em que `POST /api/v1/users/invite` é chamado (precondição do fluxo feliz desta spec: "perfil já criado via `POST /api/v1/profiles`"), **um registro `real.estate.agent` para aquele `profile_id` já existe, sem `user_id`** — não é um registro que ainda precisa ser criado do zero. Um `create()` cego (como as versões anteriores desta spec assumiam) colide com esse registro já existente na restrição `UNIQUE(cpf, company_id)` (`_sql_constraints = [("cpf_company_unique", ...)]`, `agent.py:218-224`), gerando um `psycopg2.errors.UniqueViolation` — que **não** é um `ValidationError` e portanto não seria capturado por um `except ValidationError`, vazando como 500 depois que `res.users`/token já teriam sido criados na mesma transação (violação direta da garantia de atomicidade desta mesma seção). Confirmado ao vivo via `odoo shell` durante a implementação, não apenas inferido da leitura do código.

- FR2.1 (**alterado — upsert, não create() cego**): Quando o tipo do perfil-alvo é `agent`, `invite_user` DEVE primeiro buscar (`search`) um registro `real.estate.agent` existente por `profile_id=profile_record.id`. **Se encontrado** (caso normal, dado o auto-create de `profile_api.py`), DEVE fazer `write()` nesse registro com `user_id=user.id` mais quaisquer campos explicitamente fornecidos no objeto `agent` (filtrados pelo `allowed_keys`, FR1.4b) — NÃO criar um segundo registro. **Se NÃO encontrado** (caso defensivo/legado — ex.: perfil criado antes desta lógica existir, ou o auto-create de `profile_api.py` ser removido/alterado no futuro), DEVE criar um novo registro via `profile_id=profile_record.id` mais os mesmos campos, exatamente como as versões anteriores desta spec descreviam (reaproveitando o mecanismo de fallback do `create()`, FR1.4c). Ambos os ramos ocorrem na MESMA transação de banco de dados que a criação do `res.users` e a geração do token de convite.
- FR2.1b (**novo, corrige a lacuna da Feature 025**): O registro `real.estate.agent`, seja atualizado via `write()` ou criado via `create()`, TAMBÉM DEVE ter `user_id` definido para o `res.users.id` recém-criado. Isso é obrigatório, não opcional — todo caminho de código de RBAC/notificação que restringe dados ao "agente atualmente logado" (`property_api.py`, `lead_api.py` ×3, `serializers.py`, `proposal.py` ×4, `record_rules.xml`) lê `agent_id.user_id`, nunca `agent_id.profile_id`.
- FR2.2: Se a operação em `real.estate.agent` (write ou create) falhar por qualquer motivo (validação, restrição de banco — incluindo as restrições já existentes `_check_user_unique` e `_check_creci_format`), a requisição inteira DEVE falhar atomicamente — nenhum `res.users`, nenhum token de convite, nenhum e-mail enviado (rollback implícito de transação do Odoo, consistente com o padrão "Atomic Dual Record Creation" da constituição). A semântica de upsert (FR2.1) elimina a colisão de `UNIQUE(cpf, company_id)` que um `create()` cego causaria no caso normal (registro já existente via `profile_api.py`), então esta garantia volta a valer sem depender de capturar `psycopg2.errors.UniqueViolation` como um caso especial.
- FR2.3: O e-mail de convite DEVE ser enviado somente após os registros `res.users` e `real.estate.agent` serem confirmados (commit) com sucesso (o envio de e-mail permanece best-effort/não-bloqueante — uma falha de envio não deve reverter a transação).
- FR2.4: Para todos os outros tipos de perfil, o comportamento de `invite_user` permanece INALTERADO — nenhuma criação de entidade de domínio é adicionada por esta feature para esses tipos (fora de escopo).

**FR3: Contrato de Resposta**
- FR3.1: Quando um registro `agent` é criado como parte do convite, o objeto `data` do corpo da resposta `201` DEVE incluir `agent_id` além dos já existentes `id` (id do usuário), `profile_id`.
- FR3.2: Os `links` HATEOAS DEVEM adicionar `"agent": "/api/v1/agents/{agent_id}"` quando um registro de agente foi criado.

**FR4: Reconciliação de Autorização**
- FR4.1: A matriz de autorização já existente da ADR-024 do fluxo de convite (`owner`/`director`/`manager` podem convidar `agent`) governa quem pode acionar este fluxo unificado — mais ampla que a checagem atual de `create_agent`, restrita a manager-ou-system-admin.
- FR4.2: Esta feature NÃO altera a autorização já existente de `create_agent` antes de sua remoção — os dois endpoints podem ter escopos de autorização diferentes pelo (curto, sem janela de descontinuação) período em que ambos existem; essa discrepância DEVE ser documentada na descrição OpenAPI de `POST /api/v1/users/invite` enquanto `create_agent` ainda existir.
- FR4.3: `director`/`owner` convidando um perfil `agent` é intencional, conforme a matriz já existente e inalterada da ADR-024.

**FR5: Remoção de `POST /api/v1/agents` (direta — sem janela de descontinuação, conforme diretriz explícita do solicitante)**
- FR5.1: Assim que as pré-condições de remoção da User Story 3 forem satisfeitas, excluir o método controlador `create_agent` e seu registro `@http.route` por completo — em uma única etapa, sem fase prévia de headers `Deprecation`/`Sunset` e sem estado intermediário `deprecated: true` no OpenAPI.
- FR5.2: Excluir a linha correspondente no registro `thedevkitchen.api.endpoint`.
- FR5.3: Regenerar a spec OpenAPI via skill `swagger-updater` e confirmar que `POST /api/v1/agents` não aparece mais.
- FR5.4: Atualizar a coleção Postman via skill `postman-collection-manager` para excluir o request legado.
- FR5.5: Excluir os testes de integração/unitários de `create_agent` agora substituídos.
- FR5.6: Até o momento da remoção, o comportamento funcional de `create_agent` (campos, validação, formato do corpo da resposta, headers) permanece INALTERADO — nenhum sinal de descontinuação de qualquer tipo é adicionado em nenhum momento antes da remoção.

**FR6: Completude do Vínculo de RBAC (novo — o requisito corretivo desta spec)**
- FR6.1: Todo consumidor existente de `agent_id.user_id` DEVE ser exercitado por pelo menos um teste E2E usando um agente criado através do fluxo unificado de convite, não apenas através do `create_agent` legado/dados de fixture: `property_api.py` (escopo de `GET /api/v1/properties`), `lead_api.py` (escopo de `GET /api/v1/leads`, os 3 pontos de chamada cobertos conceitualmente por um teste representativo cada, para listagem/detalhe), a checagem de propriedade em `serializers.py`, e ao menos um caminho de destinatário de notificação em `proposal.py`.
- FR6.2: O campo `real.estate.agent.user_id` DEVE ganhar um índice de banco de dados (`index=True`) — ver seção Modelo de Dados — já que este campo é lido em toda requisição de listagem de imóveis e leads feita por um usuário do papel "agent", e esta feature deve aumentar substancialmente a proporção de registros de agente em que esse campo está de fato preenchido (hoje, agentes criados por convite deixam-no nulo, o que faz a consulta sempre falhar e cair no caso "não vê nada"; após esta feature, a maioria dos logins do papel agent terá uma correspondência real, tornando este um filtro de hot-path ativo pela primeira vez).

### Modelo de Dados (conforme ADR-004, knowledge_base/09-database-best-practices.md)

**Nenhuma nova entidade é introduzida.** Esta feature altera a orquestração em nível de controller entre entidades já existentes, mais uma mudança de schema (um índice) em um campo já existente.

**Entidade: `real.estate.agent`** (existente; uma mudança de schema em nível de campo)
- **Nome do Modelo**: `real.estate.agent` (pré-existente; NÃO renomeado — exceção legada aceita, constituição §12 item 5)
- Campos existentes relevantes usados por esta feature: `profile_id` (Many2one → `thedevkitchen.estate.profile`, já aciona a sincronização `setdefault()` do `create()` descrita abaixo — mas note que, no caminho normal (FR2.1), o registro já existe via `profile_api.py` e a operação é `write()`, não `create()`; o `setdefault()` só entra em jogo no ramo defensivo de fallback), `user_id` (Many2one → `res.users`, "Link to user account if agent has system access" — **atualmente não definido em nenhum lugar do fluxo de convite; esta feature é o que começa a preenchê-lo**), `creci`, `creci_normalized` (computado, armazenado, indexado), `bank_name`, `bank_account`, `bank_account_type`, `pix_key`, `hire_date`, `company_id` (FK obrigatória, multi-tenancy).
- **Mudança de schema**: adicionar `index=True` a `user_id` (`fields.Many2one("res.users", "Related User", ondelete="restrict", index=True, help=...)`). Nenhuma migração de dados necessária além do próprio `_auto_init` do módulo (o Odoo cria o índice automaticamente na atualização do módulo, para uma tabela deste tamanho — dezenas a poucas centenas de linhas por empresa — com duração de lock desprezível).
- Restrições existentes reaproveitadas, não modificadas: `_check_creci_format` (`@api.constrains('creci', 'creci_normalized', 'company_id')` — unicidade de `creci_normalized` restrita a `company_id`); `_check_user_unique` (`@api.constrains('user_id', 'company_id')` — um agente por usuário por empresa; esta restrição é o que torna seguro definir `user_id` no momento da criação via convite, contra vinculação dupla acidental).
- **Mecanismo de reaproveitamento de campos já existente (verificado no código, `agent.py` linhas 436-470, FR1.4c)** — `create()` já faz o seguinte, sempre que `vals` contém `profile_id`:
  ```python
  # quicksol_estate/models/agent.py:436-470 (verbatim, já existente — nenhuma mudança necessária)
  @api.model
  def create(self, vals):
      if vals.get("profile_id"):
          profile = self.env["thedevkitchen.estate.profile"].sudo().browse(vals["profile_id"])
          if profile.exists():
              vals.setdefault("name", profile.name)
              vals.setdefault("cpf", profile.document)  # document → cpf
              vals.setdefault("email", profile.email)
              vals.setdefault("phone", profile.phone)
              vals.setdefault("mobile", profile.mobile)
              vals.setdefault("company_id", profile.company_id.id)
              if profile.hire_date:
                  vals.setdefault("hire_date", profile.hire_date)
      if vals.get("user_id"):
          user = self.env["res.users"].browse(vals["user_id"])
          if user.company_ids and "company_id" not in vals:
              vals["company_id"] = user.company_ids[0].id
      agent = super().create(vals)
      return agent
  ```
  Como o bloco de `profile_id` roda antes do bloco de `user_id`, e o primeiro já preenche `company_id` via `setdefault()`, o segundo bloco (`if "company_id" not in vals`) nunca chega a sobrescrevê-lo — isso é o que garante, na prática, que `company_id` sempre venha do perfil, nunca de `user.company_ids[0]`, quando ambos `profile_id` e `user_id` são passados juntos (exatamente o caso desta feature, FR1.4b).

**Entidade: `thedevkitchen.estate.profile`** (existente, schema inalterado)
- Nenhuma mudança de schema. `profile_type_id.code` é lido para ramificar a nova lógica; `document`, `name`, `email`, `phone`, `mobile`, `hire_date`, `company_id` são reaproveitados pelo `real.estate.agent.create()` acima — nenhuma leitura ou cópia adicional é feita pelo controller.

**Entidade: `res.users`** (existente, schema inalterado)
- Nenhuma mudança de schema. Lógica de criação (`InviteService.create_user_from_profile`) inalterada; o `id` do registro retornado é o que é passado para o novo `agent_vals["user_id"]`.

**Nova superfície de validação/orquestração (nível de controller, mais a única migração em nível de campo acima) — semântica de upsert (FR2.1, corrigido 2026-07-19), o reaproveitamento de campos acontece no `create()` do modelo apenas no ramo defensivo (FR1.4c)**:
```python
# thedevkitchen_user_onboarding/controllers/invite_controller.py (esboço da nova lógica)
agent_payload = data.get("agent")  # objeto aninhado opcional
if profile_type == "agent":
    if agent_payload:
        is_valid, errors = SchemaValidator.validate_agent_invite(agent_payload)
        if not is_valid:
            return self._error_response(400, "validation_error", ", ".join(errors))
    # ... cria o usuário (já existente, InviteService.create_user_from_profile) ...

    # company_id / user_id NUNCA são obtidos de agent_payload, mesmo se presentes —
    # somente derivados no servidor (ADR-008; confirmado via AskUserQuestion, 2026-07-18)
    allowed_keys = {
        "name", "cpf", "email", "phone", "mobile",
        "creci", "hire_date", "bank_name", "bank_account", "pix_key",
    }
    explicit_fields = {
        k: v for k, v in (agent_payload or {}).items()
        if k in allowed_keys and v is not None
    }

    # FR2.1: profile_api.py (Feature 010) já auto-cria um real.estate.agent (sem user_id)
    # quando o perfil é do tipo 'agent' — buscar antes de criar, para não colidir em
    # UNIQUE(cpf, company_id). Achado confirmado ao vivo durante a implementação da Task 4.
    Agent = request.env["real.estate.agent"].sudo()
    existing_agent = Agent.search([("profile_id", "=", profile_record.id)], limit=1)
    if existing_agent:
        existing_agent.write({"user_id": user.id, **explicit_fields})
        agent = existing_agent
    else:
        # Ramo defensivo (perfil legado sem auto-create, ou comportamento futuro de
        # profile_api.py alterado) — reaproveita o fallback já existente de create() (FR1.4c)
        agent = Agent.create({
            "profile_id": profile_record.id,
            "user_id": user.id,
            **explicit_fields,
        })
    # write()/create() geram exceção em conflitos de CRECI/usuário -> revertem toda a requisição
```

**Novo schema (estende `quicksol_estate/controllers/utils/schema.py::SchemaValidator`) — paridade total com `AGENT_CREATE_SCHEMA`, menos `company_id`, reaproveitando as mesmas funções de restrição em vez de reescrevê-las**:
```python
# Reaproveita as funções de restrição já definidas em AGENT_CREATE_SCHEMA (schema.py:25-55)
# em vez de duplicar as mesmas lambdas em um segundo dicionário — evita que as duas
# validações divirjam silenciosamente ao longo do tempo (o pedido original desta seção).
_SHARED_CONSTRAINTS = AGENT_CREATE_SCHEMA["constraints"]  # {"name": ..., "cpf": ..., "email": ..., "creci": ...}

AGENT_INVITE_SCHEMA = {
    "required": [],  # nada é obrigatório aqui — campos de identidade usam o perfil vinculado como padrão
    "optional": [
        "name", "cpf", "email", "phone", "mobile",
        "creci", "hire_date", "bank_name", "bank_account", "pix_key",
    ],
    "types": AGENT_CREATE_SCHEMA["types"],  # reaproveitado por completo — os mesmos 10 campos + company_id (ignorado, ver FR1.4b)
    "constraints": _SHARED_CONSTRAINTS,  # reaproveitado por completo, não reescrito
}
```
Observação: `AGENT_CREATE_SCHEMA` marca `name`/`cpf`/`email`/`company_id` como `required` porque `create_agent` não tem outra fonte para eles; `AGENT_INVITE_SCHEMA` marca os mesmos campos como `optional` porque o perfil vinculado já os garante (FR1.4c) — mas as *funções de restrição em si* não são reescritas, são literalmente a mesma referência de objeto (`AGENT_CREATE_SCHEMA["constraints"]`/`["types"]`), então qualquer ajuste futuro em uma regra (ex.: mudar o tamanho mínimo de `name`) se propaga automaticamente para os dois schemas sem exigir uma segunda edição. `company_id` e `user_id` estão intencionalmente ausentes do conjunto de chaves *aceitas* (`optional`) de `AGENT_INVITE_SCHEMA` (FR1.4b) mesmo estando presentes em `AGENT_CREATE_SCHEMA["types"]`/`["constraints"]` — reaproveitar o dicionário de tipos/restrições não significa aceitar todas as suas chaves como entrada; o filtro `allowed_keys` no controller (acima) é o que efetivamente restringe quais chaves chegam a `agent_vals`, e ele deliberadamente omite `company_id`/`user_id`. A normalização/unicidade completa de CRECI permanece nos `@api.constrains` do modelo, não duplicada na camada de schema.

**Regras de Registro (Record Rules)**: Nenhuma nova regra de registro — `rule_agent_own_properties` e `rule_agent_own_assignments` (ambas chaveadas em `agent_id.user_id = user.id`) já existem e, pela primeira vez, vão de fato corresponder a agentes criados via convite assim que `user_id` estiver preenchido (esta feature torna essas regras já existentes *efetivas* para agentes convidados via API, em vez de exigir qualquer regra nova).

### Endpoints de API (conforme ADR-007, ADR-009, ADR-011)

**Endpoint: POST /api/v1/users/invite (modificado)**

| Atributo | Valor |
|-----------|-------|
| **Método** | POST |
| **Caminho** | `/api/v1/users/invite` |
| **Autenticação** | `@require_jwt` + `@require_session` + `@require_company` (inalterado) |
| **Autorização** | Conforme matriz da ADR-024: `owner`, `director`, `manager` podem convidar perfis `agent` (autorização inalterada, agora também condiciona a criação do registro de agente) |
| **Limite de Taxa** | Nenhum atualmente (consistente com o endpoint existente) |

**Corpo da Requisição** (estende o contrato existente, conforme ADR-018 — o objeto `agent` espelha o conjunto completo de campos de `AGENT_CREATE_SCHEMA`, menos `company_id`/`user_id`, conforme FR1.4/FR1.4b):
```json
{
  "profile_id": "integer (obrigatório, perfil existente com profile_type_id.code == 'agent')",
  "agent": {
    "name": "string (opcional, 3-255 caracteres — substitui o name do perfil no registro de agente se fornecido, senão usa o do perfil)",
    "cpf": "string (opcional, 11 dígitos após remover '.'/'-' — substitui o document do perfil se fornecido, senão usa o do perfil)",
    "email": "string (opcional, deve conter '@' e '.' — substitui o email do perfil se fornecido, senão usa o do perfil)",
    "phone": "string (opcional — substitui o phone do perfil se fornecido, senão usa o do perfil)",
    "mobile": "string (opcional — substitui o mobile do perfil se fornecido, senão usa o do perfil)",
    "creci": "string (opcional, mínimo 4 caracteres, formato+unicidade validados por empresa)",
    "hire_date": "string (opcional, data ISO)",
    "bank_name": "string (opcional)",
    "bank_account": "string (opcional, máximo 20 caracteres conforme o campo do modelo)",
    "pix_key": "string (opcional)"
  }
}
```
(O objeto `agent` é ignorado/opcional para tipos de perfil diferentes de agent; incluí-lo para um perfil não-agent é um no-op, não um erro. `company_id` e `user_id` NÃO são chaves aceitas neste objeto — se presentes, são silenciosamente descartadas; ambos são sempre derivados no servidor, conforme FR1.4b.)

**Resposta de Sucesso (201)** (conforme HATEOAS da ADR-007 — o formato completo de array `links` está planejado mas ainda não implementado neste endpoint; a resposta atual estende o formato de dict `links` já existente):
```json
{
  "success": true,
  "data": {
    "id": 42,
    "name": "Jane Agent",
    "email": "jane@example.com",
    "document": "12345678901",
    "profile": "agent",
    "profile_id": 17,
    "agent_id": 88,
    "signup_pending": true,
    "invite_sent_at": "2026-07-18T10:00:00Z",
    "invite_expires_at": "2026-07-19T10:00:00Z"
  },
  "message": "User invited successfully. Email sent to jane@example.com",
  "links": {
    "self": "/api/v1/users/42",
    "resend_invite": "/api/v1/users/42/resend-invite",
    "collection": "/api/v1/users",
    "profile": "/api/v1/profiles/17",
    "agent": "/api/v1/agents/88"
  }
}
```

**Respostas de Erro** (estende o envelope existente):
| Código | Condição | Resposta |
|------|-----------|----------|
| 400 | Qualquer campo de `agent` falha na validação (tamanho de `name`, contagem de dígitos de `cpf`, formato de `email`, formato de `creci` — restrições idênticas às de `create_agent`) | `{"success": false, "error": "validation_error", "message": "...", "details": {...}}` |
| 403 | Solicitante não autorizado para o tipo de perfil `agent` (ADR-024) | `{"success": false, "error": "forbidden", "message": "..."}` |
| 404 | Perfil não encontrado (`profile_id` inexistente) | `{"success": false, "error": "not_found", "message": "..."}` |
| 400 | Perfil de empresa diferente da do solicitante — comportamento atual, **acidental**, não uma checagem de anti-vazamento intencional (ver "Achado de Segurança Registrado", fora de escopo desta spec; um 404 real de anti-vazamento ADR-008 é candidato à spec 027) | `{"success": false, "error": "validation_error", "message": "..."}` |
| 409 | Perfil já tem um usuário vinculado, OU `agent.creci` já usado na empresa, OU (novo) o `user_id`-alvo já está vinculado a outro agente na empresa (`_check_user_unique`) | `{"success": false, "error": "conflict", "message": "...", "details": {...}}` |
| 500 | Erro inesperado (inclui falhas de criação de agente não categorizadas de outra forma) | `{"success": false, "error": "internal_error", "message": "..."}` |

**Endpoint: POST /api/v1/agents (inalterado → removida diretamente, sem estágio de descontinuação)**

| Atributo | Valor |
|-----------|-------|
| **Método** | POST |
| **Caminho** | `/api/v1/agents` |
| **Status (até a remoção)** | **INALTERADO** — sem headers, sem marcador `deprecated` no OpenAPI, sem qualquer mudança de comportamento (conforme diretriz explícita do solicitante: não descontinuar, remover) |
| **Status (após a remoção)** | **REMOVIDO** — rota, método do controller, linha do `thedevkitchen.api.endpoint`, testes, operação OpenAPI e request do Postman, todos excluídos em uma única etapa (FR5) |
| **Autenticação (até a remoção)** | `@require_jwt` + `@require_session` + `@require_company` (inalterado) |
| **Autorização (até a remoção)** | Apenas `group_real_estate_manager` ou `base.group_system` (inalterado — mais restrito que a matriz ADR-024 do fluxo de convite, ver FR4.2) |

Até o momento da remoção, o contrato deste endpoint permanece totalmente inalterado; ele continua criando um agente apenas-registro (sem `res.users`, `user_id` fica nulo — este é o comportamento legado do qual os consumidores já dependem). Não há sinal intermediário para os consumidores — o endpoint funciona exatamente como funciona hoje, até que a etapa de remoção da User Story 3 seja executada, após a qual chamar esse caminho retorna um 404 padrão.

### Dados de Seed (OBRIGATÓRIO — todos os tipos de solução)

**Seed: Empresas**
```python
seed_company_a = env['res.company'].create({'name': 'Empresa A (Seed 026)'})
seed_company_b = env['res.company'].create({'name': 'Empresa B (Seed 026)'})
```

**Seed: Usuários por Papel**
```python
seed_users = {
    'owner_a':      {'login': 'seed_owner_a_026@test.com',      'company': seed_company_a, 'group': 'group_real_estate_owner'},
    'manager_a':    {'login': 'seed_manager_a_026@test.com',    'company': seed_company_a, 'group': 'group_real_estate_manager'},
    'agent_a':      {'login': 'seed_agent_a_026@test.com',      'company': seed_company_a, 'group': 'group_real_estate_agent'},
    'manager_b':    {'login': 'seed_manager_b_026@test.com',    'company': seed_company_b, 'group': 'group_real_estate_manager'},  # isolamento
}
```

**Seed: Tipo de Perfil**
```python
# Reaproveita o profile_type 'agent' já semeado (thedevkitchen.profile.type, code='agent') — não duplicar.
```

**Seed: Entidades de Domínio**
```python
# Perfil pendente de convite (empresa A) — usado pelos testes de caminho feliz da User Story 1
seed_profile_pending_agent = env['thedevkitchen.estate.profile'].create({
    'name': 'Seed Agent Pending', 'company_id': seed_company_a.id,
    'profile_type_id': agent_profile_type.id,
    'document': '<CPF válido>', 'email': 'seed_agent_pending_026@test.com',
    'birthdate': '1990-01-01',
})

# Agente existente com CRECI já cadastrado (empresa A) — usado no teste de conflito de unicidade
seed_agent_existing_creci = env['real.estate.agent'].create({
    'name': 'Seed Agent Existing', 'cpf': '<CPF válido>', 'email': 'seed_agent_existing_026@test.com',
    'company_id': seed_company_a.id, 'creci': 'CRECI-SP-999999-J',
})

# Imóvel + Lead pré-atribuídos ao agente *convidado* (criados DEPOIS do convite no fluxo do teste,
# via agent_id = <o registro de agente criado pelo convite unificado>) — usados por
# test_invited_agent_sees_own_properties / test_invited_agent_sees_own_leads
seed_property_for_invited_agent = env['real.estate.property'].create({
    'name': 'Seed Property for Invited Agent', 'company_id': seed_company_a.id,
    'agent_id': None,  # definido no momento do teste para o id do agente recém-convidado
})

# Perfil pendente de convite (empresa B) — usado no teste de isolamento entre empresas
seed_profile_pending_agent_b = env['thedevkitchen.estate.profile'].create({
    'name': 'Seed Agent Pending B', 'company_id': seed_company_b.id,
    'profile_type_id': agent_profile_type.id,
    'document': '<CPF válido>', 'email': 'seed_agent_pending_b_026@test.com',
    'birthdate': '1990-01-01',
})
```

> **Regras**: Todos os IDs/logins de seed usam o prefixo `seed_`. Criação idempotente (proteger com `search()` antes de `create()`). Todo critério de aceitação acima tem um registro de seed correspondente como ponto de partida.

---

### Requisitos Não-Funcionais

**NFR1: Segurança** (conforme ADR-008, ADR-011, ADR-017, ADR-019)
- `POST /api/v1/users/invite` mantém a cadeia de triplo decorador já existente; nenhuma nova superfície pública é introduzida.
- O novo objeto `agent` não aceita `company_id` ou `user_id` (ambos são sempre derivados no servidor — `company_id` a partir do perfil, `user_id` a partir do registro `res.users` recém-criado) — fecha um vetor de spoofing entre empresas E um vetor de "vincular a mim mesmo o registro de agente de outra pessoa".
- Anti-enumeração entre empresas: **inalterada** em relação ao comportamento atual de `invite_user` — o que hoje significa um bloqueio acidental via `ValidationError`/400 (efeito colateral de `company_id`/`company_ids` inconsistentes em `res.users`), não um 404 intencional de anti-vazamento. Esta feature não piora nem corrige essa lacuna pré-existente (ver "Achado de Segurança Registrado", fora de escopo — candidato à spec 027).

**NFR2: Performance** (conforme `knowledge_base/performance.md` — análise específica desta feature, não boilerplate)
- **Volume de dados**: Convites de agente são uma operação de baixa frequência, conduzida por administradores (dezenas por empresa por mês) — nenhuma preocupação de paginação/endpoint de listagem se aplica ao próprio endpoint de convite.
- **Padrão de consulta / indexação — a mudança concreta que esta feature exige**: `real.estate.agent.user_id` atualmente **não tem índice** (verificado em `agent.py`: `fields.Many2one("res.users", "Related User", ondelete="restrict")`, sem `index=True`), mas é exatamente o campo consultado em **toda** chamada de `GET /api/v1/properties` e `GET /api/v1/leads` feita por um usuário do papel "agent" (`property_api.py`: `search([('user_id','=', user.id)], limit=1)`; `lead_api.py`: `domain.append(('agent_id.user_id','=', user.id))` em 3 pontos de chamada). Hoje essa consulta quase sempre falha (agentes criados por convite têm `user_id = NULL`), então o índice ausente tem custo pouco observável. **Após esta feature entrar em produção, a maioria dos logins do papel agent terá um `user_id` real e preenchido**, transformando isso de uma consulta raramente correspondente em um filtro ativamente usado em toda requisição de listagem de imóveis/leads de todo agente de campo — este é o único índice concreto que esta spec adiciona (`index=True` em `real_estate_agent.user_id`), dimensionado adequadamente para uma tabela com realisticamente dezenas a poucas centenas de linhas por empresa (a criação do índice é quase instantânea; nenhuma preocupação de `CONCURRENTLY`/migração online nessa escala).
- **Risco de N+1**: O próprio fluxo de convite adiciona um único `search()` por `profile_id` (indexado, `limit=1`) mais uma única operação `write()` OU `create()` (nunca ambos) por requisição de convite — sem N+1, e sem mudança de magnitude em relação à versão anterior desta spec (que assumia um único `create()`; agora é um único `search()` + um único `write()`/`create()`, ainda O(1) por requisição). A jusante, os 3 pontos de chamada de `lead_api.py` e o 1 ponto de chamada de `property_api.py` já fazem, cada um, um único `search()` limitado (não um loop por registro) para resolver `agent_id`, então nenhum novo padrão de N+1 é introduzido ao preencher `user_id` — a *consulta em si* permanece inalterada, apenas sua taxa de correspondência aumenta (o que é a correção pretendida, não uma regressão).
- **Aplicabilidade de cache-aside com Redis**: Não aplicável ao próprio endpoint de convite (caminho de escrita de baixa frequência, não um hot-path de leitura/autenticação — não se qualifica para o padrão de cache JWT/sessão da Feature 023, que é restrito a consultas de autenticação por requisição). A consulta a jusante de `real.estate.agent` por `user_id` em `property_api.py`/`lead_api.py` **é** uma leitura por requisição em um hot-path (toda chamada de listagem de todo agente), mas é uma única busca pontual indexada (`limit=1` / filtro de igualdade) em uma tabela pequena — sub-milissegundo com o novo índice, bem abaixo do limite em que uma camada de cache-aside Redis justificaria sua própria complexidade de invalidação (mudanças no vínculo agente-usuário são raras, mas o custo marginal da consulta indexada que seria cacheada também é). Recomendação: não adicionar cache Redis para esta consulta; reconsiderar apenas se a tabela `real.estate.agent` crescer para um tamanho incomum (milhares de linhas por empresa) ou se o profiling mostrar o contrário.
- **Offload assíncrono/Celery**: O envio do e-mail de convite (`InviteService.send_invite_email`, atualmente `mail.mail.create()` + `.send()`, síncrono hoje) permanece inalterado por esta feature e já fica fora do limite da transação atômica (best-effort conforme FR2.3). A nova chamada `real.estate.agent.create()` deve permanecer **síncrona** e dentro da mesma transação que a criação do `res.users` (garantia de atomicidade do FR2.2) — movê-la para o Celery quebraria essa garantia, já que tasks do Celery rodam em uma transação/conexão separada, após o commit. Nenhuma nova fila é introduzida; esta é uma restrição de corretude, não uma oportunidade de otimização perdida.
- Meta: o tempo de resposta p95 de `POST /api/v1/users/invite` permanece `< 300ms` (orçamento inalterado em relação à linha de base da Feature 009; um INSERT adicional de uma única linha mais duas buscas de unicidade já indexadas — `creci_normalized`, e agora `user_id` — não deve mover esse orçamento).

**NFR3: Qualidade** (conforme ADR-022)
- O código deve passar: black, isort, flake8 (`18.0/lint.sh`).
- Nota do Pylint ≥ 8.0/10.
- 100% de cobertura de testes nas validações novas/modificadas (conjunto completo de campos de `AGENT_INVITE_SCHEMA`, o ramo `profile_type == 'agent'`, o vínculo de `user_id`).

**NFR4: Integridade de Dados** (conforme knowledge_base/09-database-best-practices.md)
- O design 3NF já existente (`profile` ↔ `agent` ↔ `res.users`, todos vinculados via FK, sem colunas duplicadas) é preservado e melhorado — esta feature elimina dois estados inconsistentes anteriormente possíveis: perfil+usuário sem nenhum registro de agente (objetivo original da Feature 025), E registro de agente presente mas funcionalmente invisível para o RBAC porque `user_id` nunca foi definido (adição corretiva desta spec).
- Soft delete (ADR-015) não afetado — nenhum novo caminho de exclusão é introduzido.
- Atomicidade: FR2.2 é a garantia central de integridade (nenhum estado parcial de usuário-sem-agente, e nenhum de agente-sem-user_id, para convites do tipo `agent` daqui em diante).

**NFR5: Compatibilidade com Frontend**
- Não aplicável — ambos os endpoints são apenas de API (Modelo de Acesso: apenas o usuário `admin` do Odoo acessa a UI do Odoo; Owner/Manager/Director convidam agentes pelo frontend headless). Nenhuma view/menu do Odoo é introduzido ou modificado. Nenhum teste Cypress é necessário.

---

## Restrições Técnicas

### Deve Seguir (das ADRs & Knowledge Base)

| Fonte | Requisito | Aplicado a |
|--------|-------------|------------|
| ADR-004 | Prefixo `thedevkitchen_` apenas para módulos NOVOS — `quicksol_estate` e `real.estate.agent` são a exceção legada documentada; esta feature não os renomeia | Nomes de modelo |
| ADR-005 | Regeneração de OpenAPI; confirmar que a operação `POST /api/v1/agents` está totalmente ausente após a remoção (sem fase intermediária de `deprecated: true`) | Registro `thedevkitchen.api.endpoint` de `POST /api/v1/agents` |
| ADR-008 | Isolamento entre empresas; sem spoofing de empresa via payload aninhado `agent`; `user_id` também sempre derivado no servidor | Controller de convite |
| ADR-009 | Modelo de autenticação headless — ambos os endpoints conduzidos apenas via API por admin/manager/owner | Modelo de Acesso |
| ADR-011 | Triplo decorador em ambos os endpoints (inalterado) | Controllers |
| ADR-012 | Validação/normalização de CRECI reaproveitada sem modificação | `CreciValidator`, `_check_creci_format` |
| ADR-015 | Soft delete — não afetado por esta feature | N/A |
| ADR-016 | Atualização da coleção Postman — request legado excluído diretamente, sem estado intermediário re-rotulado | `docs/postman/` |
| ADR-018 | Validação de schema para o novo objeto `agent` | `SchemaValidator.AGENT_INVITE_SCHEMA` |
| ADR-019 | RBAC — matriz de convite da ADR-024 vs. checagem mais restrita de `create_agent`; discrepância documentada (FR4.2) | Autorização |
| ADR-022 | Padrões de lint | Todo código modificado |
| ADR-024 | Unificação de perfil — sincronização `profile_id` em `agent.py::create()` reaproveitada, não duplicada | Modelo de dados |
| Constituição §"Atomic Dual Record Creation" | Padrão reaproveitado para atomicidade de usuário+agente | `invite_user` |
| Constituição §"Transactional Email Patterns" | Falha de e-mail não-bloqueante equivalente a `force_send=False` | `send_invite_email` (inalterado) |
| `.claude/rules/git-workflow.md` | Nenhum merge em `develop`/`master` sem confirmação explícita do usuário — a correção direta de processo para a reversão da Feature 025 | Processo de implementação/rollout |

### Padrões Arquiteturais

- **Padrão de Controller**: Conforme `.github/instructions/controllers.instructions.md`
- **Padrão de Testes**: Conforme `.github/instructions/test-strategy.instructions.md`
- **Implementação de Referência**: Feature 009 (ciclo de vida do token de convite) + Feature 010/ADR-024 (perfil unificado, sincronização já existente de `profile_id` em `create_agent`, em `agent.py::create()`) + a análise da spec da Feature 025 (substituída por, e parcialmente reaproveitada nesta spec — seu sequenciamento de descontinuar-depois-remover explicitamente NÃO é reaproveitado) são os padrões de implementação prévia mais próximos que esta feature combina.

---

## Critérios de Sucesso

### Backend
- [ ] As 3 user stories implementadas e testadas
- [ ] 100% de cobertura de testes unitários nas novas validações (conjunto completo de campos de `AGENT_INVITE_SCHEMA` — `name`/`cpf`/`email`/`phone`/`mobile` mais `creci`/`hire_date`/`bank_name`/`bank_account`/`pix_key` — caminho de unicidade de CRECI reaproveitado, vínculo de `user_id`, rollback de atomicidade, `company_id`/`user_id` ignorados se presentes no nó)
- [ ] Testes E2E de API para todos os fluxos críticos, incluindo os dois **novos** testes de visibilidade de RBAC (`test_invited_agent_sees_own_properties`, `test_invited_agent_sees_own_leads`) que a Feature 025 não tinha
- [ ] Isolamento multi-empresa verificado para o novo objeto `agent` (nenhum spoofing de `company_id` ou `user_id` possível)
- [ ] `real_estate_agent.user_id` tem um índice de banco de dados (`index=True`) confirmado presente após a atualização do módulo
- [ ] Qualidade de código: Pylint ≥ 8.0, todos os linters passando (ADR-022)
- [ ] Requisitos de segurança validados (ADR-008, ADR-011)
- [ ] O comportamento de `POST /api/v1/agents` permanece completamente inalterado (sem headers, sem marcador OpenAPI) até a única etapa de remoção — sua suíte de testes de integração existente passa sem modificação até esse ponto
- [ ] A rota, o método do controller, a linha do registro e os testes substituídos de `POST /api/v1/agents` são excluídos assim que as pré-condições de remoção da User Story 3 forem atendidas (FR5) — diretamente, sem estágio de descontinuação
- [ ] `POST /api/v1/agents` retorna 404 após a remoção e não aparece mais na spec OpenAPI gerada
- [ ] O merge na `develop` acontece somente após autorização explícita do usuário (gate de processo, conforme Armadilhas Conhecidas)

### Frontend
- Não aplicável (feature apenas de API; ver NFR5).

### Seeds
- [ ] Arquivo de dados de seed criado com prefixo `seed_` em todos os IDs/logins
- [ ] Seed cobre os papéis owner/manager/agent em duas empresas (teste de isolamento)
- [ ] Seed inclui um perfil pendente de convite + um agente existente com CRECI cadastrado (teste de conflito) + uma fixture de imóvel/lead para exercitar os novos testes de visibilidade de RBAC
- [ ] Seed é idempotente
- [ ] Testes de API usam os registros de seed como estado inicial

### Documentação
- [ ] Feedback de constituição analisado e documentado (ver abaixo)
- [ ] Swagger/OpenAPI regenerado (conforme ADR-005) — obrigatório, duas passagens, mas nenhuma das duas passagens introduz um estado intermediário `deprecated: true` — ver `.claude/skills/swagger-updater/SKILL.md`:
  - [ ] Passagem 1 (enquanto ambos os endpoints existem): novo objeto `agent` com paridade total documentado em `POST /api/v1/users/invite`; documentação de `POST /api/v1/agents` inalterada (sem marcador de descontinuação)
  - [ ] Passagem 2 (pós-remoção): a operação `POST /api/v1/agents` totalmente ausente da spec regenerada
- [ ] Coleção Postman atualizada (conforme ADR-016) — ver `.claude/skills/postman-collection-manager/SKILL.md` — Passagem 1 adiciona o request unificado "Invite Agent" inalterado, Passagem 2 exclui diretamente o request legado "Create Agent" (sem etapa de re-rotulação intermediária)
- [ ] Fluxogramas de jornada criados em `specs/026-user-agent-registration-unification/flowcharts.md` (um por user story, incluindo a história de remoção)

---

## Feedback de Constituição

### Novos Padrões Introduzidos

| Padrão | Descrição | Seção da Constituição | Prioridade |
|---------|-------------|---------------------|----------|
| Sub-Objeto Opcional Aninhado para Campos Condicionais por Tipo | Quando um tipo de perfil entre vários precisa de campos extras em um endpoint compartilhado, adicionar um objeto aninhado opcional (`agent: {...}`) em vez de bifurcar o endpoint ou achatar os campos específicos do tipo no schema compartilhado — o objeto espelha o conjunto completo de campos do endpoint substituído, exceto os campos de tenancy/identidade derivados no servidor (`company_id`, `user_id`) | "Padrões Arquiteturais" | Baixa — reaproveitável para futuros tipos de perfil |
| **Padrão de Identidade com Vínculo Duplo** (novo nesta spec) | Quando uma entidade de domínio (`real.estate.agent`) pode ser vinculada tanto a um registro cadastral/de perfil (`profile_id`) quanto a um login de sistema (`user_id`), qualquer fluxo de criação que produza ambos DEVE definir ambos os vínculos explicitamente — código de RBAC/notificação frequentemente depende do vínculo voltado para o login (`user_id`), não do cadastral (`profile_id`), e os dois não são intercambiáveis | Nova subseção em "Padrões Arquiteturais" ou um item de checklist em "Multi-Tenancy by Design" | Média — esta classe exata de bug (registro criado, mas não vinculado ao campo que o RBAC de fato lê) é genérica o suficiente para recorrer com outras entidades de vínculo duplo |
| **Substituição Direta em vez de Janela de Descontinuação** (novo nesta spec, direcionado pelo solicitante) | Quando um endpoint antigo é totalmente substituído por um novo unificado e o solicitante opta explicitamente por não ter um período de transição, remover o endpoint antigo definitivamente assim que o substituto estiver implementado e validado — sem headers `Deprecation`/`Sunset`, sem estado intermediário `deprecated: true` no OpenAPI, sem request do Postman re-rotulado mas ainda presente. Esta é uma alternativa válida ao "Padrão de Descontinuação de Endpoint" que a Feature 025 teria introduzido, não uma rejeição de janelas de descontinuação em geral — a escolha é uma decisão por feature, não uma regra de toda a constituição | Nova subseção em "Padrões Arquiteturais" — documentar ao lado de (não em vez de) um futuro padrão de janela de descontinuação, já que ambos são legítimos dependendo da tolerância a risco dos chamadores | Baixa — reconhecer como um sequenciamento alternativo aceito, para que um futuro autor de spec não presuma que descontinuar-depois-remover é obrigatório |

### Novas Entidades/Relacionamentos

Nenhuma — nenhuma nova entidade é introduzida; esta feature fecha uma lacuna na orquestração já existente `profile` ↔ `agent` ↔ `res.users` e completa um vínculo `agent` ↔ `res.users` anteriormente parcial.

### Decisões Arquiteturais

| Decisão | Justificativa | ADR Necessária? |
|----------|-----------|---------------|
| Manter o comportamento de `POST /api/v1/agents` totalmente inalterado até que seja removido definitivamente, sem janela de descontinuação | Diretriz explícita do solicitante (2026-07-18): uma janela de descontinuação não é desejada para esta feature; a remoção direta evita o estágio extra de rollout e manter dois caminhos de código de validação duplicada em paralelo por mais tempo do que o necessário | Não — capturado nesta spec (inalterado → removido); User Story 3/FR5 definem os critérios de remoção |
| O nó `agent` espelha o conjunto completo de campos de `AGENT_CREATE_SCHEMA` (`name`, `cpf`, `email`, `phone`, `mobile`, `creci`, `hire_date`, `bank_name`, `bank_account`, `pix_key`), não apenas os campos ausentes do perfil | Diretriz explícita do solicitante (2026-07-18): o nó deve ter "os mesmos campos da API original," validados de forma idêntica — indo além da suposição do primeiro rascunho desta própria spec, de que apenas os campos não-identitários precisavam ser repetidos | Não — capturado nesta spec (FR1.4); um requisito direto de paridade de campos, não um novo princípio arquitetural |
| Company ID e `user_id` para o novo registro de agente são sempre derivados no servidor, nunca aceitos no objeto de requisição `agent` — a única exceção deliberada à paridade total de campos | Fecha um vetor de spoofing de empresa (ADR-008) e um vetor de spoofing de usuário; confirmado via `AskUserQuestion` durante a elaboração da spec, sobre duas alternativas menos seguras (aceitar-e-cruzar-validar, aceitar-e-confiar) | Não — aplicação da ADR-008 já existente, não uma nova decisão |
| `real.estate.agent.user_id` ganha um índice de banco de dados | O campo se torna um filtro de RBAC ativamente correspondido, por requisição, assim que esta feature entrar em produção (anteriormente quase sempre nulo); esta é uma adição de índice direcionada, baseada em evidência, não especulativa | Não — otimização de schema de rotina, não requer uma ADR |

### Recomendação de Atualização da Constituição

- **Atualização Necessária**: Sim (após a implementação estar completa e validada)
- **Bump de Versão Sugerido**: MINOR (novos "Padrão de Identidade com Vínculo Duplo" e "Substituição Direta em vez de Janela de Descontinuação" documentados como padrões reaproveitáveis, sem redefinição de princípio)
- **Seções a Atualizar**:
  - [ ] Padrões Arquiteturais → adicionar "Padrão de Identidade com Vínculo Duplo"
  - [ ] Padrões Arquiteturais → adicionar "Substituição Direta em vez de Janela de Descontinuação" (como uma alternativa aceita, ao lado de, não substituindo, um futuro padrão de janela de descontinuação)
  - [ ] Implementações de Referência → adicionar a entrada da Feature 026 assim que implementada (substituindo a entrada nunca concluída da Feature 025)

---

## Suposições & Dependências

**Suposições**:
- Tipos de perfil diferentes de `agent` estão explicitamente FORA DE ESCOPO para esta feature — seu fluxo de convite permanece inalterado.
- A lista de campos obrigatórios já existente de `AGENT_CREATE_SCHEMA` (`name`, `cpf`, `company_id`, `email`) é totalmente satisfeita pelos campos obrigatórios de `PROFILE_CREATE_SCHEMA` — verificado por comparação direta dos dois schemas em `quicksol_estate/controllers/utils/schema.py` (confirmado inalterado desde a análise da Feature 025); é isso que torna seguro que `AGENT_INVITE_SCHEMA` marque esses mesmos campos como opcionais (fallback do perfil) em vez de obrigatórios.
- `POST /api/v1/agents` é removida diretamente, SEM janela de descontinuação — diretriz explícita confirmada do solicitante (2026-07-18), substituindo o padrão de descontinuar-depois-remover da Feature 025 e o primeiro rascunho desta própria spec.
- O objeto `agent` espelha o conjunto completo de campos de `AGENT_CREATE_SCHEMA` (não um subconjunto reduzido "apenas-extras"), exceto `company_id`/`user_id` — diretriz explícita confirmada do solicitante (2026-07-18), com a exclusão de `company_id`/`user_id` confirmada via `AskUserQuestion` durante a elaboração.
- A regeneração de Swagger/OpenAPI é obrigatória, não um "bônus" opcional — mantido da decisão já confirmada da Feature 025.
- O objeto aninhado `agent` (não um payload plano no estilo `create_agent`) é o formato da requisição — mantido da decisão já confirmada da Feature 025, e adicionalmente justificado aqui pela necessidade de manter `user_id`/`company_id` derivados no servidor (NFR1).
- `profile_id` permanece **obrigatório** em `POST /api/v1/users/invite` — confirmado explicitamente pelo solicitante (2026-07-18), após a pergunta natural levantada pela paridade total de campos do nó `agent` ("por que ainda preciso de um `profile_id` pré-existente, se o nó `agent` já carrega os mesmos campos de `create_agent`?"). Esta spec **não** introduz um caminho que crie `thedevkitchen.estate.profile` inline a partir do nó `agent` — o fluxo continua em duas chamadas (`POST /api/v1/profiles` depois `POST /api/v1/users/invite`), como hoje. Fazer o `profile_id` opcional foi considerado e explicitamente descartado, para não expandir o escopo desta spec para também unificar a criação de perfil.

**Dependências**:
- Módulos existentes: `quicksol_estate` (modelo/controller de agente, controllers de RBAC de imóveis/leads), `thedevkitchen_user_onboarding` (controller/serviço de convite), `thedevkitchen_apigateway` (decoradores de autenticação, geração de OpenAPI, registro de endpoints de API)
- Serviços externos: PostgreSQL 16 (atomicidade de transação, novo índice), Redis 7 (não afetado — nenhum novo uso de cache conforme NFR2)
- Autenticação: OAuth2 + sessão via `thedevkitchen_apigateway` (inalterado)
- Trabalho prévio: `specs/025-agent-invite-unification/spec-idea.md` (substituída por esta spec; ainda útil como contexto histórico para o design de objeto aninhado/atomicidade — seu sequenciamento de descontinuar-depois-remover explicitamente NÃO é reaproveitado, conforme a correção direcionada pelo solicitante nesta spec)

---

## Fases de Implementação

### Fase 1: Fundação
- Adicionar `index=True` a `real.estate.agent.user_id` (bump de versão do módulo; o Odoo cria o índice na atualização)
- Adicionar `AGENT_INVITE_SCHEMA` ao `SchemaValidator`, reaproveitando (por referência, não por cópia) `AGENT_CREATE_SCHEMA["types"]` e `AGENT_CREATE_SCHEMA["constraints"]` — paridade total de campos com `AGENT_CREATE_SCHEMA`, menos `company_id`/`user_id` no conjunto de chaves aceitas, conforme FR1/FR1.4c
- **Não** reimplementar em `SchemaValidator` ou no controller a lógica de fallback para o perfil (`setdefault`) — ela já existe em `real.estate.agent.create()` (`agent.py:436-470`, FR1.4c); esta fase só adiciona a validação do que o cliente efetivamente enviar
- Testes unitários para a validação de schema (sucesso + falha por campo, incluindo `name`/`cpf`/`email`/`phone`/`mobile`) e para a presença do índice

### Fase 2: Camada de API
- Modificar `invite_controller.py::invite_user` para ramificar em `profile_type == 'agent'`, validar o objeto opcional `agent` contra `AGENT_INVITE_SCHEMA`, descartar quaisquer chaves `company_id`/`user_id` enviadas pelo cliente (FR1.4b), e criar `real.estate.agent` atomicamente com **tanto** `profile_id` **quanto** `user_id` definidos — bastando repassar `profile_id`/`user_id` mais os campos explicitamente enviados; o reaproveitamento dos campos repetidos e omitidos é automático via `create()` (FR1.4c), o controller não duplica essa lógica
- Adicionar `agent_id` ao corpo da resposta + link `agent`
- Nenhuma mudança em `agent_api.py::create_agent` nesta fase — seu comportamento permanece exatamente como está até a etapa de remoção da Fase 5 (sem headers, sem mudanças intermediárias de registro)

### Fase 3: Testes & Qualidade
- Testes unitários (schema — conjunto completo de campos, atomicidade/rollback, reaproveitamento de CRECI, vínculo + unicidade de `user_id`, `company_id`/`user_id` ignorados se presentes)
- Testes E2E de API (caminho feliz, substituição de campo vs. fallback do perfil, conflito, isolamento entre empresas, regressão de paridade legada, **novo**: agente-convidado-vê-seus-próprios-imóveis/leads)
- Gates de lint/qualidade (ADR-022)

### Fase 4: Documentação & Artefatos
- Regeneração de OpenAPI (novo objeto `agent` com paridade total em `POST /api/v1/users/invite`; documentação de `POST /api/v1/agents` inalterada) — skill `swagger-updater`
- Atualização da coleção Postman (adicionar o request unificado "Invite Agent"; request legado "Create Agent" mantido como está até a Fase 5) — skill `postman-collection-manager`
- Fluxogramas de jornada (`flowcharts.md`)
- Atualização de constituição (Padrão de Identidade com Vínculo Duplo + Substituição Direta em vez de Janela de Descontinuação)

### Fase 5: Remoção de `POST /api/v1/agents` (após as pré-condições de remoção serem atendidas — User Story 3, remoção direta, sem estágio de descontinuação)
- Confirmar as pré-condições de remoção (User Story 1 totalmente testada; log de acesso de API mostra tráfego insignificante/aceito)
- Excluir o método do controller `create_agent` + registro de rota
- Excluir a linha do registro `thedevkitchen.api.endpoint`
- Excluir os testes unitários/de integração substituídos de `create_agent`
- Regenerar o OpenAPI (confirmar que a operação está ausente) — skill `swagger-updater`
- Regenerar a coleção Postman (excluir o request legado) — skill `postman-collection-manager`
- **Merge na `develop` somente após confirmação explícita do usuário** — a correção de processo para o incidente da Feature 025

---

## Artefatos a Gerar

> **⚠️ OBRIGATÓRIO**: Consultar `.claude/skills/development-best-practices/SKILL.md` antes de implementar as mudanças de modelo/controller acima. Usar `.claude/skills/swagger-updater/SKILL.md` e `.claude/skills/postman-collection-manager/SKILL.md` para os respectivos artefatos de documentação — nunca editar manualmente os arquivos estáticos de OpenAPI/Postman.

Após a aprovação da especificação, gerar:

1. **Atualização de Constituição** — novos "Padrão de Identidade com Vínculo Duplo" e "Substituição Direta em vez de Janela de Descontinuação" (ver Feedback de Constituição acima); recomenda-se rodar o subagente `thedevkitchen-speckit-project-constitution` assim que a implementação estiver validada.
2. **Atualização das Instruções do Copilot** — se o padrão de vínculo duplo e/ou o padrão de substituição direta forem considerados reaproveitáveis, adicionar exemplos curtos a `.github/copilot-instructions.md`.
3. **Tarefas Pós-Desenvolvimento** (após a implementação estar completa e validada):
   - OpenAPI (`docs/openapi/`) via skill `swagger-updater`
   - Coleção Postman via skill `postman-collection-manager`
   - Fluxogramas de jornada em `specs/026-user-agent-registration-unification/flowcharts.md`

---

## Checklist de Validação

### Validação de Backend
- [ ] "Fora de Escopo / Não-Objetivos" preenchido com itens específicos da feature (não genéricos/vazios)
- [ ] Todos os requisitos de ADR referenciados e seguidos
- [ ] Padrões da knowledge base aplicados (análise de performance completa, baseada em código — ver NFR2, não boilerplate genérico)
- [ ] Multi-tenancy corretamente especificada (ADR-008) — `company_id` E `user_id` sempre derivados no servidor, nunca aceitos a partir do objeto `agent`
- [ ] Segurança devidamente definida (ADR-011, ADR-019) — discrepância de autorização entre os dois endpoints explicitamente documentada (FR4.2)
- [ ] Estratégia de testes completa — unitário + E2E de API (ADR-003), incluindo os dois novos testes E2E de visibilidade de RBAC
- [ ] Design de banco de dados normalizado — uma adição de índice direcionada (`user_id`), 3NF preservada
- [ ] Tratamento de erros especificado (ADR-018) — 400/403/404/409/500 todos mapeados
- [ ] Requisitos de qualidade de código definidos (ADR-022)

### Validação de Frontend
- Não aplicável (feature apenas de API, nenhuma view/menu introduzido).
