# 第 2 章：客服聊天内的单轮 Function Calling 工具链设计

## 1. 目标与成功标准

本章以 `ch01-pure-chat/` 为只读来源，在同级新建完整、独立、可运行的
`ch02-function-calling/` 章节快照。第一章保持不变；第二章在原有 FastAPI、
LangChain、SSE 流式聊天和静态聊天页之上增加 MySQL 持久化、五个业务工具、
一次工具选择与执行、工具结果回灌，以及聊天气泡中的工具轨迹徽章。

核心用户路径是同一个聊天入口：浏览器提交一句话后，模型自行决定是否调用工具；
如需工具，后端先推送工具状态帧，再执行工具并把结果交回模型；无论是否调用工具，
最终回答都由未绑定工具的模型通过 SSE 增量输出。一次请求最多执行一个工具，随后
必须收敛，不进入 Agent Loop。

浏览器验收标准：

1. 输入“订单 1001 的物流到哪了”，模型选择 `query_logistics`，气泡显示工具徽章，
   最终回答引用工具返回的物流信息。
2. 输入“退货政策是什么”，模型选择 `query_faq`，SQL `LIKE` 命中 FAQ 并回答政策。
3. 输入“邮费是多少”，模型仍可选择 `query_faq`，但字面关键词无法命中仅包含
   “运费怎么算”的记录；该漏召回属于预期结果，写入过程记录，留给下一章的
   向量检索升级。

## 2. 固定边界

- Python 3.12 或更高版本。
- FastAPI 提供 HTTP 与 SSE 接口。
- SQLAlchemy 2.x 异步 ORM，驱动使用 `asyncmy`。
- MySQL 8.4 LTS 由 Docker Compose 启动；应用仍可在本机用 Uvicorn 启动。
- LangChain `@tool` 定义工具，`ChatOpenAI.bind_tools()` 承载 Function Calling。
- 沿用第一章的 OpenAI 兼容 `CHAT_BASE_URL`、`CHAT_API_KEY`、`CHAT_MODEL` 配置。
- 不替换上述技术选型；若真实上游不支持结构化 `tool_calls`，立即停止并请用户决策。
- 不实现多轮自动 Agent Loop、向量检索、RAG、Redis、鉴权、限流或真实电商/物流 API。
- 聊天页改造按用户指定的 Vibe Coding 例外执行，不套 brainstorm、TDD 或独立 code review；
  后端与基础设施仍完整遵循 Superpowers 流程。
- `../python/` 仅作为只读参考，不修改、不复制其后续章节实现。

## 3. 章节结构与分层

第二章先复制第一章的应用、测试、评估和文档基础，再在自身目录内演进：

```text
ch02-function-calling/
├─ app/
│  ├─ main.py
│  ├─ api/
│  │  ├─ chat.py                 # 请求校验、SSE 映射、错误脱敏
│  │  └─ dependencies.py         # 模型、session factory、编排器依赖
│  ├─ core/
│  │  ├─ config.py               # 模型、数据库和工具执行配置
│  │  ├─ model.py                # ChatOpenAI 工厂
│  │  ├─ messages.py             # 历史转换与 token 裁剪
│  │  └─ prompts.py              # 工具选择与最终回答 Prompt
│  ├─ db/
│  │  ├─ base.py                 # AsyncEngine 与 async_sessionmaker
│  │  ├─ models.py               # 四张表的 ORM 映射
│  │  └─ repositories.py         # 会话、消息、FAQ、工单持久化
│  ├─ schemas/
│  │  └─ chat.py                 # user_id/message/conversation_id 契约
│  ├─ services/
│  │  └─ chat.py                 # 单轮工具编排与 SSE 领域事件
│  ├─ tools/
│  │  ├─ business.py             # 五个 @tool 业务实现
│  │  ├─ registry.py             # 唯一名称注册与工具策略
│  │  └─ executor.py             # 校验、注入、超时、重试、错误结果
│  └─ static/                    # 第一章聊天页的 Vibe Coding 改造
├─ docker/mysql/init/
│  ├─ 001-schema.sql
│  └─ 002-seed.sql
├─ evals/ch02_cases.json
├─ scripts/eval_ch02.py
├─ tests/
├─ dev-notes/ch02.md
├─ docker-compose.yml
├─ .env.example
├─ pyproject.toml
└─ README.md
```

边界职责：

- `api/` 只处理 FastAPI 契约、状态码、SSE 编码与脱敏错误。
- `services/chat.py` 是唯一编排核心，不包含 SQL 细节或 DOM 逻辑。
- `tools/` 对模型暴露稳定 Schema，并把所有执行结果归一化。
- `db/repositories.py` 封装 SQLAlchemy 查询与事务；工具和编排器不直接拼 SQL。
- 流式期间不长期持有一个请求级数据库事务。每次持久化使用短生命周期 session。

## 4. 配置与 Docker MySQL

第二章在第一章配置之上增加：

```dotenv
DATABASE_URL=mysql+asyncmy://mewhelp:mewhelp@127.0.0.1:3306/mewhelp
MYSQL_DATABASE=mewhelp
MYSQL_USER=mewhelp
MYSQL_PASSWORD=mewhelp
MYSQL_ROOT_PASSWORD=replace-root-password
TOOL_TIMEOUT_SECONDS=3
TOOL_MAX_ATTEMPTS=2
```

真实 `.env` 继续被 Git 忽略；仓库只保存 `.env.example`。错误消息和日志不得输出
API key、数据库密码或完整连接串。

`docker-compose.yml` 只负责 MySQL，使用命名 volume 保存数据，并设置 `mysqladmin ping`
健康检查。初始化目录按文件名顺序挂载到 `/docker-entrypoint-initdb.d/`：先建表，后灌
FAQ 测试数据。DDL 与 seed 显式使用 `utf8mb4`，避免中文数据乱码。应用启动时不调用
`Base.metadata.create_all()`；SQL 初始化文件是本章演示环境的表结构权威来源，ORM 映射
必须与其一致。

## 5. 数据模型

### 5.1 `faq`

- `id`: `BIGINT UNSIGNED` 自增主键。
- `question`: `VARCHAR(512)`，不可空。
- `answer`: `TEXT`，不可空。
- `category`: `VARCHAR(64)`，不可空并建立索引。
- `created_at`: `DATETIME`，数据库生成。
- `updated_at`: `DATETIME`，数据库生成并在更新时自动刷新。

`query_faq` 只执行 `question LIKE :pattern`，其中 pattern 为 `%原始关键词%`。不做分词、
同义词改写、全文索引、向量检索或回退搜索。

### 5.2 `conversations`

- `id`: `BIGINT UNSIGNED` 自增主键。
- `user_id`: `VARCHAR(64)`，不可空并建立索引。
- `status`: `ENUM('进行中','已转人工','已结束')`，默认 `进行中`。
- `created_at`: `DATETIME`，数据库生成。
- `updated_at`: `DATETIME`，数据库生成并在更新时自动刷新。

续接会话时必须同时按 `id` 和 `user_id` 查找；不存在或不属于当前用户均按“会话不存在”
处理，避免跨用户读取历史。

### 5.3 `messages`

- `id`: `BIGINT UNSIGNED` 自增主键。
- `conversation_id`: 外键关联 `conversations.id`，不可空并建立索引。
- `role`: `ENUM('user','assistant','tool')`。
- `content`: `TEXT`，可空；工具申请型 assistant 消息可能没有文本内容。
- `tool_calls`: `JSON`，可空；保存模型返回的标准化工具申请数组。
- `tool_call_id`: `VARCHAR(64)`，可空；tool 消息用于关联申请。
- `created_at`: `DATETIME`，数据库生成；`conversation_id` 单列索引用于会话查询。

正常工具轮次的落库顺序为：user → 带 `tool_calls` 的 assistant → tool → 最终 assistant。
无工具轮次只保存 user → 最终 assistant。跨轮组装历史时只回放 user 与最终 assistant；
工具申请和工具结果完整保留用于审计，但不污染后续自然对话上下文。

### 5.4 `tickets`

- `ticket_no`: `VARCHAR(32)` 主键，由服务端生成，例如 `T20260701008`。
- `conversation_id`: 外键关联 `conversations.id`，不可空并建立索引。
- `description`: `TEXT`，不可空。
- `ticket_type`: `ENUM('售后','投诉','咨询')`。
- `status`: `ENUM('待处理','已处理')`，默认 `待处理`。
- `created_at`: `DATETIME`，数据库生成。

创建工单与把会话状态改为 `已转人工` 在同一数据库事务中完成。外键行为严格采用用户提供的
DDL，不额外增加 `ON DELETE CASCADE` 或 `ON DELETE RESTRICT`。

## 6. FAQ 测试数据

Seed 至少包含退货、换货、退款时效、会员、发票和运费条目。两条验收关键数据固定为：

```text
question: 退货政策是什么
answer: 商品满足条件时支持七天无理由退货，具体以商品页面和平台规则为准。
category: 售后

question: 运费怎么算
answer: 达到包邮门槛免运费，否则按结算页面展示的金额收取。
category: 配送
```

第一条使“退货政策是什么”能够字面命中；第二条故意不包含“邮费是多少”，确保验收三
暴露关键词检索的语义鸿沟。

## 7. 五个业务工具

所有工具使用 `from langchain.tools import tool` 的 `@tool` 定义，并由 Pydantic 输入 Schema
完成参数约束。普通工具显式传入 `args_schema`；`create_ticket` 让 `@tool` 从带有
`InjectedToolArg` 注解的函数签名推导完整输入 Schema，使模型可见的 `tool_call_schema`
自动排除注入字段。工具 docstring 直接作为模型可见用途描述。

### 7.1 查询类 mock 工具

- `query_order(order_id: str)`: 返回订单状态、金额、下单时间和商品摘要。
- `query_product(product_name: str)`: 返回演示价格、库存和规格。
- `query_logistics(order_id: str)`: 返回运单号、物流状态、当前位置和时间线。

三者不建业务表、不请求外部 API。实现使用业务参数的 SHA-256 摘要初始化独立
`random.Random`，在保留“随机演示数据”特征的同时让相同入参可复现，便于测试和演示。

### 7.2 FAQ 工具

`query_faq(keyword: str)` 通过注入的 session factory 调用 repository，对 `faq.question`
执行字面 `LIKE`。工具描述要求模型尽量保留用户原词，不主动把“邮费”改写为“运费”。
命中返回 FAQ 记录；未命中返回结构化的 `found: false`，不编造答案。

### 7.3 工单工具

`create_ticket(description: str, ticket_type: str, conversation_id: Annotated[int, InjectedToolArg])`
写入 `tickets`。`conversation_id` 来自可信编排上下文；LangChain 的 `tool_call_schema`
隐藏该字段，而完整输入 Schema 仍在实际执行时验证它。执行器在模型可见参数校验后注入
当前会话 ID，确保模型不能选择其他会话。

## 8. 注册与执行基础设施

`ToolRegistry` 在应用装配时接收五个工具，拒绝空名称和重名；它提供稳定顺序的模型绑定
列表与按名称查找接口。每个注册项还包含：

- `read_only`: 是否允许安全重试。
- `timeout_seconds`: 默认来自 `TOOL_TIMEOUT_SECONDS`。
- `max_attempts`: 查询工具默认来自 `TOOL_MAX_ATTEMPTS`；写工具固定为 1。
- `inject_conversation_id`: 是否在校验后注入当前会话 ID。

`ToolExecutor` 的顺序固定为：查找工具 → 校验模型参数 → 注入可信参数 → 限时执行 →
归一化结果。查询工具仅在 `TimeoutError`、`ConnectionError` 或 SQLAlchemy 连接类暂时性
错误时重试一次；未知工具、Schema 校验失败和确定性业务错误不重试；`create_ticket`
永不自动重试。

执行结果统一为可 JSON 序列化的对象：

```json
{"ok":true,"tool":"query_logistics","data":{"order_id":"1001"}}
```

或：

```json
{"ok":false,"tool":"query_logistics","error":{"code":"timeout","message":"工具暂时不可用"}}
```

错误结果同样转换为匹配原始 `tool_call_id` 的 `ToolMessage` 回灌模型。工具执行失败不直接
转成 SSE `error`；模型应根据失败结果给出安全、可行动的客服回答。

## 9. 单轮编排

`ChatOrchestrator.stream_turn()` 返回领域事件异步迭代器，流程如下：

1. 根据 `conversation_id` 创建或校验会话，并提交 user 消息。
2. 读取该会话可回放的 user/最终 assistant 历史，沿用第一章 token 预算裁剪，再添加工具版
   System Prompt。
3. 调用 `model.bind_tools(tools, tool_choice="auto", parallel_tool_calls=False).ainvoke(...)`。
   这次非流式调用只负责工具决策；Prompt 要求无需工具时不输出客服终稿。
4. 若返回超过一个工具申请，按上游协议违规处理，不选择性执行，也不留下不完整工具链。
5. 若没有工具申请，忽略选择阶段可能产生的文本，直接用未绑定工具的原模型对原上下文
   执行一次 `astream()`，增量输出最终答案并在成功结束后保存最终 assistant 消息。
6. 若有一个工具申请，先保存带 `tool_calls` 的 assistant 消息并发送工具状态事件，然后
   执行工具、保存 tool 消息；最后把原上下文、工具申请 AIMessage 和 ToolMessage 一起交给
   未绑定工具的原模型 `astream()`，增量输出并保存最终 assistant 消息。
7. 发送完成事件。收敛模型没有绑定任何工具，因此不存在第二轮工具调用入口。

两条分支都由第二次模型调用流式生成最终回答，满足最终答案始终增量输出的要求。选择阶段
与收敛阶段使用同一个模型配置，不引入新的模型或 Agent 框架。

若流式生成中断，已提交的 user、工具申请和工具结果仍保留；只有模型正常结束且累计文本
非空时才保存最终 assistant 消息，不把部分文本伪装为完整答案。

## 10. HTTP 与 SSE 契约

`POST /chat/stream` 请求改为：

```json
{
  "user_id": "browser-generated-id",
  "conversation_id": 12,
  "message": "订单 1001 的物流到哪了"
}
```

- `user_id` 去除空白后长度为 1–64，与 DDL 字段宽度一致。
- `message` 去除空白后不得为空，并设置合理的最大长度。
- `conversation_id` 可空；为空时创建新会话。

成功事件：

```text
event: tool
data: {"name":"query_logistics","status":"running"}

event: token
data: {"content":"您的"}

event: done
data: {"conversation_id":12,"tools":["query_logistics"]}

```

无需工具时不发送 `tool`，但仍发送多个 `token` 和一个 `done`。请求体校验错误在建流前返回
HTTP 422。流建立后的模型、数据库、会话或多工具协议错误使用一次脱敏 `error` 事件并立即
结束，不再发送 `done`。

## 11. 聊天页改造（Vibe Coding 例外）

原生 JavaScript 页面继续使用 `fetch()` 读取 POST SSE。改造范围：

- 为浏览器生成并持久化稳定 `user_id`。
- 保存服务端 `done` 帧返回的当前 `conversation_id`。
- 请求只发送 `user_id`、`conversation_id` 与本轮 `message`，不再把客户端数组作为历史权威。
- 收到 `tool` 帧时，在当前 assistant 气泡顶部添加或更新“调用了 query_logistics”徽章。
- 等待工具和首个 token 时保留加载状态；首个 token 到达后开始增量渲染。
- “重新开始”清除当前 `conversation_id` 和页面消息，不删除服务端历史或稳定 `user_id`。
- 继续使用安全 DOM 文本节点渲染，不引入 `innerHTML` 注入风险。

该部分不写前端单元测试；执行 JavaScript 语法检查、静态资源路由测试和真实浏览器三条验收。

## 12. 错误处理

| 场景 | 行为 |
|---|---|
| 请求字段非法 | 建流前 HTTP 422 |
| 会话不存在或不属于用户 | SSE `error`：“会话不存在” |
| 未知工具或参数非法 | 失败 ToolMessage 回灌模型，不执行工具 |
| 查询工具暂时失败 | 按策略重试；耗尽后失败 ToolMessage 回灌 |
| `create_ticket` 失败 | 不重试，失败 ToolMessage 回灌 |
| 模型返回多个工具 | SSE `error`，不执行任一工具 |
| 选择或收敛模型失败 | SSE `error`：“模型服务暂时不可用” |
| MySQL 不可用 | SSE `error`：“数据库暂时不可用” |
| 浏览器中断 | 停止生成；不保存不完整最终回答 |

日志可以记录异常类型、会话 ID、工具名、尝试次数和耗时，但不得记录密钥、数据库密码、
完整连接串或原始上游错误体。

## 13. 测试、评估与验收

### 13.1 真实能力前置探针

正式实现的第一个任务是对当前 `.env` 模型做最小 `@tool` + `bind_tools()` 冒烟，验证返回的
`AIMessage.tool_calls` 包含名称、参数和 ID。探针失败时停止并报告证据；不得自行换模型、
改为关键词路由或换技术栈。

### 13.2 TDD 范围

以下代码严格执行 RED → GREEN → REFACTOR：

- 配置、ORM 映射和 repository 的会话所有权、消息顺序、FAQ LIKE、工单事务。
- 五个工具的参数 Schema、确定性 mock 数据、FAQ 命中/未命中和工单创建。
- 注册表重名拒绝、未知工具、参数错误、可信参数注入、超时、查询重试和写工具不重试。
- 编排器的无工具分支、单工具分支、多工具拒绝、未绑定收敛、持久化顺序和流式事件顺序。
- API 的 422、SSE `tool → token → done`、无工具流、会话错误和脱敏错误。

测试默认不访问真实模型。数据库 repository 测试优先使用 Docker MySQL 测试库，确保 JSON、
时间戳、外键和 LIKE 行为与正式环境一致；测试 fixture 在每个测试间清理自身创建的数据。

### 13.3 Prompt 与标注评估

Prompt 和标注数据不用脆弱的字符串单测代替行为验证。`evals/ch02_cases.json` 至少覆盖：

- 订单查询 → `query_order`
- 商品查询 → `query_product`
- 物流查询 → `query_logistics`
- 退货政策 → `query_faq` 且命中
- 邮费问法 → `query_faq` 且预期未命中
- 明确要求人工处理 → `create_ticket`
- 普通寒暄 → 不调用工具

`scripts/eval_ch02.py` 使用真实配置运行完整集合，记录模型实际选择、工具结果和通过/失败摘要，
但不保存密钥或完整敏感响应。Prompt 或工具描述发生实质变化后必须完整重跑。

### 13.4 最终门禁

- 完整 `pytest` 通过且输出无未解释 warning。
- `python -m compileall` 与 `node --check app/static/chat.js` 通过。
- Docker MySQL 健康，四张表存在，seed 中文数据可正确读取。
- 真实 Function Calling 探针通过，完整标注评估结果已记录。
- 浏览器完成三条验收，并确认工具徽章与最终流式回答。
- `git diff --check`、敏感文件检查和章节边界检查通过。
- `../python/` 与 `ch01-pure-chat/` 均无改动。

## 14. 过程留痕

`dev-notes/ch02.md` 是追加式开发日志。在 brainstorm、书面 spec、计划评审、工作区/基线、
每个 TDD 任务、真实模型探针、标注评估、聊天页浏览器验收、code review 和 finish 后立即追加。
每段包含用户关键原话、产出或验证命令、结果、失败、纠偏与返工；不得把失败结果改写成成功。

## 15. Context7 依据

设计阶段于 2026-09-23 通过 Context7 核对：

- LangChain 当前 Python 文档使用 `@tool`、可选 Pydantic `args_schema`、`bind_tools()`、
  `AIMessage.tool_calls`，并用匹配 `tool_call_id` 的 ToolMessage 将结果回灌模型。
- SQLAlchemy 2.x 文档推荐类型化 Declarative 映射、`mapped_column()`、`sessionmaker`/事务上下文，
  并支持使用 `column.like("%keyword%")` 构造字面 LIKE 查询。
- FastAPI 当前文档支持异步生成器交给 `StreamingResponse`；生成器必须包含可让取消传播的
  await 点，SSE 使用 `text/event-stream` 并关闭代理缓冲。

实施计划阶段仍需针对 SQLAlchemy async session、LangChain 注入参数和 `parallel_tool_calls`
的精确签名再次核对当前文档；若当前库版本与设计冲突，按固定技术选型规则停下请用户决定。

## 16. 明确不做

- 第二轮或持续自动工具调用。
- 多工具并行执行。
- 订单、商品和物流数据库表或真实外部 API。
- 向量检索、全文检索、RAG 或同义词扩展。
- 独立 Agent JSON API；本章能力只长在现有聊天入口及其测试/评估脚本中。
- Alembic 迁移体系、生产部署编排、多租户鉴权、限流和工单幂等设施。
