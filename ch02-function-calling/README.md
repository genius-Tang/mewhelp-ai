# Chapter 02：工具增强的电商智能客服

本章在第一章的流式客服基础上加入 MySQL 持久化、订单与物流查询、商品查询、FAQ 查询及人工工单工具。服务端保存会话历史，浏览器只提交用户标识、当前问题和可选会话 ID；工具调用会在聊天页显示徽标。

## 本地环境

在 `ch02-function-calling` 目录中运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

填写 `.env` 的模型配置，并分别为 `MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD` 设置仅用于本机的随机密码；将相同的普通用户密码填入 `DATABASE_URL` 和 `TEST_DATABASE_URL`，并确认端口与 `MYSQL_PORT` 一致。密码包含 `@`、`:` 等 URL 特殊字符时，数据库 URL 中的密码须做百分号编码。Compose 缺少这两个密码会直接报错。`.env` 只保存在本机，不提交到 Git；MySQL 仅映射到 `127.0.0.1`。

## 启动演示

```powershell
docker compose up -d mysql
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

浏览器打开 <http://127.0.0.1:8000/>；API 文档位于 <http://127.0.0.1:8000/docs>。以下三条命令可分别在另一个 PowerShell 窗口运行，每条都创建新会话。继续同一会话时，把前一次 `done` 事件的 `conversation_id` 作为 JSON 数值加入请求。

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/chat/stream -H "Content-Type: application/json" -d '{"user_id":"demo-logistics","message":"订单 1001 的物流到哪了"}'
curl.exe -N -X POST http://127.0.0.1:8000/chat/stream -H "Content-Type: application/json" -d '{"user_id":"demo-return","message":"退货政策是什么"}'
curl.exe -N -X POST http://127.0.0.1:8000/chat/stream -H "Content-Type: application/json" -d '{"user_id":"demo-postage","message":"邮费是多少"}'
```

正常响应依次发出 `tool`、若干 `token` 和 `done` SSE 事件。物流与退货政策应命中相应工具；邮费问题会调用 FAQ，但当前演示数据中没有匹配项，回答应如实说明未找到，不应编造金额。

运行七例真实模型评估与测试：

```powershell
python scripts/eval_ch02.py
python -m pytest -q -p no:cacheprovider
```

结束演示时可运行 `docker compose down`。`docker compose down -v` 会删除本地演示数据卷和其中的数据，只有明确希望清空数据时才运行。
