# Unificar Cadastro de Usuários com Onboarding de Agentes — Plano de Implementação

> **Para workers agênticos:** SUB-SKILL OBRIGATÓRIA: use `superpowers:subagent-driven-development` (recomendado) ou `superpowers:executing-plans` para implementar este plano tarefa a tarefa. Os passos usam sintaxe de checkbox (`- [ ]`) para rastreamento.

**Objetivo:** `POST /api/v1/users/invite` passa a criar um registro `real.estate.agent` (vinculado a `profile_id` **e** `user_id`) atomicamente quando o perfil convidado é do tipo `agent`, aceitando um objeto `agent` opcional com paridade total de campos com `AGENT_CREATE_SCHEMA` — fechando a lacuna de RBAC que a Feature 025 deixou aberta.

**Arquitetura:** Nenhum componente novo de infraestrutura. Uma extensão de controller (`invite_controller.py::invite_user`) que reaproveita, sem duplicar, o mecanismo de fallback de campos já existente em `real.estate.agent.create()` (`agent.py:436-470`), mais uma migração de índice de banco de dados. `POST /api/v1/agents` permanece intocada — sua remoção é uma fase futura, fora deste plano (ver "Fora deste Plano" no final).

**Stack:** Odoo 18.0 / Python 3.12, PostgreSQL 16, testes via `odoo.tests.common.TransactionCase` (unitário) + scripts curl em `integration_tests/*.sh` (E2E API — convenção deste projeto, `HttpCase` é evitado por sua limitação de transação somente-leitura).

## Restrições Globais

- **ADR-008**: `agent.company_id` e `agent.user_id` NUNCA são aceitos do cliente no objeto `agent` — sempre derivados no servidor (perfil vinculado / login recém-criado).
- **ADR-011**: cadeia de decoradores `@require_jwt` + `@require_session` + `@require_company` em `invite_user` permanece inalterada — não remover nem contornar.
- **ADR-012**: validação/normalização de CRECI (`CreciValidator`, `_check_creci_format`) é reaproveitada sem modificação.
- **ADR-022**: todo código modificado deve passar `black`/`isort`/`flake8` (`18.0/lint.sh`) e Pylint ≥ 8.0/10.
- **FR2.2 (atomicidade)**: falha na criação do `real.estate.agent` deve impedir que `res.users`/token/e-mail sejam persistidos — nenhum estado parcial.
- **`profile_id` continua obrigatório** em `POST /api/v1/users/invite` — este plano NÃO introduz criação de perfil inline (decisão confirmada com o usuário).
- **`.claude/rules/git-workflow.md`**: nenhum merge em `develop`/`master` sem autorização explícita do usuário — vale para TODOS os commits deste plano, mesmo que a branch de feature seja mesclada depois.
- **Comando de upgrade de módulo** (verificado em specs anteriores deste repo): `docker compose exec odoo odoo -d realestate -u <módulo> --stop-after-init` (a partir de `18.0/`).
- **Convenção de testes CORRIGIDA (2026-07-19, achado em execução — `--test-tags /<módulo>:<Classe>` NÃO funciona neste ambiente, confirmado empiricamente contra classes já existentes)**: este projeto tem exatamente dois caminhos válidos, roteados por `scripts/validate_coverage.sh` (fonte de verdade, leia antes de escrever qualquer teste novo):
  1. **Lógica pura, sem `self.env`/DB** (ex.: validação de schema, funções utilitárias): arquivo em `tests/unit/`, sufixo obrigatório `_unit.py` (ex.: `test_algo_unit.py`), classe `unittest.TestCase` (NÃO `TransactionCase`), importando o módulo via o truque de path já usado em `tests/unit/run_unit_tests.py` (`odoo.addons.__path__.insert(0, "/mnt/extra-addons")` seguido de `from odoo.addons.quicksol_estate.X import Y`). Executado via `docker compose exec odoo python3 /mnt/extra-addons/quicksol_estate/tests/unit/run_unit_tests.py` (a partir de `18.0/`) — nenhum processo Odoo/DB é iniciado, é só Python puro.
  2. **Qualquer coisa que precise de `self.env`/DB** (registros ORM reais, constraints, etc.): arquivo em `tests/integration/`, classe `TransactionCase`, **com um `from . import nome_do_arquivo` adicionado em `tests/integration/__init__.py`** (Odoo só descobre testes explicitamente importados na cadeia de `tests/__init__.py` — arquivos não importados são invisíveis para o test runner, mesmo usando `TransactionCase`). Executado via `docker compose exec odoo odoo -d realestate -u quicksol_estate --test-enable --stop-after-init --log-level=test --http-port=8988` (a partir de `18.0/`, porta alternativa para não colidir com o `odoo18` já rodando) — **nunca usar `--test-tags`, rodar o módulo inteiro** e conferir que a saída NÃO contém a string `"0 tests"` (se contiver, o teste não foi de fato descoberto — sintoma exato que `validate_coverage.sh` já verifica).
- **Verificação pendente antes da Task 4**: os scripts curl deste plano assumem `TEST_USER_MANAGER`/`TEST_PASSWORD_MANAGER` em `18.0/.env` (só `TEST_USER_OWNER`/`TEST_PASSWORD_OWNER` foram confirmados existir, em outro script já existente). Antes de rodar a Task 4, confirmar com `grep TEST_USER_MANAGER 18.0/.env` — se não existir, usar `TEST_USER_OWNER`/`TEST_PASSWORD_OWNER` nos scripts (Owner também está autorizado a convidar `agent` pela matriz ADR-024) ou criar o usuário de teste correspondente.
- **Verificação pendente antes da Task 4**: os scripts curl deste plano assumem `TEST_USER_MANAGER`/`TEST_PASSWORD_MANAGER` em `18.0/.env` (só `TEST_USER_OWNER`/`TEST_PASSWORD_OWNER` foram confirmados existir, em outro script já existente). Antes de rodar a Task 4, confirmar com `grep TEST_USER_MANAGER 18.0/.env` — se não existir, usar `TEST_USER_OWNER`/`TEST_PASSWORD_OWNER` nos scripts (Owner também está autorizado a convidar `agent` pela matriz ADR-024) ou criar o usuário de teste correspondente.

---

## Estrutura de Arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `18.0/extra-addons/quicksol_estate/models/agent.py:84-89` | Modificar | Adicionar `index=True` ao campo `user_id` |
| `18.0/extra-addons/quicksol_estate/migrations/18.0.6.0.0/pre-migrate.py` | Criar | Migração idempotente de índice para bancos já existentes |
| `18.0/extra-addons/quicksol_estate/__manifest__.py` | Modificar | Bump de versão `18.0.5.0.0` → `18.0.6.0.0` |
| `18.0/extra-addons/quicksol_estate/controllers/utils/schema.py` | Modificar | Adicionar `AGENT_INVITE_SCHEMA` + `validate_agent_invite()` |
| `18.0/extra-addons/quicksol_estate/tests/unit/test_schema_agent_invite.py` | Criar | Testes unitários do novo schema |
| `18.0/extra-addons/quicksol_estate/tests/unit/test_agent_create_from_profile_and_user.py` | Criar | Testes de caracterização (regressão) do mecanismo `setdefault()` já existente, chamado com `profile_id`+`user_id` juntos |
| `18.0/extra-addons/thedevkitchen_user_onboarding/controllers/invite_controller.py:33-171` | Modificar | Ramificar em `profile_type == 'agent'`, validar `agent` opcional, criar `real.estate.agent` atomicamente |
| `18.0/extra-addons/thedevkitchen_user_onboarding/__manifest__.py` | Modificar | Bump de versão `18.0.1.0.0` → `18.0.2.0.0` |
| `18.0/extra-addons/thedevkitchen_user_onboarding/data/api_endpoints_data.xml:11-78` | Modificar | Documentar o objeto `agent` no registro `thedevkitchen.api.endpoint` de `POST /api/v1/users/invite` |
| `integration_tests/test_us026_s1_invite_agent_unification.sh` | Criar | E2E: fluxo completo + paridade de campos + validação + conflito + visibilidade RBAC |
| `integration_tests/test_us026_s2_resend_invite_regression.sh` | Criar | E2E: reenvio de convite não recria agente |
| `docs/postman/postman_collection.json` (ou caminho equivalente do projeto) | Modificar (via skill) | Adicionar exemplo do objeto `agent` no request "Invite Agent" |

---

### Task 1: Índice de banco de dados em `real.estate.agent.user_id`

**Arquivos:**
- Modificar: `18.0/extra-addons/quicksol_estate/models/agent.py:84-89`
- Modificar: `18.0/extra-addons/quicksol_estate/__manifest__.py`
- Criar: `18.0/extra-addons/quicksol_estate/migrations/18.0.6.0.0/pre-migrate.py`
- Teste: `18.0/extra-addons/quicksol_estate/tests/unit/test_agent_user_id_index.py`

**Interfaces:**
- Consome: nada de tarefas anteriores.
- Produz: `real.estate.agent.user_id` com `index=True` — usado implicitamente por toda consulta futura em `property_api.py`/`lead_api.py` (já existentes, inalteradas por este plano).

- [ ] **Passo 1: Escrever o teste que falha**

```python
# 18.0/extra-addons/quicksol_estate/tests/unit/test_agent_user_id_index.py
# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestAgentUserIdIndex(TransactionCase):
    def test_user_id_field_has_index(self):
        """Feature 026: user_id deve ter index=True (hot-path de RBAC após esta feature)"""
        field = self.env["real.estate.agent"]._fields["user_id"]
        self.assertTrue(
            field.index,
            "real.estate.agent.user_id deve ter index=True — "
            "campo lido em toda listagem de imóveis/leads por usuário 'agent'",
        )
```

- [ ] **Passo 2: Rodar o teste e confirmar que falha**

```
cd 18.0
docker compose exec odoo odoo -d realestate --test-tags /quicksol_estate:TestAgentUserIdIndex --test-enable --stop-after-init
```
Esperado: FALHA — `AssertionError: False is not true : real.estate.agent.user_id deve ter index=True ...` (o campo hoje não tem `index=True`).

- [ ] **Passo 3: Adicionar `index=True` ao campo**

Em `18.0/extra-addons/quicksol_estate/models/agent.py`, linhas 84-89, substituir:
```python
    user_id = fields.Many2one(
        "res.users",
        "Related User",
        ondelete="restrict",
        help="Link to user account if agent has system access",
    )
```
por:
```python
    user_id = fields.Many2one(
        "res.users",
        "Related User",
        ondelete="restrict",
        index=True,
        help="Link to user account if agent has system access",
    )
```

- [ ] **Passo 4: Rodar o teste e confirmar que passa**

```
cd 18.0
docker compose exec odoo odoo -d realestate -u quicksol_estate --stop-after-init
docker compose exec odoo odoo -d realestate --test-tags /quicksol_estate:TestAgentUserIdIndex --test-enable --stop-after-init
```
Esperado: PASSA.

- [ ] **Passo 5: Criar a migração idempotente para bancos já existentes**

```python
# 18.0/extra-addons/quicksol_estate/migrations/18.0.6.0.0/pre-migrate.py
# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Feature 026: adiciona índice em real_estate_agent.user_id.

    real.estate.agent.user_id passa a ser um filtro de RBAC ativamente
    consultado em toda listagem de imóveis/leads feita por um agente
    convidado via POST /api/v1/users/invite (antes, o campo ficava quase
    sempre nulo e a consulta raramente batia). Ver spec-idea.md NFR2/FR6.2.
    """
    cr.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'real_estate_agent'
        )
        """
    )
    table_exists = cr.fetchone()[0]
    if not table_exists:
        _logger.info("Feature 026: tabela real_estate_agent ainda não existe, pulando migração.")
        return

    cr.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_real_estate_agent_user_id
        ON real_estate_agent (user_id);
        """
    )
    _logger.info("Feature 026: índice idx_real_estate_agent_user_id garantido em real_estate_agent.")
```

- [ ] **Passo 6: Bump de versão do manifest**

Em `18.0/extra-addons/quicksol_estate/__manifest__.py`, alterar:
```python
"version": "18.0.5.0.0",  # Feature 020: RBAC Capabilities API
```
para:
```python
"version": "18.0.6.0.0",  # Feature 026: user_id index for agent invite RBAC
```

- [ ] **Passo 7: Rodar o upgrade completo do módulo e verificar o índice no banco**

```
cd 18.0
docker compose exec odoo odoo -d realestate -u quicksol_estate --stop-after-init
docker compose exec -T db psql -U odoo -d realestate -c "\d real_estate_agent" | grep idx_real_estate_agent_user_id
```
Esperado: a linha do índice aparece na saída do `\d`.

- [ ] **Passo 8: Commit**

```bash
git add 18.0/extra-addons/quicksol_estate/models/agent.py \
        18.0/extra-addons/quicksol_estate/__manifest__.py \
        18.0/extra-addons/quicksol_estate/migrations/18.0.6.0.0/pre-migrate.py \
        18.0/extra-addons/quicksol_estate/tests/unit/test_agent_user_id_index.py
git commit -m "feat(quicksol_estate): add index=True to real.estate.agent.user_id"
```

---

### Task 2: Schema `AGENT_INVITE_SCHEMA` + `validate_agent_invite()`

**Arquivos:**
- Modificar: `18.0/extra-addons/quicksol_estate/controllers/utils/schema.py` (inserir após `AGENT_CREATE_SCHEMA`, linha ~55, e após `validate_agent_create`, linha ~388)
- Teste: `18.0/extra-addons/quicksol_estate/tests/unit/test_schema_agent_invite.py`

**Interfaces:**
- Consome: `SchemaValidator.AGENT_CREATE_SCHEMA["types"]`/`["constraints"]` (já existentes, linhas 25-55), `SchemaValidator.validate_request(data, schema)` (já existente, linhas 332-381 — motor genérico de validação, não modificado).
- Produz: `SchemaValidator.AGENT_INVITE_SCHEMA` (dict) e `SchemaValidator.validate_agent_invite(data) -> tuple[bool, list[str]]` — consumido pela Task 4.

- [ ] **Passo 1: Escrever o teste que falha**

```python
# 18.0/extra-addons/quicksol_estate/tests/unit/test_schema_agent_invite.py
# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.addons.quicksol_estate.controllers.utils.schema import SchemaValidator


class TestSchemaAgentInvite(TransactionCase):
    def test_full_field_parity_payload_is_valid(self):
        """Paridade total: todos os 10 campos de AGENT_CREATE_SCHEMA (menos company_id) são aceitos"""
        payload = {
            "name": "Jane Agent",
            "cpf": "12345678901",
            "email": "jane@example.com",
            "phone": "1130000000",
            "mobile": "11999998888",
            "creci": "CRECI-SP 12345",
            "hire_date": "2026-01-01",
            "bank_name": "Banco do Brasil",
            "bank_account": "12345-6",
            "pix_key": "jane@example.com",
        }
        is_valid, errors = SchemaValidator.validate_agent_invite(payload)
        self.assertTrue(is_valid, errors)
        self.assertEqual(errors, [])

    def test_empty_payload_is_valid(self):
        """Nada é obrigatório — todos os campos de identidade caem no fallback do perfil (FR1.4c)"""
        is_valid, errors = SchemaValidator.validate_agent_invite({})
        self.assertTrue(is_valid, errors)

    def test_name_length_constraint_rejects_short_name(self):
        """agent.name fora de 3-255 chars -> inválido, mesma regra de create_agent"""
        is_valid, errors = SchemaValidator.validate_agent_invite({"name": "Jo"})
        self.assertFalse(is_valid)
        self.assertTrue(any("name" in e for e in errors))

    def test_cpf_digit_count_constraint_rejects_invalid_cpf(self):
        """agent.cpf sem 11 dígitos -> inválido, mesma regra de create_agent"""
        is_valid, errors = SchemaValidator.validate_agent_invite({"cpf": "123"})
        self.assertFalse(is_valid)
        self.assertTrue(any("cpf" in e for e in errors))

    def test_email_format_constraint_rejects_invalid_email(self):
        """agent.email sem @/. -> inválido, mesma regra de create_agent"""
        is_valid, errors = SchemaValidator.validate_agent_invite({"email": "not-an-email"})
        self.assertFalse(is_valid)
        self.assertTrue(any("email" in e for e in errors))

    def test_creci_length_constraint_rejects_short_creci(self):
        """agent.creci com menos de 4 chars -> inválido, mesma regra de create_agent"""
        is_valid, errors = SchemaValidator.validate_agent_invite({"creci": "ab"})
        self.assertFalse(is_valid)
        self.assertTrue(any("creci" in e for e in errors))

    def test_company_id_and_user_id_keys_do_not_cause_validation_failure(self):
        """FR1.4b: se o cliente enviar company_id/user_id, o schema NÃO rejeita
        (a barreira real é o filtro allowed_keys no controller, Task 4) —
        aqui confirmamos apenas que a presença dessas chaves não gera 400."""
        is_valid, errors = SchemaValidator.validate_agent_invite(
            {"name": "Valid Name", "company_id": 999, "user_id": 5}
        )
        self.assertTrue(is_valid, errors)

    def test_constraints_are_the_same_object_as_agent_create_schema(self):
        """Reaproveitamento por referência (não cópia) — evita divergência silenciosa"""
        self.assertIs(
            SchemaValidator.AGENT_INVITE_SCHEMA["constraints"],
            SchemaValidator.AGENT_CREATE_SCHEMA["constraints"],
        )
```

- [ ] **Passo 2: Rodar o teste e confirmar que falha**

```
cd 18.0
docker compose exec odoo odoo -d realestate --test-tags /quicksol_estate:TestSchemaAgentInvite --test-enable --stop-after-init
```
Esperado: FALHA com `AttributeError: type object 'SchemaValidator' has no attribute 'AGENT_INVITE_SCHEMA'` (ou `validate_agent_invite`).

- [ ] **Passo 3: Implementar o schema e o método de validação**

Em `18.0/extra-addons/quicksol_estate/controllers/utils/schema.py`, logo após o fechamento do dict `AGENT_CREATE_SCHEMA` (linha 55), inserir:
```python
    # Feature 026: agent invite schema — paridade total com AGENT_CREATE_SCHEMA,
    # exceto company_id/user_id (sempre derivados no servidor, ver invite_controller.py)
    AGENT_INVITE_SCHEMA = {
        "required": [],
        "optional": [
            "name",
            "cpf",
            "email",
            "phone",
            "mobile",
            "creci",
            "hire_date",
            "bank_name",
            "bank_account",
            "pix_key",
        ],
        "types": AGENT_CREATE_SCHEMA["types"],
        "constraints": AGENT_CREATE_SCHEMA["constraints"],
    }
```
E logo após o método `validate_agent_create` (linha 388), inserir:
```python
    @staticmethod
    def validate_agent_invite(data):
        """Validate the optional 'agent' object inside POST /api/v1/users/invite. Feature 026."""
        return SchemaValidator.validate_request(
            data, SchemaValidator.AGENT_INVITE_SCHEMA
        )
```

- [ ] **Passo 4: Rodar o teste e confirmar que passa**

```
cd 18.0
docker compose exec odoo odoo -d realestate -u quicksol_estate --stop-after-init
docker compose exec odoo odoo -d realestate --test-tags /quicksol_estate:TestSchemaAgentInvite --test-enable --stop-after-init
```
Esperado: PASSA (8 testes).

- [ ] **Passo 5: Commit**

```bash
git add 18.0/extra-addons/quicksol_estate/controllers/utils/schema.py \
        18.0/extra-addons/quicksol_estate/tests/unit/test_schema_agent_invite.py
git commit -m "feat(quicksol_estate): add AGENT_INVITE_SCHEMA reusing AGENT_CREATE_SCHEMA constraints"
```

---

### Task 3: Teste de caracterização do reaproveitamento de campos (`agent.py::create()`)

Esta tarefa NÃO altera código de produção — `real.estate.agent.create()` (linhas 436-470) já implementa o fallback via `setdefault()`. O objetivo é ter uma rede de segurança de regressão ANTES de conectar o controller a esse mecanismo na Task 4, provando que ele funciona exatamente como a Task 4 vai assumir.

**Arquivos:**
- Teste: `18.0/extra-addons/quicksol_estate/tests/integration/test_agent_create_from_profile_and_user.py` (NÃO em `tests/unit/` — esta classe usa `self.env`/DB, e precisa de `TransactionCase` real; `tests/unit/` deste projeto é reservado para `unittest.TestCase` puro, sem Odoo/DB, ver Restrições Globais)
- Modificar: `18.0/extra-addons/quicksol_estate/tests/integration/__init__.py` (adicionar `from . import test_agent_create_from_profile_and_user` — sem esse import explícito, o Odoo nunca descobre o arquivo, mesmo sendo `TransactionCase`)

**Interfaces:**
- Consome: `real.estate.agent.create()` (já existente, `agent.py:436-470`), `thedevkitchen.estate.profile` (já existente).
- Produz: nenhuma interface nova — apenas confirma o contrato que a Task 4 vai depender.

- [ ] **Passo 1: Escrever os testes de caracterização (devem passar imediatamente, sem mudança de código)**

```python
# 18.0/extra-addons/quicksol_estate/tests/integration/test_agent_create_from_profile_and_user.py
# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestAgentCreateFromProfileAndUser(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company_a = self.env["res.company"].create({"name": "Seed Company A 026"})
        self.company_b = self.env["res.company"].create({"name": "Seed Company B 026"})
        self.profile_type_agent = self.env["thedevkitchen.profile.type"].search(
            [("code", "=", "agent")], limit=1
        )
        self.profile = self.env["thedevkitchen.estate.profile"].create({
            "name": "Profile Name",
            "company_id": self.company_a.id,
            "profile_type_id": self.profile_type_agent.id,
            "document": "11122233396",
            "email": "profile@example.com",
            "phone": "1130000000",
            "mobile": "11999998888",
            "birthdate": "1990-01-01",
        })
        self.user_in_company_b = self.env["res.users"].create({
            "name": "User In Company B",
            "login": "user_company_b_026@example.com",
            "company_id": self.company_b.id,
            "company_ids": [(6, 0, [self.company_b.id])],
        })

    def test_omitted_identity_fields_fall_back_to_profile(self):
        """FR1.4c: name/cpf/email/phone/mobile ausentes -> usam o valor do profile"""
        agent = self.env["real.estate.agent"].create({
            "profile_id": self.profile.id,
            "user_id": self.user_in_company_b.id,
        })
        self.assertEqual(agent.name, "Profile Name")
        self.assertEqual(agent.cpf, "11122233396")  # document -> cpf
        self.assertEqual(agent.email, "profile@example.com")
        self.assertEqual(agent.phone, "1130000000")
        self.assertEqual(agent.mobile, "11999998888")

    def test_explicit_identity_fields_override_profile(self):
        """FR1.4: valores explícitos vencem o fallback do perfil"""
        agent = self.env["real.estate.agent"].create({
            "profile_id": self.profile.id,
            "user_id": self.user_in_company_b.id,
            "name": "Explicit Override Name",
            "email": "override@example.com",
        })
        self.assertEqual(agent.name, "Explicit Override Name")
        self.assertEqual(agent.email, "override@example.com")
        self.assertEqual(agent.cpf, "11122233396")  # não sobrescrito -> ainda vem do profile

    def test_user_id_is_set_on_created_agent(self):
        """FR2.1b: o registro criado deve ter user_id, não só profile_id"""
        agent = self.env["real.estate.agent"].create({
            "profile_id": self.profile.id,
            "user_id": self.user_in_company_b.id,
        })
        self.assertEqual(agent.user_id.id, self.user_in_company_b.id)
        self.assertEqual(agent.profile_id.id, self.profile.id)

    def test_company_id_derives_from_profile_not_from_user(self):
        """FR1.4b/spec 'Achado': quando profile_id e user_id são passados juntos,
        company_id deve refletir profile.company_id (empresa A), NÃO
        user.company_ids[0] (empresa B) — confirma a ordem de precedência
        entre os dois blocos de sincronização em agent.py:436-470."""
        agent = self.env["real.estate.agent"].create({
            "profile_id": self.profile.id,
            "user_id": self.user_in_company_b.id,
        })
        self.assertEqual(
            agent.company_id.id,
            self.company_a.id,
            "company_id deveria vir do profile (empresa A), não do user (empresa B)",
        )
```

- [ ] **Passo 2: Adicionar o import explícito em `tests/integration/__init__.py`**

Abrir `18.0/extra-addons/quicksol_estate/tests/integration/__init__.py` e adicionar, junto aos demais imports já existentes (ex.: perto de `from . import test_event_bus_integration`):
```python
from . import test_agent_create_from_profile_and_user
```

- [ ] **Passo 3: Rodar os testes e confirmar que PASSAM imediatamente (caracterização, não TDD-de-código-novo)**

```
cd 18.0
docker compose exec odoo odoo -d realestate -u quicksol_estate --test-enable --stop-after-init --log-level=test --http-port=8988 2>&1 | tee /tmp/task3_test.log
grep -c "0 tests" /tmp/task3_test.log  # deve ser 0 (ou seja, a string "0 tests" NÃO deve aparecer)
grep "tests when loading" /tmp/task3_test.log  # confirma "0 failed, 0 error(s) of N tests" com N > 0
```
Esperado: PASSA já na primeira execução, e a contagem de testes (`N tests`) aumenta em 4 em relação à execução da mesma linha antes deste passo (rode uma vez antes de escrever o teste para ter a contagem-base, se quiser confirmar que os 4 novos foram de fato descobertos) — isso confirma que o mecanismo de `agent.py:436-470` funciona exatamente como a Task 4 vai assumir. **Se qualquer um destes testes falhar aqui, PARE** — significa que a premissa da Task 4 (reaproveitar esse mecanismo sem duplicá-lo) está incorreta para o estado atual do código, e a Task 4 precisa ser redesenhada antes de prosseguir. **Se a string "0 tests" aparecer**, o import do Passo 2 não foi aplicado corretamente — conferir antes de qualquer outra coisa.

- [ ] **Passo 4: Commit**

```bash
git add 18.0/extra-addons/quicksol_estate/tests/integration/test_agent_create_from_profile_and_user.py \
        18.0/extra-addons/quicksol_estate/tests/integration/__init__.py
git commit -m "test(quicksol_estate): characterize agent.create() profile/user setdefault mechanism"
```

---

### Task 4: `invite_controller.py::invite_user` — vínculo/criação atômica do agente (upsert) + teste E2E do fluxo feliz

Esta é a tarefa central. Como este projeto testa o comportamento HTTP real via scripts curl (não `HttpCase`, por sua limitação de transação somente-leitura — ver `CLAUDE.md` §10), o ciclo TDD aqui é: escrever o script curl primeiro, rodá-lo contra o código atual (falha), implementar a mudança no controller, rodar de novo (passa).

**⚠️ ACHADO CRÍTICO DURANTE A EXECUÇÃO (2026-07-19), CORRIGIDO NESTA VERSÃO DA TASK — leia antes de implementar**: `profile_api.py` (`POST /api/v1/profiles`, código pré-existente da Feature 010, linhas 236-255, NÃO faz parte desta feature) **já cria automaticamente** um `real.estate.agent` (com `profile_id`, `name`, `cpf`, `email`, `phone`, `mobile`, `company_id`, `hire_date` — mas `user_id` nulo) sempre que o perfil criado é do tipo `agent`. Isso significa que, no momento em que `POST /api/v1/users/invite` é chamado (a precondição do fluxo feliz: "perfil já criado via `POST /api/v1/profiles`"), **um `real.estate.agent` para aquele `profile_id` já existe**. Um `create()` cego (como uma versão anterior desta task especificava) colide com esse registro na restrição `UNIQUE(cpf, company_id)` (`_sql_constraints`, `agent.py:218-224`), gerando `psycopg2.errors.UniqueViolation` — que **não** é `ValidationError` e vazaria como 500 depois que `res.users`/token já teriam sido criados, quebrando a atomicidade (FR2.2). Isso foi reproduzido ao vivo via `odoo shell` durante uma tentativa anterior de implementação desta task, e não é um caso extremo: acontece 100% das vezes que um perfil `agent` é criado pela API real antes do convite, que é a única forma como perfis são criados na prática. **A correção (confirmada com o solicitante): semântica de upsert** — buscar (`search`) um `real.estate.agent` existente por `profile_id` antes de decidir entre `write()` (se existir — caso normal) ou `create()` (se não existir — caso defensivo/legado). Os passos abaixo já refletem essa correção.

**Arquivos:**
- Modificar: `18.0/extra-addons/thedevkitchen_user_onboarding/controllers/invite_controller.py:33-171`
- Criar: `integration_tests/test_us026_s1_invite_agent_unification.sh`

**Interfaces:**
- Consome: `SchemaValidator.validate_agent_invite` (Task 2), `real.estate.agent.create()`/`.write()` (Task 3 provou o mecanismo de fallback do `create()`; `write()` não tem esse mecanismo — não precisa, já que os campos de identidade já vieram do `profile_api.py`), `InviteService.create_user_from_profile` (já existente, `invite_service.py:189-256`, inalterado).
- Produz: resposta `201` de `POST /api/v1/users/invite` com `data.agent_id` (novo campo) e `links.agent` (novo link) quando `profile_type == 'agent'`.

- [ ] **Passo 1: Escrever o script E2E que falha (parte 1 — fluxo feliz + paridade de campos)**

```bash
#!/bin/bash
# integration_tests/test_us026_s1_invite_agent_unification.sh
# Feature 026 — User Story 1: convite unificado cria real.estate.agent
# vinculado a profile_id E user_id, com paridade total de campos.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../18.0/.env" 2>/dev/null || true
BASE_URL="${BASE_URL:-http://localhost:8069}"

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

assert_status() {
  local expected="$1" actual="$2" label="$3"
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ "$actual" = "$expected" ]; then
    echo "PASS: $label (status $actual)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "FAIL: $label (expected $expected, got $actual)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
}

assert_field_value() {
  local body="$1" jq_path="$2" expected="$3" label="$4"
  local actual
  actual=$(echo "$body" | jq -r "$jq_path")
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ "$actual" = "$expected" ]; then
    echo "PASS: $label ($jq_path = $actual)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "FAIL: $label (expected $jq_path = $expected, got $actual)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
}

cleanup_test_data() {
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM res_users WHERE login LIKE 'us026_%@example.com';" >/dev/null 2>&1
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM thedevkitchen_estate_profile WHERE email LIKE 'us026_%@example.com';" >/dev/null 2>&1
}

cleanup_test_data

# --- Auth (mesmo padrão de test_us9_s6_resend_invite.sh) ---
BEARER_TOKEN=$(curl -s -X POST "${BASE_URL}/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d "{\"grant_type\":\"client_credentials\",\"client_id\":\"${OAUTH_CLIENT_ID}\",\"client_secret\":\"${OAUTH_CLIENT_SECRET}\"}" \
  | jq -r '.access_token')

LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d "{\"login\":\"${TEST_USER_MANAGER}\",\"password\":\"${TEST_PASSWORD_MANAGER}\"}")
# CORRIGIDO (achado 2026-07-19): a resposta de /api/v1/users/login NÃO tem wrapper .data —
# os campos vêm direto na raiz, confirmado contra o container ao vivo e contra
# test_us9_s6_resend_invite.sh (que já lê .session_id/.user.default_company_id sem .data).
SESSION_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.session_id')
COMPANY_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.user.default_company_id')

AUTH_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${SESSION_ID}" -H "X-Company-ID: ${COMPANY_ID}")

# --- Resolve o FK inteiro de profile_type_id (achado 2026-07-19: profile_api.py exige um
# inteiro de thedevkitchen_profile_type.id, NÃO a string "agent" — profile_api.py:174-182) ---
AGENT_PROFILE_TYPE_ID=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM thedevkitchen_profile_type WHERE code = 'agent' LIMIT 1;" | tr -d '[:space:]')

# --- Cria o profile (pré-requisito — profile_id continua obrigatório, decisão confirmada).
# NOTA: isso já dispara profile_api.py:236-255, que auto-cria um real_estate_agent para este
# profile_id (sem user_id) — é exatamente esse registro que o convite abaixo deve vincular
# (write), não duplicar (create). Ver o "Achado Crítico" no topo desta task. ---
PROFILE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{
    "name": "US026 Agent Pending",
    "company_id": '"${COMPANY_ID}"',
    "document": "39053344705",
    "email": "us026_agent_pending@example.com",
    "birthdate": "1990-01-01",
    "profile_type_id": '"${AGENT_PROFILE_TYPE_ID}"'
  }')
PROFILE_BODY=$(echo "$PROFILE_RESPONSE" | sed '$d')
PROFILE_STATUS=$(echo "$PROFILE_RESPONSE" | tail -n 1)
assert_status "201" "$PROFILE_STATUS" "profile creation"
PROFILE_ID=$(echo "$PROFILE_BODY" | jq -r '.data.id')

# --- Confirma a premissa do achado: profile_api.py já criou um real_estate_agent órfão ---
PRE_EXISTING_COUNT=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM real_estate_agent WHERE profile_id = ${PROFILE_ID};" | tr -d '[:space:]')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$PRE_EXISTING_COUNT" = "1" ]; then
  echo "PASS: profile_api.py auto-created exactly 1 real_estate_agent row for this profile (as expected)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: expected exactly 1 pre-existing real_estate_agent row, got $PRE_EXISTING_COUNT — the achado's premise may no longer hold, investigate before trusting the rest of this script"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Convite com paridade total de campos no nó agent ---
INVITE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{
    "profile_id": '"${PROFILE_ID}"',
    "agent": {
      "creci": "CRECI-SP 999999",
      "hire_date": "2026-01-15",
      "bank_name": "Banco Teste",
      "bank_account": "12345-6",
      "pix_key": "us026_agent_pending@example.com"
    }
  }')
INVITE_BODY=$(echo "$INVITE_RESPONSE" | sed '$d')
INVITE_STATUS=$(echo "$INVITE_RESPONSE" | tail -n 1)
assert_status "201" "$INVITE_STATUS" "invite with agent object"
assert_field_value "$INVITE_BODY" '.data.profile_id' "$PROFILE_ID" "response has profile_id"

AGENT_ID=$(echo "$INVITE_BODY" | jq -r '.data.agent_id')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$AGENT_ID" != "null" ] && [ -n "$AGENT_ID" ]; then
  echo "PASS: response includes agent_id ($AGENT_ID)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: response missing agent_id"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

AGENT_LINK=$(echo "$INVITE_BODY" | jq -r '.links.agent')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$AGENT_LINK" = "/api/v1/agents/${AGENT_ID}" ]; then
  echo "PASS: links.agent present and correct"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: links.agent missing or wrong (got $AGENT_LINK)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Verifica no banco: profile_id E user_id ambos preenchidos no mesmo registro ---
USER_ID=$(echo "$INVITE_BODY" | jq -r '.data.id')
DB_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT profile_id, user_id, creci FROM real_estate_agent WHERE id = ${AGENT_ID};")
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$DB_CHECK" | grep -q "${PROFILE_ID}|${USER_ID}|CRECI-SP 999999"; then
  echo "PASS: real_estate_agent row has BOTH profile_id and user_id set, plus creci"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: real_estate_agent row missing profile_id/user_id/creci (got: $DB_CHECK)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Confirma semântica de upsert: ainda existe SÓ 1 linha para este profile_id (write, não
# um segundo create() duplicado) — e é a MESMA linha que profile_api.py já tinha criado ---
POST_INVITE_COUNT=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM real_estate_agent WHERE profile_id = ${PROFILE_ID};" | tr -d '[:space:]')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$POST_INVITE_COUNT" = "1" ]; then
  echo "PASS: exactly 1 real_estate_agent row for this profile_id after invite (upsert, not duplicate create)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: expected exactly 1 real_estate_agent row after invite, got $POST_INVITE_COUNT (duplicate create() instead of upsert write()?)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

cleanup_test_data

echo ""
echo "=== US026-S1: $TESTS_PASSED/$TESTS_RUN passed ==="
if [ "$TESTS_FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
```

Tornar executável: `chmod +x integration_tests/test_us026_s1_invite_agent_unification.sh`

- [ ] **Passo 2: Rodar o script e confirmar que falha**

```
cd 18.0 && docker compose up -d
cd ..
./integration_tests/test_us026_s1_invite_agent_unification.sh
```
Esperado: os dois asserts novos ("profile_api.py auto-created exactly 1 real_estate_agent row" e "exactly 1 real_estate_agent row for this profile_id after invite") já devem PASSAR mesmo sem nenhuma mudança de código, já que `profile_api.py` já auto-cria o registro hoje. O que deve FALHAR é "response includes agent_id" e "real_estate_agent row has BOTH profile_id and user_id set, plus creci" — o registro já existe, mas `user_id` continua nulo e o convite hoje não mexe nele.

- [ ] **Passo 3: Implementar a mudança em `invite_controller.py::invite_user`**

Em `18.0/extra-addons/thedevkitchen_user_onboarding/controllers/invite_controller.py`, confirmar/adicionar o import no topo do arquivo (junto aos demais imports):
```python
from odoo.addons.quicksol_estate.controllers.utils.schema import SchemaValidator
```

Logo após a linha que lê `profile_type = profile_record.profile_type_id.code` (dentro do bloco existente "Extract company and profile data"), adicionar a leitura do payload e a validação, **antes** da checagem de autorização e da criação do usuário (FR1.5 — falhar rápido, antes de qualquer `res.users`):
```python
            # Feature 026: read optional 'agent' object, validate BEFORE any res.users is created
            agent_payload = data.get("agent")
            if profile_type == "agent" and agent_payload:
                is_valid, errors = SchemaValidator.validate_agent_invite(agent_payload)
                if not is_valid:
                    return self._error_response(
                        400, "validation_error", ", ".join(errors)
                    )
```

Logo após o bloco existente que cria o usuário (`user = invite_service.create_user_from_profile(...)`, dentro do mesmo `try`, depois do `except ValidationError` correspondente) e **antes** da geração do token de convite, adicionar o vínculo/criação atômica do agente — **semântica de upsert** (achado 2026-07-19: `profile_api.py` já auto-cria o registro sem `user_id`; buscar antes de decidir entre `write()`/`create()`, para não colidir em `UNIQUE(cpf, company_id)`):
```python
            # Feature 026: link (or, defensively, create) real.estate.agent atomically,
            # linked to BOTH profile and login (FR2.1, FR2.1b).
            # Upsert semantics: profile_api.py (Feature 010) already auto-creates a
            # real.estate.agent (without user_id) whenever the profile is type 'agent' —
            # a blind create() here would collide on UNIQUE(cpf, company_id).
            agent_id = None
            if profile_type == "agent":
                allowed_agent_keys = {
                    "name", "cpf", "email", "phone", "mobile",
                    "creci", "hire_date", "bank_name", "bank_account", "pix_key",
                }
                explicit_fields = {
                    k: v for k, v in (agent_payload or {}).items()
                    if k in allowed_agent_keys and v is not None
                }
                Agent = request.env["real.estate.agent"].sudo()
                existing_agent = Agent.search(
                    [("profile_id", "=", profile_record.id)], limit=1
                )
                try:
                    if existing_agent:
                        existing_agent.write({"user_id": user.id, **explicit_fields})
                        agent_record = existing_agent
                    else:
                        agent_record = Agent.create({
                            "profile_id": profile_record.id,
                            "user_id": user.id,
                            **explicit_fields,
                        })
                except ValidationError as e:
                    return self._error_response(409, "conflict", str(e))
                agent_id = agent_record.id
```

No dicionário `response_data` (logo após ele ser montado, antes de `if not email_sent:`), adicionar:
```python
            if agent_id:
                response_data["agent_id"] = agent_id
```

No dicionário `links` (logo após ele ser montado, antes do `return self._success_response(...)`), adicionar:
```python
            if agent_id:
                links["agent"] = f"/api/v1/agents/{agent_id}"
```

- [ ] **Passo 4: Bump de versão do manifest**

Em `18.0/extra-addons/thedevkitchen_user_onboarding/__manifest__.py`, alterar `"version": "18.0.1.0.0"` para `"version": "18.0.2.0.0"`.

- [ ] **Passo 5: Fazer upgrade do módulo e rodar o script de novo**

```
cd 18.0
docker compose exec odoo odoo -d realestate -u thedevkitchen_user_onboarding --stop-after-init
cd ..
./integration_tests/test_us026_s1_invite_agent_unification.sh
```
Esperado: PASSA (todas as asserções).

- [ ] **Passo 6: Commit**

```bash
git add 18.0/extra-addons/thedevkitchen_user_onboarding/controllers/invite_controller.py \
        18.0/extra-addons/thedevkitchen_user_onboarding/__manifest__.py \
        integration_tests/test_us026_s1_invite_agent_unification.sh
git commit -m "feat(thedevkitchen_user_onboarding): link/create real.estate.agent atomically during invite (upsert by profile_id)"
```

---

### Task 5: E2E — validação de campos, conflito, atomicidade e filtragem de `company_id`/`user_id`

**Arquivos:**
- Modificar: `integration_tests/test_us026_s1_invite_agent_unification.sh` (adicionar cenários ao mesmo script da Task 4)

**Interfaces:**
- Consome: o mesmo endpoint e controller da Task 4 (nenhuma mudança de código de produção nesta tarefa).

- [ ] **Passo 1: Adicionar os cenários de erro ao script, antes da linha `cleanup_test_data` final**

```bash
# --- Cenário: agent.creci mal formado -> 400, nenhum registro criado ---
BAD_CRECI_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Bad Creci","company_id":'"${COMPANY_ID}"',"document":"52998224725","email":"us026_bad_creci@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}')
BAD_CRECI_PROFILE_ID=$(echo "$BAD_CRECI_RESPONSE" | sed '$d' | jq -r '.data.id')

INVALID_INVITE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${BAD_CRECI_PROFILE_ID}"',"agent":{"creci":"ab"}}')
INVALID_INVITE_STATUS=$(echo "$INVALID_INVITE" | tail -n 1)
assert_status "400" "$INVALID_INVITE_STATUS" "creci too short returns 400"

# Atomicidade (FR2.2): nenhum res.users deve ter sido criado para este profile
ATOMIC_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE p.email = 'us026_bad_creci@example.com';")
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$(echo "$ATOMIC_CHECK" | tr -d '[:space:]')" = "0" ]; then
  echo "PASS: atomic rollback — no res.users created after creci validation failure"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: atomic rollback — a res.users row exists despite the 400 (got count: $ATOMIC_CHECK)"
  echo "  ACTION IF THIS FAILS: add request.env.cr.rollback() before the 409/400 return"
  echo "  inside invite_controller.py's new agent-creation except block, then re-run."
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Cenário: CRECI duplicado na mesma empresa -> 409 ---
DUP_PROFILE_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Dup Creci","company_id":'"${COMPANY_ID}"',"document":"91129418804","email":"us026_dup_creci@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}')
DUP_PROFILE_ID=$(echo "$DUP_PROFILE_RESPONSE" | jq -r '.data.id')

FIRST_INVITE=$(curl -s -X POST "${BASE_URL}/api/v1/users/invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${DUP_PROFILE_ID}"',"agent":{"creci":"CRECI-SP 555555"}}')

DUP_PROFILE2_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Dup Creci 2","company_id":'"${COMPANY_ID}"',"document":"15350946056","email":"us026_dup_creci_2@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}')
DUP_PROFILE2_ID=$(echo "$DUP_PROFILE2_RESPONSE" | jq -r '.data.id')

DUP_INVITE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${DUP_PROFILE2_ID}"',"agent":{"creci":"CRECI-SP 555555"}}')
DUP_INVITE_STATUS=$(echo "$DUP_INVITE" | tail -n 1)
assert_status "409" "$DUP_INVITE_STATUS" "duplicate creci in same company returns 409"

# --- Cenário: cliente envia company_id/user_id no nó agent -> ignorados silenciosamente ---
SPOOF_PROFILE_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Spoof Test","company_id":'"${COMPANY_ID}"',"document":"74954510736","email":"us026_spoof@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}')
SPOOF_PROFILE_ID=$(echo "$SPOOF_PROFILE_RESPONSE" | jq -r '.data.id')

SPOOF_INVITE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${SPOOF_PROFILE_ID}"',"agent":{"company_id":999999,"user_id":999999,"creci":"CRECI-SP 777777"}}')
SPOOF_STATUS=$(echo "$SPOOF_INVITE" | tail -n 1)
assert_status "201" "$SPOOF_STATUS" "company_id/user_id in agent node do not cause a 400"

SPOOF_AGENT_ID=$(echo "$SPOOF_INVITE" | sed '$d' | jq -r '.data.agent_id')
SPOOF_DB_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT company_id FROM real_estate_agent WHERE id = ${SPOOF_AGENT_ID};")
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$(echo "$SPOOF_DB_CHECK" | tr -d '[:space:]')" = "${COMPANY_ID}" ]; then
  echo "PASS: spoofed company_id (999999) ignored, real company_id (${COMPANY_ID}) persisted"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: company_id spoofing NOT blocked (got: $SPOOF_DB_CHECK, expected ${COMPANY_ID})"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi
```

- [ ] **Passo 2: Rodar o script inteiro e confirmar que todos os cenários passam**

```
./integration_tests/test_us026_s1_invite_agent_unification.sh
```
Esperado: PASSA (todos). Se o cenário de atomicidade falhar, seguir a instrução impressa no próprio output do script (adicionar `request.env.cr.rollback()` no bloco `except ValidationError` da Task 4/Passo 3, dentro do `if profile_type == "agent":` de criação do agente, imediatamente antes do `return self._error_response(409, ...)`), fazer upgrade do módulo e rodar de novo.

- [ ] **Passo 3: Commit**

```bash
git add integration_tests/test_us026_s1_invite_agent_unification.sh
git commit -m "test(integration): add validation/conflict/spoofing scenarios for agent invite"
```

---

### Task 6: E2E — agente convidado enxerga seus próprios imóveis/leads (fecha a lacuna de RBAC da Feature 025)

Este é o teste mais importante da feature — prova que `user_id` corrigido realmente resolve o problema original, não apenas que o registro foi criado.

**Arquivos:**
- Criar: `integration_tests/test_us026_s1_rbac_visibility.sh`

**Interfaces:**
- Consome: endpoint da Task 4, `GET /api/v1/properties` e `GET /api/v1/leads` (já existentes, inalterados), fluxo de "set password" já existente (`thedevkitchen_user_onboarding`).

- [ ] **Passo 1: Escrever o script (falha contra o código pré-Task 4, mas como a Task 4 já foi aplicada, este roda depois — ver nota abaixo)**

```bash
#!/bin/bash
# integration_tests/test_us026_s1_rbac_visibility.sh
# Feature 026 — prova que o agente convidado vê seus próprios imóveis/leads
# (o bug que a Feature 025 deixaria aberto: profile_id setado, user_id não).
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../18.0/.env" 2>/dev/null || true
BASE_URL="${BASE_URL:-http://localhost:8069}"
TESTS_RUN=0; TESTS_PASSED=0; TESTS_FAILED=0

assert_status() {
  local expected="$1" actual="$2" label="$3"
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ "$actual" = "$expected" ]; then echo "PASS: $label"; TESTS_PASSED=$((TESTS_PASSED + 1));
  else echo "FAIL: $label (expected $expected, got $actual)"; TESTS_FAILED=$((TESTS_FAILED + 1)); fi
}

cleanup() {
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_property WHERE name = 'US026 RBAC Test Property';" >/dev/null 2>&1
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM res_users WHERE login = 'us026_rbac_agent@example.com';" >/dev/null 2>&1
}
cleanup

BEARER_TOKEN=$(curl -s -X POST "${BASE_URL}/api/v1/auth/token" -H "Content-Type: application/json" \
  -d "{\"grant_type\":\"client_credentials\",\"client_id\":\"${OAUTH_CLIENT_ID}\",\"client_secret\":\"${OAUTH_CLIENT_SECRET}\"}" \
  | jq -r '.access_token')
LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d "{\"login\":\"${TEST_USER_MANAGER}\",\"password\":\"${TEST_PASSWORD_MANAGER}\"}")
# CORRIGIDO (achado 2026-07-19): sem wrapper .data, ver nota na Task 4
SESSION_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.session_id')
COMPANY_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.user.default_company_id')
AUTH_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${SESSION_ID}" -H "X-Company-ID: ${COMPANY_ID}")

# Resolve o FK inteiro de profile_type_id (achado 2026-07-19, ver Task 4)
AGENT_PROFILE_TYPE_ID=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM thedevkitchen_profile_type WHERE code = 'agent' LIMIT 1;" | tr -d '[:space:]')

# 1. Cria profile + convite
PROFILE_ID=$(curl -s -X POST "${BASE_URL}/api/v1/profiles" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 RBAC Agent","company_id":'"${COMPANY_ID}"',"document":"60011239301","email":"us026_rbac_agent@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}' \
  | jq -r '.data.id')
INVITE_BODY=$(curl -s -X POST "${BASE_URL}/api/v1/users/invite" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${PROFILE_ID}"',"agent":{"creci":"CRECI-SP 888888"}}')
NEW_USER_ID=$(echo "$INVITE_BODY" | jq -r '.data.id')
NEW_AGENT_ID=$(echo "$INVITE_BODY" | jq -r '.data.agent_id')

# 2. Força a senha diretamente no banco (mesmo padrão usado em test_us9_s6_resend_invite.sh
#    para contornar o fluxo de e-mail em ambiente de teste)
docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
  "UPDATE res_users SET password='rbac_test_pass_026', signup_pending=FALSE WHERE id = ${NEW_USER_ID};" >/dev/null

# 3. Cria um imóvel atribuído ao NOVO agente
docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
  "INSERT INTO real_estate_property (name, company_id, agent_id, active) VALUES ('US026 RBAC Test Property', ${COMPANY_ID}, ${NEW_AGENT_ID}, TRUE);" >/dev/null

# 4. Login como o agente recém-convidado
AGENT_LOGIN=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d '{"login":"us026_rbac_agent@example.com","password":"rbac_test_pass_026"}')
AGENT_SESSION_ID=$(echo "$AGENT_LOGIN" | jq -r '.session_id')  # sem wrapper .data, ver Task 4
AGENT_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${AGENT_SESSION_ID}" -H "X-Company-ID: ${COMPANY_ID}")

# 5. O PRÓPRIO teste da lacuna que a Feature 025 deixaria aberta:
PROPERTIES_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "${BASE_URL}/api/v1/properties" "${AGENT_HEADERS[@]}")
PROPERTIES_STATUS=$(echo "$PROPERTIES_RESPONSE" | tail -n 1)
PROPERTIES_BODY=$(echo "$PROPERTIES_RESPONSE" | sed '$d')
assert_status "200" "$PROPERTIES_STATUS" "invited agent can call GET /properties"

PROPERTY_COUNT=$(echo "$PROPERTIES_BODY" | jq '.data | length')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$PROPERTY_COUNT" -gt 0 ]; then
  echo "PASS: invited agent sees $PROPERTY_COUNT own propert(y/ies) — NOT an empty list"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: invited agent sees ZERO properties — the exact bug this feature exists to fix (user_id not linked)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

cleanup
echo ""
echo "=== US026-S1 RBAC visibility: $TESTS_PASSED/$TESTS_RUN passed ==="
[ "$TESTS_FAILED" -gt 0 ] && exit 1
exit 0
```

Tornar executável: `chmod +x integration_tests/test_us026_s1_rbac_visibility.sh`

- [ ] **Passo 2: Rodar o script**

```
./integration_tests/test_us026_s1_rbac_visibility.sh
```
Esperado: PASSA (já que a Task 4 foi implementada antes desta tarefa). Se este script for rodado ANTES da Task 4 (para confirmar que ele de fato captura o bug), o passo "PASS: invited agent sees" falharia com "FAIL: invited agent sees ZERO properties" — essa é a evidência de que o teste realmente exercita a lacuna da Feature 025.

- [ ] **Passo 3: Commit**

```bash
git add integration_tests/test_us026_s1_rbac_visibility.sh
git commit -m "test(integration): prove invited agent sees own properties via user_id link (closes Feature 025 gap)"
```

---

### Task 7: Regressão — reenvio de convite não recria o agente (User Story 2)

Nenhuma mudança de código de produção — `resend-invite` não passa por `create_user_from_profile`/pela nova lógica de criação de agente. Esta tarefa só adiciona cobertura de regressão.

**Arquivos:**
- Criar: `integration_tests/test_us026_s2_resend_invite_regression.sh`

- [ ] **Passo 1: Escrever o script**

```bash
#!/bin/bash
# integration_tests/test_us026_s2_resend_invite_regression.sh
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../18.0/.env" 2>/dev/null || true
BASE_URL="${BASE_URL:-http://localhost:8069}"
TESTS_RUN=0; TESTS_PASSED=0; TESTS_FAILED=0

cleanup() {
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM res_users WHERE login = 'us026_resend_agent@example.com';" >/dev/null 2>&1
}
cleanup

BEARER_TOKEN=$(curl -s -X POST "${BASE_URL}/api/v1/auth/token" -H "Content-Type: application/json" \
  -d "{\"grant_type\":\"client_credentials\",\"client_id\":\"${OAUTH_CLIENT_ID}\",\"client_secret\":\"${OAUTH_CLIENT_SECRET}\"}" \
  | jq -r '.access_token')
LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d "{\"login\":\"${TEST_USER_MANAGER}\",\"password\":\"${TEST_PASSWORD_MANAGER}\"}")
SESSION_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.session_id')  # sem wrapper .data, ver Task 4
COMPANY_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.user.default_company_id')
AUTH_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${SESSION_ID}" -H "X-Company-ID: ${COMPANY_ID}")

# Resolve o FK inteiro de profile_type_id (achado 2026-07-19, ver Task 4)
AGENT_PROFILE_TYPE_ID=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM thedevkitchen_profile_type WHERE code = 'agent' LIMIT 1;" | tr -d '[:space:]')

PROFILE_ID=$(curl -s -X POST "${BASE_URL}/api/v1/profiles" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Resend Agent","company_id":'"${COMPANY_ID}"',"document":"88817915058","email":"us026_resend_agent@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}' \
  | jq -r '.data.id')
FIRST_INVITE=$(curl -s -X POST "${BASE_URL}/api/v1/users/invite" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${PROFILE_ID}"',"agent":{"creci":"CRECI-SP 444444"}}')
USER_ID=$(echo "$FIRST_INVITE" | jq -r '.data.id')

AGENT_COUNT_BEFORE=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM real_estate_agent WHERE user_id = ${USER_ID};")

RESEND_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/${USER_ID}/resend-invite" "${AUTH_HEADERS[@]}")
RESEND_STATUS=$(echo "$RESEND_RESPONSE" | tail -n 1)
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$RESEND_STATUS" = "200" ] || [ "$RESEND_STATUS" = "201" ]; then
  echo "PASS: resend-invite succeeds"; TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: resend-invite returned $RESEND_STATUS"; TESTS_FAILED=$((TESTS_FAILED + 1))
fi

AGENT_COUNT_AFTER=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM real_estate_agent WHERE user_id = ${USER_ID};")
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$(echo "$AGENT_COUNT_BEFORE" | tr -d '[:space:]')" = "$(echo "$AGENT_COUNT_AFTER" | tr -d '[:space:]')" ]; then
  echo "PASS: agent count unchanged after resend-invite ($AGENT_COUNT_BEFORE == $AGENT_COUNT_AFTER)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: agent count changed after resend-invite (before: $AGENT_COUNT_BEFORE, after: $AGENT_COUNT_AFTER)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

cleanup
echo ""
echo "=== US026-S2: $TESTS_PASSED/$TESTS_RUN passed ==="
[ "$TESTS_FAILED" -gt 0 ] && exit 1
exit 0
```

Tornar executável: `chmod +x integration_tests/test_us026_s2_resend_invite_regression.sh`

- [ ] **Passo 2: Rodar e confirmar que passa**

```
./integration_tests/test_us026_s2_resend_invite_regression.sh
```

- [ ] **Passo 3: Commit**

```bash
git add integration_tests/test_us026_s2_resend_invite_regression.sh
git commit -m "test(integration): regression — resend-invite does not recreate agent record"
```

---

### Task 8: Documentação — OpenAPI/Swagger (registro `thedevkitchen.api.endpoint`)

**Arquivos:**
- Modificar: `18.0/extra-addons/thedevkitchen_user_onboarding/data/api_endpoints_data.xml:11-78`

> Consultar `.claude/skills/swagger-updater/SKILL.md` antes de editar — este projeto nunca edita OpenAPI estático à mão; o Swagger é gerado dinamicamente a partir da tabela `thedevkitchen.api.endpoint`, e este arquivo XML é a fonte de dados carregada no `data` do manifest.

- [ ] **Passo 1: Atualizar o registro `api_endpoint_users_invite`**

Em `18.0/extra-addons/thedevkitchen_user_onboarding/data/api_endpoints_data.xml`, dentro do `<field name="request_schema">` (CDATA, linhas ~40-56), substituir o schema atual (que já estava desatualizado em relação ao código antes desta feature — documentava `name`/`email`/`profile`/`cpf`/`phone` no nível raiz, quando o código real sempre exigiu apenas `profile_id`) por:
```xml
            <field name="request_schema"><![CDATA[
{
  "type": "object",
  "title": "InviteUserRequest",
  "required": ["profile_id"],
  "properties": {
    "profile_id": {"type": "integer", "example": 17, "description": "ID of an existing thedevkitchen.estate.profile record"},
    "agent": {
      "type": "object",
      "title": "AgentInviteExtra",
      "description": "Optional. Only used when the target profile's type is 'agent'. Mirrors AGENT_CREATE_SCHEMA's full field set except company_id/user_id (always server-derived).",
      "properties": {
        "name":         {"type": "string", "example": "Jane Agent"},
        "cpf":          {"type": "string", "example": "12345678901"},
        "email":        {"type": "string", "format": "email", "example": "jane@example.com"},
        "phone":        {"type": "string", "example": "1130000000"},
        "mobile":       {"type": "string", "example": "11999998888"},
        "creci":        {"type": "string", "example": "CRECI-SP 12345"},
        "hire_date":    {"type": "string", "format": "date", "example": "2026-01-15"},
        "bank_name":    {"type": "string", "example": "Banco do Brasil"},
        "bank_account": {"type": "string", "example": "12345-6"},
        "pix_key":      {"type": "string", "example": "jane@example.com"}
      }
    }
  }
}
]]></field>
```

Atualizar o `<field name="description">` para incluir, ao final do texto existente:
```
Feature 026: when the target profile's type is 'agent', an optional nested 'agent' object may be supplied with CRECI/bank/identity fields mirroring POST /api/v1/agents' full field set. company_id and user_id are never accepted in this object — always derived server-side. On success, the response includes agent_id and a 'links.agent' HATEOAS entry.
```

- [ ] **Passo 2: Fazer upgrade do módulo e verificar no Swagger UI**

```
cd 18.0
docker compose exec odoo odoo -d realestate -u thedevkitchen_user_onboarding --stop-after-init
```
Acessar `${BASE_URL}/api/docs` e confirmar que `POST /api/v1/users/invite` mostra o objeto `agent` no corpo da requisição.

- [ ] **Passo 3: Commit**

```bash
git add 18.0/extra-addons/thedevkitchen_user_onboarding/data/api_endpoints_data.xml
git commit -m "docs(thedevkitchen_user_onboarding): document agent object on invite endpoint, fix stale request_schema"
```

---

### Task 9: Documentação — Coleção Postman

> Consultar `.claude/skills/postman-collection-manager/SKILL.md` antes de editar — este projeto segue a ADR-016 para nomenclatura/versionamento/headers da coleção.

- [ ] **Passo 1: Localizar a pasta "User Onboarding" (ou equivalente) na coleção Postman do projeto e adicionar/atualizar o request "Invite Agent"**, incluindo no corpo de exemplo o objeto `agent` completo (mesmos 10 campos documentados na Task 8), seguindo exatamente a estrutura de headers/variáveis/scripts de auto-save de token já usada pelos demais requests da coleção (per skill).

- [ ] **Passo 2: Bump de versão da coleção conforme convenção ADR-016 (skill `postman-collection-manager` define o formato exato).**

- [ ] **Passo 3: Commit**

```bash
git add docs/postman/  # ou o caminho real da coleção, confirmar com a skill
git commit -m "docs(postman): add agent object example to Invite Agent request"
```

---

## Autorrevisão do Plano

**1. Cobertura da spec** — mapeamento tarefa → requisito:
- FR1 (validação de campos, paridade total, `company_id`/`user_id` excluídos) → Tasks 2, 4, 5.
- FR1.4c (reaproveitamento de campos já existente) → Task 3 (caracterização) + Task 4 (uso sem duplicação).
- FR2 (criação atômica, `user_id` obrigatório) → Task 4, 5.
- FR3 (contrato de resposta, `agent_id`/link) → Task 4.
- FR4 (autorização inalterada) → nenhuma mudança de código necessária (já existente); coberto implicitamente pelos testes de 403 já existentes em `test_invite_authorization.py` — não duplicado neste plano.
- FR6 (índice + cobertura de RBAC) → Task 1 (índice), Task 6 (visibilidade).
- User Story 2 (resend-invite) → Task 7.
- User Story 3 (remoção de `POST /api/v1/agents`) → **fora deste plano**, ver seção abaixo.
- NFR2 (performance/índice) → Task 1.
- Documentação (OpenAPI/Postman) → Tasks 8, 9.

**2. Varredura de placeholders**: nenhum "TBD"/"TODO"/"implementar depois" encontrado — todo passo tem código completo ou comando exato.

**3. Consistência de tipos/nomes**: `agent_vals`, `allowed_agent_keys`, `AGENT_INVITE_SCHEMA`, `validate_agent_invite` usados de forma idêntica em Task 2/3/4 — conferido.

---

## Fora deste Plano (por decisão explícita do usuário/spec)

- **Remoção de `POST /api/v1/agents`** (User Story 3 / FR5) — depende de pré-condições de produção (tráfego residual aceito, autorização explícita de merge) que não podem ser satisfeitas durante a implementação inicial. Requer um plano de acompanhamento próprio quando essas pré-condições forem atendidas.
- **Correção da checagem de `company_id` ausente em `invite_user`** — achado de segurança registrado na spec, explicitamente fora de escopo, candidato a `specs/027-...`.
- **Tornar `profile_id` opcional / criação de perfil inline** — considerado e descartado.
- Atualização da Constituição do projeto (Padrão de Identidade com Vínculo Duplo, Substituição Direta) — a fazer após a implementação estar validada em produção, per spec.
