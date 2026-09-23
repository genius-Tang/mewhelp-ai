# Chapter 2 Function Calling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a chapter-two snapshot whose existing SSE customer-service chat can select and execute exactly one LangChain tool, persist the complete trace in MySQL, and stream a grounded final answer with a visible tool badge.

**Architecture:** A `ChatOrchestrator` owns the fixed selector → optional tool → unbound finalizer flow. A SQLAlchemy repository provides short-lived async transactions, a registry/executor validates and runs five `@tool` tools, and the FastAPI route maps typed domain events to the existing SSE protocol. The browser stores only stable user/conversation identifiers; MySQL is the source of conversation history.

**Tech Stack:** Python 3.12+, FastAPI 0.139+, SQLAlchemy 2.x asyncio, asyncmy 0.2.9+, MySQL 8.4 LTS in Docker Compose, LangChain 1.3+/langchain-core 1.6+, langchain-openai 1.3+, Pydantic 2, pytest 9+, vanilla JavaScript

**Spec:** `docs/superpowers/specs/2026-09-23-ch02-function-calling-design.md`

## Global Constraints

- Work only in the isolated `code` repository workspace; do not modify `ch01-pure-chat/` or `../python/`.
- Build `ch02-function-calling/` as a complete independent chapter snapshot derived from chapter one.
- Keep FastAPI + SQLAlchemy async + Docker MySQL + LangChain `@tool`; stop and ask if the real upstream cannot return structured `tool_calls`.
- Execute zero or one tool per request. Reject multiple tool calls and finalize with the original model without bound tools.
- Keep order/product/logistics data mocked; do not add their tables or call real external APIs.
- Keep FAQ retrieval as literal SQL `LIKE`; the “邮费是多少” miss is required evidence, not a bug to hide.
- Treat the user-supplied four-table DDL as authoritative: preserve its unsigned IDs, Chinese ENUM values, field widths, timestamps, indexes, comments, and non-cascading foreign keys in SQL and ORM mappings.
- Do not add an Agent/AgentExecutor loop, RAG, vector search, Redis, auth, rate limiting, Alembic, or a separate Agent API.
- Use TDD for every testable backend behavior. Prompt/data changes use the labeled evaluation set. The chat page alone uses the approved Vibe Coding exception.
- Append `dev-notes/ch02.md` immediately after workspace baseline, every task, real capability probe, evaluation, browser QA, review, and finish. Record observed commands/results and all rework.
- Never print, log, commit, or return `.env`, API keys, database passwords, full database URLs, or raw upstream error bodies.

## File Map

**Copied unchanged at the initial snapshot:** chapter-one `app/`, `tests/`, `evals/`, `scripts/`, `.env.example`, `pyproject.toml`, and `README.md`.

**New backend units:**

- `app/db/base.py`: declarative base, async engine, and session factory constructors.
- `app/db/models.py`: exact four-table ORM mapping.
- `app/db/repository.py`: all conversation/message/FAQ/ticket transactions.
- `app/tools/business.py`: schemas and five LangChain tools.
- `app/tools/registry.py`: unique registry plus per-tool execution policy.
- `app/tools/executor.py`: visible-schema validation, trusted injection, timeout/retry, normalized ToolMessage output.
- `app/services/chat.py`: selector/tool/finalizer orchestration and typed stream events.

**Modified integration units:**

- `app/core/config.py`, `app/core/messages.py`, `app/core/prompts.py`, `app/main.py`.
- `app/api/chat.py`, `app/api/dependencies.py`, `app/schemas/chat.py`.
- `app/static/chat.js`, `app/static/chat.css`, `app/static/chat.html`.
- `pyproject.toml`, `.env.example`, `README.md`, and repository-root `README.md`.

## Stable Interfaces

The tasks below must preserve these names and signatures:

Implement these exact public signatures:

- `Base(AsyncAttrs, DeclarativeBase)`
- `create_database_engine(settings: Settings) -> AsyncEngine`
- `create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]`
- `Repository(session_factory: async_sessionmaker[AsyncSession])`
- `Repository.create_conversation(user_id: str) -> Conversation`
- `Repository.get_conversation(conversation_id: int, user_id: str) -> Conversation | None`
- `Repository.append_message(conversation_id: int, role: str, content: str | None, tool_calls: list[dict] | None = None, tool_call_id: str | None = None) -> Message`
- `Repository.list_replay_messages(conversation_id: int) -> list[Message]`
- `Repository.find_faq(keyword: str) -> Faq | None`
- `Repository.create_ticket(conversation_id: int, description: str, ticket_type: str) -> Ticket`
- `ToolSpec(tool: BaseTool, read_only: bool, timeout_seconds: float, max_attempts: int, inject_conversation_id: bool = False)`
- `ToolRegistry(specs: Sequence[ToolSpec])`, `model_tools -> list[BaseTool]`, and `get(name: str) -> ToolSpec | None`
- `ToolExecution(name: str, ok: bool, attempts: int, message: ToolMessage, payload: dict[str, Any])`
- `ToolExecutor.execute(tool_call: dict[str, Any], conversation_id: int) -> ToolExecution`
- `ToolEvent(name: str, status: Literal["running"] = "running")`
- `TokenEvent(content: str)`
- `DoneEvent(conversation_id: int, tools: tuple[str, ...])`
- `ChatEvent = ToolEvent | TokenEvent | DoneEvent`
- `ChatOrchestrator.stream_turn(user_id: str, message: str, conversation_id: int | None) -> AsyncIterator[ChatEvent]`

## Review Focus

- A supplied conversation ID owned by another user must produce the same safe “会话不存在” behavior as an unknown ID; Task 3 and Task 7 test it.
- A provider returning two tool calls despite `parallel_tool_calls=False` must execute neither and emit no `done`; Task 6 and Task 7 test it.
- `create_ticket` must hide `conversation_id` from the model schema, inject the real ID after validation, and never retry; Task 4 and Task 5 test all three conditions.
- A failed/timeout query tool must become one safe ToolMessage so the finalizer can answer, while model/DB infrastructure failure becomes a sanitized SSE error; Task 5–7 test this boundary.
- Streaming cancellation or finalizer failure must not persist a fabricated complete assistant answer; Task 6 tests that only completed non-empty text is saved.

---

### Task 1: Create the chapter snapshot and prove upstream tool calling

**Files:**
- Copy: `ch01-pure-chat/app/` → `ch02-function-calling/app/`
- Copy: `ch01-pure-chat/tests/` → `ch02-function-calling/tests/`
- Copy: `ch01-pure-chat/evals/` → `ch02-function-calling/evals/`
- Copy: `ch01-pure-chat/scripts/` → `ch02-function-calling/scripts/`
- Copy: `ch01-pure-chat/.env.example`, `pyproject.toml`, `README.md`
- Create: `ch02-function-calling/scripts/probe_tool_call.py`
- Modify: `ch02-function-calling/dev-notes/ch02.md`

**Interfaces:**
- Consumes: the approved spec and the existing chapter-one snapshot.
- Produces: a green chapter-two baseline plus real evidence that the configured upstream returns one structured tool call.

- [ ] **Step 1: Enter the approved isolated worktree and confirm boundaries**

Use `superpowers:using-git-worktrees` before this task. From the worktree’s `code` root run:

```powershell
git status --short --branch
git diff -- ch01-pure-chat
git -C ..\python status --short
```

Expected: only the already-approved chapter-two design commit is present; both protected paths have no changes.

- [ ] **Step 2: Copy only the chapter-one runtime snapshot**

```powershell
$target = "ch02-function-calling"
Copy-Item "ch01-pure-chat\app" "$target\app" -Recurse
Copy-Item "ch01-pure-chat\tests" "$target\tests" -Recurse
Copy-Item "ch01-pure-chat\evals" "$target\evals" -Recurse
Copy-Item "ch01-pure-chat\scripts" "$target\scripts" -Recurse
Copy-Item "ch01-pure-chat\.env.example" "$target\.env.example"
Copy-Item "ch01-pure-chat\pyproject.toml" "$target\pyproject.toml"
Copy-Item "ch01-pure-chat\README.md" "$target\README.md"
```

Do not copy `.env`, `.venv`, caches, or generated evaluation results.

- [ ] **Step 3: Create and install the chapter environment**

```powershell
py -3.12 -m venv ch02-function-calling\.venv
.\ch02-function-calling\.venv\Scripts\python.exe -m pip install -e "ch02-function-calling[dev]"
```

- [ ] **Step 4: Run the inherited baseline**

```powershell
Set-Location ch02-function-calling
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m compileall -q app scripts
Set-Location ..
```

Expected: the copied chapter-one suite is green before chapter-two behavior changes. Record the observed count rather than assuming a count.

- [ ] **Step 5: Add the real capability probe**

Create `scripts/probe_tool_call.py`:

```python
import asyncio
import json

from langchain.tools import tool

from app.core.config import get_settings
from app.core.model import create_chat_model


@tool
def probe_order(order_id: str) -> str:
    """Look up one order by its exact order ID."""
    return order_id


async def main() -> None:
    model = create_chat_model(get_settings())
    reply = await model.bind_tools(
        [probe_order], tool_choice="auto", parallel_tool_calls=False
    ).ainvoke("必须调用 probe_order 查询订单 1001，不要直接回答。")
    calls = reply.tool_calls
    if len(calls) != 1 or calls[0]["name"] != "probe_order":
        raise SystemExit("upstream did not return exactly one probe_order tool call")
    print(json.dumps({"name": calls[0]["name"], "args": calls[0]["args"]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 6: Run the real probe before any feature implementation**

Place a local ignored `.env` in the chapter directory without printing it. Reusing the existing chapter-one `.env` by local `Copy-Item` is allowed; never add it to Git.

```powershell
Set-Location ch02-function-calling
.\.venv\Scripts\python.exe scripts\probe_tool_call.py
Set-Location ..
```

Expected: safe JSON showing `probe_order` and `order_id=1001`. If this fails, stop, append the sanitized failure to `dev-notes/ch02.md`, and ask the user; do not continue with a fallback router or different model.

- [ ] **Step 7: Record and commit the baseline/probe stage**

Append the exact baseline commands, observed counts, model name (not endpoint/key), and sanitized probe result to `dev-notes/ch02.md`, then run:

```powershell
git add ch02-function-calling
git commit -m "chore: scaffold chapter two from chapter one"
```

---

### Task 2: Add MySQL configuration, Docker initialization, and ORM mappings

**Files:**
- Modify: `ch02-function-calling/pyproject.toml`
- Modify: `ch02-function-calling/.env.example`
- Modify: `ch02-function-calling/app/core/config.py`
- Create: `ch02-function-calling/app/db/__init__.py`
- Create: `ch02-function-calling/app/db/base.py`
- Create: `ch02-function-calling/app/db/models.py`
- Create: `ch02-function-calling/docker-compose.yml`
- Create: `ch02-function-calling/docker/mysql/init/001-schema.sql`
- Create: `ch02-function-calling/docker/mysql/init/002-seed.sql`
- Create: `ch02-function-calling/docker/mysql/init/003-test-database.sh`
- Create: `ch02-function-calling/.gitattributes`
- Modify: `ch02-function-calling/tests/core/test_config.py`
- Modify: `ch02-function-calling/tests/core/test_model.py`
- Modify: `ch02-function-calling/tests/api/test_chat.py`
- Modify: `ch02-function-calling/tests/api/test_extraction.py`
- Modify: `ch02-function-calling/tests/test_main.py`
- Create: `ch02-function-calling/tests/db/__init__.py`
- Create: `ch02-function-calling/tests/db/test_models.py`
- Modify: `ch02-function-calling/dev-notes/ch02.md`

**Interfaces:**
- Produces: `Settings.database_url`, `Settings.test_database_url`, tool execution settings, `Base`, engine/session constructors, and ORM classes `Faq`, `Conversation`, `Message`, `Ticket`.

- [ ] **Step 1: Add dependency metadata and install it**

Add these runtime dependencies to `pyproject.toml` without changing existing version floors:

```toml
"asyncmy>=0.2.9",
"sqlalchemy[asyncio]>=2.0.0",
```

Then run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

- [ ] **Step 2: Write failing settings and metadata tests**

Add tests that construct `Settings(_env_file=None)` after setting all required environment fields and assert:

```python
assert settings.database_url.get_secret_value().startswith("mysql+asyncmy://")
assert settings.test_database_url.get_secret_value().endswith("/mewhelp_test")
assert settings.tool_timeout_seconds == 3.0
assert settings.tool_max_attempts == 2
```

Add parameterized rejection tests for timeout values `0` and `-1`, and attempt values `0` and `4`. Add a secret-leak regression asserting an invalid setting error does not contain the supplied database password.

Update every copied test helper that directly constructs `Settings` so it supplies safe example
`database_url` and `test_database_url` values. This is a mechanical compatibility update; do not weaken
the new required-field validation.

Create `tests/db/test_models.py`:

```python
from app.db.base import Base
from app.db.models import Conversation, Faq, Message, Ticket


def test_metadata_contains_exact_chapter_two_tables() -> None:
    assert set(Base.metadata.tables) == {"faq", "conversations", "messages", "tickets"}


def test_message_trace_columns_are_present() -> None:
    table = Message.__table__
    assert {"conversation_id", "role", "content", "tool_calls", "tool_call_id", "created_at"} <= set(table.c)
    assert table.c.tool_calls.nullable is True
    assert table.c.tool_call_id.nullable is True


def test_timestamp_and_width_columns_match_the_authoritative_ddl() -> None:
    assert {"created_at", "updated_at"} <= set(Conversation.__table__.c)
    assert {"created_at", "updated_at"} <= set(Faq.__table__.c)
    assert Conversation.__table__.c.user_id.type.length == 64
    assert Message.__table__.c.tool_call_id.type.length == 64


def test_ticket_number_is_the_ticket_primary_key() -> None:
    assert [column.name for column in Ticket.__table__.primary_key.columns] == ["ticket_no"]
    assert Ticket.__table__.c.ticket_no.type.length == 32
```

- [ ] **Step 3: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_config.py tests\db\test_models.py -v -p no:cacheprovider
```

Expected: failures for missing settings and missing `app.db` modules.

- [ ] **Step 4: Implement settings and SQLAlchemy primitives**

Add to `Settings`:

```python
database_url: SecretStr = Field(min_length=1)
test_database_url: SecretStr = Field(min_length=1)
tool_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
tool_max_attempts: int = Field(default=2, ge=1, le=3)
```

Create `app/db/base.py` using the documented current APIs:

```python
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncEngine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings


class Base(AsyncAttrs, DeclarativeBase):
    pass


def create_database_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(), pool_pre_ping=True
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

Implement the four mapped classes with the exact names/types/nullability/FKs from the user-supplied DDL now recorded in the spec. Use MySQL unsigned `BIGINT`, native MySQL `ENUM`, `JSON` for `Message.tool_calls`, `DateTime(timezone=False)` with database defaults, and no ORM `ondelete` action for either foreign key.

- [ ] **Step 5: Add Docker and SQL initialization**

Create `docker-compose.yml`:

```yaml
services:
  mysql:
    image: mysql:8.4
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
    environment:
      MYSQL_DATABASE: ${MYSQL_DATABASE:-mewhelp}
      MYSQL_USER: ${MYSQL_USER:-mewhelp}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:-mewhelp}
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-mewhelp-root}
    ports:
      - "${MYSQL_PORT:-3306}:3306"
    volumes:
      - mysql_data:/var/lib/mysql
      - ./docker/mysql/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "mysqladmin ping -h localhost -uroot -p$$MYSQL_ROOT_PASSWORD --silent"]
      interval: 2s
      timeout: 3s
      retries: 30

volumes:
  mysql_data:
```

Create `001-schema.sql`:

```sql
SET NAMES utf8mb4;

CREATE TABLE conversations (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '会话主键',
  user_id VARCHAR(64) NOT NULL COMMENT '用户标识',
  status ENUM('进行中','已转人工','已结束') NOT NULL DEFAULT '进行中' COMMENT '处理状态',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '开启时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客服会话';

CREATE TABLE messages (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '消息主键',
  conversation_id BIGINT UNSIGNED NOT NULL COMMENT '所属会话',
  role ENUM('user','assistant','tool') NOT NULL COMMENT '角色:用户/助手/工具结果',
  content TEXT NULL COMMENT '消息正文,assistant 纯工具调用时可为空',
  tool_calls JSON NULL COMMENT 'assistant 消息带的工具调用申请单',
  tool_call_id VARCHAR(64) NULL COMMENT 'tool 消息对应的申请单 id,回灌时对号入座',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '产生时间',
  PRIMARY KEY (id),
  KEY idx_conversation_id (conversation_id),
  CONSTRAINT fk_messages_conversation FOREIGN KEY (conversation_id) REFERENCES conversations (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话消息流水';

CREATE TABLE faq (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'FAQ 主键',
  question VARCHAR(512) NOT NULL COMMENT '问题',
  answer TEXT NOT NULL COMMENT '答案',
  category VARCHAR(64) NOT NULL COMMENT '分类',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='常见问答';

CREATE TABLE tickets (
  ticket_no VARCHAR(32) NOT NULL COMMENT '工单号,如 T20260701008',
  conversation_id BIGINT UNSIGNED NOT NULL COMMENT '关联会话,可倒查当时聊了什么',
  description TEXT NOT NULL COMMENT '问题描述',
  ticket_type ENUM('售后','投诉','咨询') NOT NULL COMMENT '工单类型',
  status ENUM('待处理','已处理') NOT NULL DEFAULT '待处理' COMMENT '处理状态',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (ticket_no),
  KEY idx_conversation_id (conversation_id),
  CONSTRAINT fk_tickets_conversation FOREIGN KEY (conversation_id) REFERENCES conversations (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='人工工单';
```

Create `002-seed.sql` with refund, exchange, membership, invoice, and these acceptance rows:

```sql
INSERT INTO faq (question, answer, category) VALUES
('退货政策是什么', '商品满足条件时支持七天无理由退货，具体以商品页面和平台规则为准。', '售后'),
('运费怎么算', '达到包邮门槛免运费，否则按结算页面展示的金额收取。', '配送');
```

Create `003-test-database.sh`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

export MYSQL_PWD="${MYSQL_ROOT_PASSWORD}"
mysql --protocol=socket -uroot <<SQL
CREATE DATABASE IF NOT EXISTS mewhelp_test
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON mewhelp_test.* TO '${MYSQL_USER}'@'%';
FLUSH PRIVILEGES;
SQL
mysql --protocol=socket -uroot mewhelp_test \
  < /docker-entrypoint-initdb.d/001-schema.sql
mysql --protocol=socket -uroot mewhelp_test \
  < /docker-entrypoint-initdb.d/002-seed.sql
unset MYSQL_PWD
```

Create `.gitattributes` so Windows checkout does not break container shell scripts:

```gitattributes
*.sh text eol=lf
```

Extend `.env.example` with the exact variables from the design spec, including `DATABASE_URL` and `TEST_DATABASE_URL` using `?charset=utf8mb4`.

For the current PowerShell implementation session, set matching local demo environment values without
committing them; they remain available to subsequent test and Uvicorn commands in that terminal:

```powershell
$env:MYSQL_DATABASE = "mewhelp"
$env:MYSQL_USER = "mewhelp"
$env:MYSQL_PASSWORD = "mewhelp"
$env:MYSQL_ROOT_PASSWORD = "mewhelp-root"
$env:DATABASE_URL = "mysql+asyncmy://mewhelp:mewhelp@127.0.0.1:3306/mewhelp?charset=utf8mb4"
$env:TEST_DATABASE_URL = "mysql+asyncmy://mewhelp:mewhelp@127.0.0.1:3306/mewhelp_test?charset=utf8mb4"
```

- [ ] **Step 6: Verify GREEN and the actual MySQL schema**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_config.py tests\db\test_models.py -v -p no:cacheprovider
docker compose up -d mysql
docker compose ps
docker compose exec -T mysql sh -lc 'MYSQL_PWD="$MYSQL_PASSWORD" mysql -u"$MYSQL_USER" "$MYSQL_DATABASE" -e "SHOW TABLES; SELECT question FROM faq ORDER BY id;"'
```

Expected: focused tests pass, MySQL is healthy, exactly four application tables are listed, and Chinese FAQ text is readable. If port 3306 is occupied, report the conflict and use `MYSQL_PORT` rather than changing the stack.

- [ ] **Step 7: Run the full suite, record, and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
git diff --check
git add ch02-function-calling
git commit -m "feat: add chapter two MySQL foundation"
```

Append RED/GREEN output and Docker evidence to `dev-notes/ch02.md` before the commit.

---

### Task 3: Implement repositories and real MySQL integration tests

**Files:**
- Create: `ch02-function-calling/app/db/repository.py`
- Create: `ch02-function-calling/tests/conftest.py`
- Create: `ch02-function-calling/tests/db/test_repository.py`
- Modify: `ch02-function-calling/dev-notes/ch02.md`

**Interfaces:**
- Produces: the exact `Repository` interface from “Stable Interfaces”.

- [ ] **Step 1: Add a MySQL test fixture**

`tests/conftest.py` must read `TEST_DATABASE_URL` through `Settings`, create an async engine/session factory, yield them, and dispose the engine. An autouse cleanup fixture deletes rows in FK-safe order (`tickets`, `messages`, `conversations`) and restores the six known FAQ seed rows before each repository test.

- [ ] **Step 2: Write failing repository tests**

Cover these named behaviors with real MySQL: conversation lookup requires the matching user; messages
preserve user/tool-call/tool-result/final order; replay excludes tool trace but keeps final answers; FAQ
LIKE hits the return policy; FAQ LIKE does not rewrite postage to shipping; and ticket creation updates
the conversation in the same transaction.

The FAQ assertions must be literal:

```python
assert (await repository.find_faq("退货政策")).question == "退货政策是什么"
assert await repository.find_faq("邮费是多少") is None
```

- [ ] **Step 3: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\db\test_repository.py -v -p no:cacheprovider
```

Expected: collection fails because `app.db.repository` does not exist.

- [ ] **Step 4: Implement short-session repository methods**

Every method opens its own `async with self._session_factory() as session`. Writes use `async with session.begin()`. Reads use SQLAlchemy `select()`. `find_faq` uses:

```python
statement = select(Faq).where(Faq.question.like(f"%{keyword}%")).order_by(Faq.id).limit(1)
```

`list_replay_messages` selects `role == "user"` or assistant rows with non-empty content and `tool_calls IS NULL`, ordered by `(created_at, id)`. `create_ticket` locks or loads the conversation, inserts a server-generated `T`-prefixed identifier of at most 32 characters, and sets status to `已转人工` in the same transaction.

- [ ] **Step 5: Verify focused and full GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\db\test_repository.py -v -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

- [ ] **Step 6: Record and commit**

Append observed RED/GREEN evidence to `dev-notes/ch02.md`, then:

```powershell
git add ch02-function-calling
git commit -m "feat: add conversation and ticket repositories"
```

---

### Task 4: Define the five LangChain business tools

**Files:**
- Create: `ch02-function-calling/app/tools/__init__.py`
- Create: `ch02-function-calling/app/tools/business.py`
- Create: `ch02-function-calling/tests/tools/__init__.py`
- Create: `ch02-function-calling/tests/tools/test_business.py`
- Modify: `ch02-function-calling/dev-notes/ch02.md`

**Interfaces:**
- Consumes: `Repository`.
- Produces: exported `query_order`, `query_product`, `query_logistics`, plus `build_business_tools(repository) -> list[BaseTool]` containing all five tools in stable order.

- [ ] **Step 1: Write failing tool tests**

Test exact names, JSON schemas, deterministic mock results, FAQ hit/miss, and ticket persistence. Include this injection assertion:

```python
tools = {tool.name: tool for tool in build_business_tools(repository)}
schema = tools["create_ticket"].tool_call_schema.model_json_schema()
assert set(schema["properties"]) == {"description", "ticket_type"}
assert "conversation_id" not in schema["properties"]
```

Invoke the ticket tool with the trusted field present and assert the ticket row and conversation status exist in MySQL.

- [ ] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_business.py -v -p no:cacheprovider
```

Expected: missing `app.tools.business`.

- [ ] **Step 3: Implement schemas and deterministic mock helpers**

Define Pydantic schemas with stripped non-empty strings and useful field descriptions:

```python
class OrderInput(BaseModel):
    order_id: str = Field(min_length=1, max_length=64, description="用户提供的原始订单号")

class ProductInput(BaseModel):
    product_name: str = Field(min_length=1, max_length=200, description="用户询问的商品名称")

class FaqInput(BaseModel):
    keyword: str = Field(min_length=1, max_length=200, description="保留用户原词的 FAQ 关键词，不改写同义词")
```

Use SHA-256 bytes to seed a new `random.Random` per call; never use Python’s process-randomized `hash()`. Return JSON-serializable dictionaries with the requested identifier plus realistic status/price/stock/timeline fields.

- [ ] **Step 4: Implement all five `@tool` definitions**

Use explicit `args_schema` for the three mock queries and the repository-backed FAQ tool. Define the ticket tool with an inferred schema:

```python
@tool
async def create_ticket(
    description: str,
    ticket_type: Literal["售后", "投诉", "咨询"],
    conversation_id: Annotated[int, InjectedToolArg],
) -> dict[str, Any]:
    """Create a human-service ticket only when the user explicitly requests follow-up."""
    ticket = await repository.create_ticket(conversation_id, description, ticket_type)
    return {"ticket_no": ticket.ticket_no, "status": ticket.status}
```

The nested ticket/FAQ tools may close over the injected `Repository`; the three stateless mock tools remain module-level exports.

- [ ] **Step 5: Verify GREEN, full suite, record, and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_business.py -v -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
git diff --check
git add ch02-function-calling
git commit -m "feat: add customer service business tools"
```

Append observed evidence to `dev-notes/ch02.md` before committing.

---

### Task 5: Build the registry and resilient one-call executor

**Files:**
- Create: `ch02-function-calling/app/tools/registry.py`
- Create: `ch02-function-calling/app/tools/executor.py`
- Create: `ch02-function-calling/tests/tools/test_registry.py`
- Create: `ch02-function-calling/tests/tools/test_executor.py`
- Modify: `ch02-function-calling/dev-notes/ch02.md`

**Interfaces:**
- Produces: `ToolSpec`, `ToolRegistry`, `ToolExecution`, `ToolExecutor` from “Stable Interfaces”.

- [ ] **Step 1: Write registry RED tests**

Cover stable registration order, lookup, duplicate-name rejection, empty-name rejection, and `model_tools` returning the underlying tools without policy metadata.

- [ ] **Step 2: Write executor RED tests**

Use tiny decorated test tools to cover these named behaviors: unknown tool returns a safe failed
ToolMessage; visible-schema validation prevents execution; conversation ID is injected after visible
validation; a read tool retries one timeout then succeeds; a read tool stops at configured attempts; a
write tool never retries; success content is UTF-8 JSON with the matching call ID; and error content never
contains raw exception text.

Assert `ToolMessage.status` is `success` or `error`, its `tool_call_id` matches the model call, and failure content contains only stable codes/messages.

- [ ] **Step 3: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_registry.py tests\tools\test_executor.py -v -p no:cacheprovider
```

- [ ] **Step 4: Implement registry invariants**

Store specs in insertion-ordered `dict[str, ToolSpec]`. Reject `not spec.tool.name.strip()` and any duplicate with `ValueError`. Validate `max_attempts >= 1` and positive timeout in `ToolSpec.__post_init__`.

- [ ] **Step 5: Implement execution ordering and safe results**

Executor algorithm:

```python
spec = registry.get(tool_call["name"])
visible = spec.tool.tool_call_schema.model_validate(tool_call.get("args", {})).model_dump()
if spec.inject_conversation_id:
    visible["conversation_id"] = conversation_id
result = await asyncio.wait_for(spec.tool.ainvoke(visible), spec.timeout_seconds)
```

Retry only when `spec.read_only` and the exception is `TimeoutError`, `ConnectionError`, or SQLAlchemy `OperationalError`. Serialize the named `payload` value with `json.dumps(payload, ensure_ascii=False, separators=(",", ":"))`. Never place `str(exc)` in the returned payload.

- [ ] **Step 6: Verify focused/full GREEN, record, and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_registry.py tests\tools\test_executor.py -v -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
git add ch02-function-calling
git commit -m "feat: add validated tool execution infrastructure"
```

Append the retry/timeout RED/GREEN evidence before committing.

---

### Task 6: Implement prompts and the single-round streaming orchestrator

**Files:**
- Modify: `ch02-function-calling/app/core/messages.py`
- Modify: `ch02-function-calling/app/core/prompts.py`
- Replace: `ch02-function-calling/app/services/chat.py`
- Create: `ch02-function-calling/tests/services/test_tool_chat.py`
- Modify: `ch02-function-calling/dev-notes/ch02.md`

**Interfaces:**
- Consumes: `Repository`, `ToolRegistry`, `ToolExecutor`, raw chat model, history token budget.
- Produces: typed stream events and `ChatOrchestrator.stream_turn()`.

- [ ] **Step 1: Write orchestrator RED tests with fakes**

Create fakes that separately record selector `bind_tools/ainvoke` and unbound `astream`. Cover:

- no-tool selection still invokes unbound `astream`, emits `token → done`, and stores only user/final assistant;
- one tool emits `tool` before tokens, passes `AIMessage + ToolMessage` to finalizer, and stores user/tool request/tool result/final assistant in order;
- selector receives `parallel_tool_calls=False` and stable tool order;
- two returned tool calls raise `MultipleToolCalls` before executor invocation;
- unknown/mismatched conversation raises `ConversationNotFound`;
- empty finalizer output raises `EmptyModelResponse` and stores no final assistant;
- finalizer exception after partial chunks stores no final assistant and emits no `done`;
- finalizer model object is the original unbound model, proving no second tool call can occur;
- cross-turn history excludes prior tool traces but includes prior final answers.

- [ ] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\services\test_tool_chat.py -v -p no:cacheprovider
```

- [ ] **Step 3: Add the tool-aware prompts**

Replace the old “no tools” customer-service sentence with two prompt builders:

```python
TOOL_SELECTOR_SYSTEM_PROMPT = """你是电商客服的工具选择器。根据用户原话最多选择一个必要工具。
无需工具时不要编造工具调用；FAQ 关键词必须尽量保留用户原词，不得把“邮费”改写成“运费”。
不要在本阶段输出给用户的最终答复。"""

FINAL_ANSWER_SYSTEM_PROMPT = """你是电商平台智能客服。使用用户当前语言简洁、礼貌回答。
如果提供了工具结果，只能依据该结果回答；工具失败或未找到时如实说明，不得编造数据。
不得再请求或声称调用任何工具。"""
```

Build messages with `ChatPromptTemplate` and `MessagesPlaceholder`. Preserve the chapter-one extraction prompt unchanged.

- [ ] **Step 4: Adapt history conversion without exposing ORM internals**

Keep `trim_history()` and add a converter accepting repository messages with `role/content`; map only user to `HumanMessage` and final assistant to `AIMessage`. The latest user message still triggers `MessageBudgetExceeded` if it alone exceeds the budget.

- [ ] **Step 5: Implement `ChatOrchestrator` exactly once**

Use one private `_resolve_conversation()` and one selector call. Normalize persisted tool calls to dictionaries containing only `id`, `name`, and `args`. For the tool path, finalizer input ends with the selector `AIMessage` followed by the executor’s matching `ToolMessage`. Accumulate chunk `.text`; yield only non-empty chunks. Persist the final assistant only after normal stream completion and non-empty accumulated text.

- [ ] **Step 6: Verify focused/full GREEN, record, and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\services\test_tool_chat.py -v -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
git diff --check
git add ch02-function-calling
git commit -m "feat: orchestrate one-shot tool calling"
```

Prompt behavior is not declared complete here; Task 8 runs the labeled real-model evaluation.

---

### Task 7: Wire runtime construction and the SSE chat API

**Files:**
- Modify: `ch02-function-calling/app/schemas/chat.py`
- Modify: `ch02-function-calling/app/api/dependencies.py`
- Replace: `ch02-function-calling/app/api/chat.py`
- Modify: `ch02-function-calling/app/main.py`
- Modify: `ch02-function-calling/tests/api/test_chat.py`
- Modify: `ch02-function-calling/tests/test_main.py`
- Modify: `ch02-function-calling/dev-notes/ch02.md`

**Interfaces:**
- Public request: `ChatRequest(user_id: str, message: str, conversation_id: int | None = None)`.
- Public SSE events: `tool`, `token`, `done`, or one terminal `error`.

- [ ] **Step 1: Write failing schema/API/lifespan tests**

Tests must assert:

```text
tool(query_logistics,running) → token(您的) → token(订单) → done(conversation_id,tools)
```

and separately cover no-tool output, 422 for blank/oversized fields, unknown/mismatched conversation, multiple tool calls, model failure, database failure, and no `done` after `error`. Lifespan tests assert engine disposal is awaited.

- [ ] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\api\test_chat.py tests\test_main.py -v -p no:cacheprovider
```

- [ ] **Step 3: Implement the public schema and dependency**

Use stripped fields with these limits:

```python
class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = Field(default=None, gt=0)
```

`get_chat_orchestrator(request: Request)` returns `request.app.state.chat_orchestrator`.

- [ ] **Step 4: Build runtime once in FastAPI lifespan**

During startup: validate settings → create engine/session factory → create `Repository` → build five tools → create registry policies (four reads, one write) → create executor → create model → create orchestrator → store it on `app.state`. In `finally`, call `await engine.dispose()`.

Keep the chapter-one extraction router and static page routes working.

- [ ] **Step 5: Map domain events to SSE**

The route yields:

```python
yield encode_sse("tool", {"name": event.name, "status": event.status})
yield encode_sse("token", {"content": event.content})
yield encode_sse("done", {"conversation_id": event.conversation_id, "tools": list(event.tools)})
```

Map `ConversationNotFound`, `MultipleToolCalls`, SQLAlchemy errors, and remaining upstream errors to distinct safe messages. After `error`, return immediately.

- [ ] **Step 6: Verify focused/full GREEN, record, and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\api\test_chat.py tests\test_main.py -v -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
git add ch02-function-calling
git commit -m "feat: connect tools to the SSE chat endpoint"
```

---

### Task 8: Add the labeled tool-selection evaluation and run it

**Files:**
- Create: `ch02-function-calling/evals/ch02_cases.json`
- Create: `ch02-function-calling/scripts/eval_ch02.py`
- Modify: `ch02-function-calling/app/core/prompts.py` only when evaluation evidence justifies it
- Modify: `ch02-function-calling/dev-notes/ch02.md`

**Interfaces:**
- Produces: ignored `evals/ch02_results.json` and a console pass/fail summary.

- [ ] **Step 1: Create the seven labeled cases**

Each JSON item contains `id`, `message`, `expected_tool`, optional `expected_tool_ok`, and `answer_terms`. Include exactly these intent classes: order, product, logistics 1001, return policy, postage miss, explicit human ticket, and greeting/no tool.

The postage case must expect:

```json
{
  "id": "faq-postage-expected-miss",
  "message": "邮费是多少",
  "expected_tool": "query_faq",
  "expected_tool_ok": true,
  "expected_faq_found": false
}
```

- [ ] **Step 2: Implement the evaluator**

Build the same runtime as the application, assign a unique evaluation user, call `stream_turn()` once per case, collect tool names/tokens/done IDs, then read the stored tool message JSON to inspect `found`. Print one safe line per case and write a machine-readable summary without credentials or raw upstream errors. Always dispose the engine.

- [ ] **Step 3: Validate script syntax and run the full real evaluation**

```powershell
.\.venv\Scripts\python.exe -m compileall -q app scripts
.\.venv\Scripts\python.exe scripts\eval_ch02.py
```

If a Prompt/tool-description defect is evidenced, change only the smallest relevant wording and rerun all seven cases. Do not change FAQ retrieval to make the postage case pass as a hit.

- [ ] **Step 4: Run regression tests, record, and commit**

Append every evaluation run and correction to `dev-notes/ch02.md`, including the expected postage miss. Then:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
git add ch02-function-calling/app ch02-function-calling/evals/ch02_cases.json ch02-function-calling/scripts/eval_ch02.py ch02-function-calling/dev-notes/ch02.md
git commit -m "test: add chapter two tool selection evaluation"
```

Do not add `evals/ch02_results.json`.

---

### Task 9: Vibe-code the chat badge, document demos, and perform end-to-end QA

**Files:**
- Modify: `ch02-function-calling/app/static/chat.js`
- Modify: `ch02-function-calling/app/static/chat.css`
- Modify: `ch02-function-calling/app/static/chat.html`
- Modify: `ch02-function-calling/tests/test_main.py` only for static-route smoke coverage
- Modify: `ch02-function-calling/README.md`
- Modify: `README.md`
- Modify: `ch02-function-calling/dev-notes/ch02.md`

**Interfaces:**
- Browser local storage keys: `mewhelp_user_id` and `mewhelp_conversation_id`.
- One assistant bubble can own one `.tool-badge` updated by `tool` SSE events.

- [ ] **Step 1: Apply the approved Vibe Coding exception**

Directly change the page without frontend brainstorm, TDD, or separate code review. Remove client-submitted history from the request. Generate a stable user ID with `crypto.randomUUID()` when available and a timestamp/random fallback otherwise. Persist `conversation_id` only from a valid `done` frame.

On `tool` event, create/update a badge whose visible text is `调用了 <tool name>` and keep the typing state until the first token. On reset, remove only `mewhelp_conversation_id` and visible non-welcome messages; retain the stable user ID.

- [ ] **Step 2: Add badge styling and acceptance prompts**

Add a compact neutral-green pill above assistant text, with wrapping for long names and accessible text. Update the three suggestion buttons to the exact acceptance prompts:

- `订单 1001 的物流到哪了`
- `退货政策是什么`
- `邮费是多少`

- [ ] **Step 3: Run static and backend verification**

```powershell
node --check app\static\chat.js
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m compileall -q app scripts
git diff --check
```

- [ ] **Step 4: Document exact demo commands**

README must include:

```powershell
docker compose up -d mysql
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

and three `curl.exe -N` examples for the acceptance prompts using the new request schema. Document `docker compose down` and clarify that `docker compose down -v` destroys local demo data and must only be run intentionally.

Update repository-root `README.md` with a Chapter 02 row linking to `ch02-function-calling/`.

- [ ] **Step 5: Run real browser acceptance**

Use the computer-use skill to open the local page and run all three prompts in fresh conversations. Record:

- logistics badge name and grounded answer;
- FAQ badge and returned return-policy content;
- postage FAQ badge plus honest “not found” behavior;
- confirmation that each final answer visibly streams rather than appearing as one block.

If the observed UI is wrong, fix only the Vibe Coding page and repeat browser QA. If the backend/model selection is wrong, return to the owning TDD/evaluation task rather than hiding it in UI code.

- [ ] **Step 6: Request whole-feature code review and address findings**

Use `superpowers:requesting-code-review` over the chapter-two implementation range. The review excludes applying the frontend workflow rules but still checks frontend security and integration correctness. Fix all Critical and Important findings with TDD for backend changes, rerun the full suite, and append the review/fix evidence to `dev-notes/ch02.md`.

- [ ] **Step 7: Run the final verification gate and commit delivery docs**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m compileall -q app scripts
node --check app\static\chat.js
docker compose ps
git diff --check
git status --short
git diff -- ch01-pure-chat
git -C ..\python status --short
git ls-files | Select-String -Pattern '(^|/)\.env$|ch02_results\.json$'
```

Rerun `scripts/eval_ch02.py` and the three browser cases on the exact final tree. Append the fresh counts/results and demo commands to `dev-notes/ch02.md`, then commit:

```powershell
git add README.md ch02-function-calling
git commit -m "feat: finish chapter two tool-enabled chat"
```

After the commit, invoke `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch` and present its integration menu without choosing for the user.
