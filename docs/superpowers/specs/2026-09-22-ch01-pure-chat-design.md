# 第 1 章：纯对话服务设计

## 1. 目标与范围

本章在 `code/` 独立仓库中从零建立电商智能客服后端，先跑通纯对话能力：多轮上下文、SSE 增量输出、模板化 System Prompt、售后描述结构化提取，以及最小可用的历史裁剪和 token 预算。

本章不实现工具调用、Agent 循环、数据库、服务端会话存储或聊天页面。`../python/` 只作为教程参考源码，不修改、不移动。

此前的 `docs/superpowers/plans/2026-09-22-code-workspace-scaffold.md` 只描述通用空脚手架；本设计及其后续实施计划将其纳入并取代，避免重复搭建。

## 2. 固定技术边界

- Python 3.12 或更高版本。
- FastAPI 提供 HTTP API。
- LangChain 管理聊天模型、Prompt、消息对象、历史裁剪和结构化输出。
- `ChatOpenAI` 通过自定义 `base_url` 连接 OpenAI 兼容端点。
- 本章不实现 Anthropic 原生 API；Claude 只有在外部网关提供 OpenAI 兼容协议时才可能接入，但不作为验收目标。
- 所有地址、密钥、模型名和结构化输出模式来自 `.env`，不得硬编码或写入日志。
- 具体库接口在实现前通过 Context7 查询当前官方文档；不能凭记忆替换固定技术选型。

## 3. 项目结构

```text
code/
├─ app/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ api/
│  │  ├─ __init__.py
│  │  ├─ chat.py
│  │  └─ extraction.py
│  ├─ core/
│  │  ├─ __init__.py
│  │  ├─ config.py
│  │  ├─ model.py
│  │  ├─ prompts.py
│  │  └─ messages.py
│  ├─ schemas/
│  │  ├─ __init__.py
│  │  ├─ chat.py
│  │  └─ after_sales.py
│  └─ services/
│     ├─ __init__.py
│     ├─ chat.py
│     └─ extraction.py
├─ tests/
├─ evals/ch01_cases.json
├─ scripts/eval_ch01.py
├─ dev-notes/ch01.md
├─ docs/superpowers/
├─ .env.example
├─ .gitignore
├─ pyproject.toml
└─ README.md
```

边界职责：

- `api/` 只负责请求校验后的路由协调、HTTP 状态与 SSE 响应。
- `schemas/` 定义公开输入输出契约。
- `core/` 封装配置、模型工厂、Prompt 和消息裁剪等基础能力。
- `services/` 组合基础能力完成对话流或结构化提取，模型通过依赖注入传入，测试可替换为假模型。
- `evals/` 与 `scripts/` 验证 Prompt 和真实上游表现，不替代单元测试。

## 4. 配置

`.env.example` 暴露以下变量：

```dotenv
CHAT_BASE_URL=https://api.example.com/v1
CHAT_API_KEY=replace-me
CHAT_MODEL=replace-me
CHAT_STRUCTURED_OUTPUT_METHOD=function_calling
HISTORY_MAX_TOKENS=4000
```

规则：

- `CHAT_BASE_URL`、`CHAT_API_KEY`、`CHAT_MODEL` 不能为空，应用启动时完成校验。
- `CHAT_STRUCTURED_OUTPUT_METHOD` 只允许 `function_calling`、`json_mode`、`json_schema`，默认 `function_calling`。
- 结构化输出模式取决于上游模型能力；换模型时可能需要同步修改该配置。应用不静默降级到另一种模式。
- `HISTORY_MAX_TOKENS` 必须为正整数，默认 `4000`。
- `.env`、虚拟环境、Python 缓存和测试缓存全部被 Git 忽略。

## 5. 对话接口

### 5.1 请求

`POST /chat/stream`

```json
{
  "messages": [
    {"role": "user", "content": "我买的耳机有杂音"},
    {"role": "assistant", "content": "请问订单号是多少？"},
    {"role": "user", "content": "订单号是 A12345"}
  ]
}
```

- `messages` 至少包含一条消息。
- 角色只允许 `user` 和 `assistant`；客户端不能提供或覆盖 System Prompt。
- `content` 去除首尾空白后不得为空。
- 最后一条消息必须是 `user`。

### 5.2 Prompt 与历史裁剪

服务端使用 `ChatPromptTemplate`，由固定 System Prompt 和裁剪后的历史消息占位符组成。System Prompt 要求模型：

- 只以电商客服身份回应，语气简洁、礼貌，并沿用用户当前语言。
- 信息不足时先追问，不编造订单状态、退款结果、物流进度或平台政策。
- 本章没有工具能力，不声称已经查询数据库或完成退款、换货等业务操作。
- 对超出范围的问题说明能力边界。

客户端历史转换为 LangChain 消息后，使用 `trim_messages`、`strategy="last"` 和 `count_tokens_approximately` 按 `HISTORY_MAX_TOKENS` 保留最近的完整消息序列。裁剪不得产生以 assistant 开头的无效上下文，并必须保留最新用户消息。若最新用户消息本身超过预算，返回 `422`，不静默截断用户原文。

### 5.3 SSE 响应

FastAPI 使用异步生成器与 `StreamingResponse`，媒体类型为 `text/event-stream`。上游每产生一个非空文本增量就立即发送，不缓冲、不重新分词。

正常增量：

```text
event: token
data: {"content":"您好"}

```

正常结束：

```text
event: done
data: {}

```

流建立后的上游异常：

```text
event: error
data: {"code":"upstream_error","message":"模型服务暂时不可用"}

```

发送 `error` 后立即结束，不再发送 `done`。响应和日志都不得泄露密钥或完整上游错误体。模型返回空内容时发送 `done` 并记录不含敏感信息的警告。

## 6. 售后结构化提取接口

`POST /extract/after-sales`

请求：

```json
{"description":"订单 A12345 的耳机有杂音，我想退货退款"}
```

响应 schema：

```json
{
  "order_id": "A12345",
  "request_type": "退货",
  "expected_solution": "退货退款"
}
```

字段规则：

- `order_id`: `string | null`，只提取原文明确出现的订单号。
- `request_type`: `退货 | 退款 | 换货 | 补发 | 维修 | 物流查询 | 其他`。
- `expected_solution`: `string | null`，简短概括用户明确表达的期望方案。
- 模型不得补充原文没有的信息。

实现使用单独的提取 Prompt 和 `ChatOpenAI.with_structured_output(AfterSalesResult, method=配置值)`。结果必须经过 Pydantic 校验。上游调用、解析或校验失败统一映射为不泄露内部信息的 `502`。

## 7. 错误处理

- FastAPI/Pydantic 请求校验错误使用 `422`。
- 最新用户消息单独超过 token 预算使用 `422`，返回稳定错误说明。
- 非流式结构化上游错误使用 `502`。
- SSE 流建立后的异常通过一次 `error` 事件报告并结束。
- 启动配置错误使应用启动失败，并指出缺少的配置名；不得打印配置值。
- 应用不对不兼容的结构化输出模式做自动降级，避免掩盖供应商能力差异。

## 8. 测试与评估

### 8.1 TDD 范围

以下可单测代码遵循红—绿—重构：

- 配置必填项、默认值、合法枚举和非法 token 预算。
- 请求 schema、角色限制、空内容和最后消息角色。
- 消息转换与裁剪：超预算删除最旧消息、保留最近完整轮次、保留最新用户消息、单条超预算报错。
- SSE JSON 编码、事件顺序、空 chunk 跳过、正常完成和错误终止。
- 对话 service 对假模型增量的无缓冲转发。
- 结构化 service 对 Pydantic 结果和异常的处理。
- API 集成：状态码、SSE 响应头、事件内容、结构化 JSON 与错误映射。

测试使用依赖注入和假模型，不访问真实上游。

### 8.2 Prompt 与数据评估

Prompt 和标注数据不强行写成单元测试。`evals/ch01_cases.json` 至少包含：普通商品咨询、信息不足追问、禁止编造订单状态、禁止声称已执行退款、带订单号的退货退款、无订单号换货、物流查询、无法分类描述。

`scripts/eval_ch01.py` 使用真实 `.env` 模型运行标注集，输出逐案例结果和通过/失败摘要。每次 Prompt 实质修改后至少回归一次，并立即把结果追加进 `dev-notes/ch01.md`。

## 9. 验收标准

1. `pytest` 全部通过，测试不访问真实模型。
2. `uvicorn app.main:app --reload` 可启动服务。
3. `curl -N` 调用 `/chat/stream` 能观察到多个 `token` 事件和最终 `done`。
4. 把第一轮完整历史与第二轮问题一起提交，第二轮回答能延续上下文。
5. 调用 `/extract/after-sales` 返回符合固定 schema 的 JSON。
6. 标注评估集使用真实配置模型跑完并留下结果摘要。
7. `dev-notes/ch01.md` 已在 brainstorm、计划评审、每个任务、code review 和 finish 阶段分别追加记录。
8. `../python/` 参考仓库未被修改。

## 10. Context7 文档依据

设计阶段通过 Context7 查询并采用以下当前官方接口：

- FastAPI `StreamingResponse` 与异步生成器：`https://fastapi.tiangolo.com/advanced/custom-response`。
- LangChain OpenAI 兼容 `ChatOpenAI(base_url=..., api_key=..., model=...)`。
- LangChain `trim_messages` 与 `count_tokens_approximately`。
- LangChain `with_structured_output` 的 `function_calling`、`json_mode`、`json_schema` 模式及 Pydantic schema。

实施时若接口细节仍有歧义，必须再次查询 Context7；不得以其他框架或手写解析替换固定方案。
