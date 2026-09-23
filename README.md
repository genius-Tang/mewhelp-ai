# MewHelp 学习项目

本仓库用于跟随教程从零开发电商智能客服。第 1 章只实现纯对话、SSE 增量输出、多轮历史裁剪和售后信息结构化提取。

## 本地环境

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

填写 `.env` 后运行：

```powershell
uvicorn app.main:app --reload
```

`.env` 只保存在本机，不提交到 Git。

服务启动后，在浏览器打开 <http://127.0.0.1:8000/> 使用客服聊天页面；API 调试文档仍位于 <http://127.0.0.1:8000/docs>。

## 第 1 章验收

启动服务：

```powershell
uvicorn app.main:app --reload
```

流式对话：

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/chat/stream -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"我买的耳机有杂音"}]}'
```

第二轮把第一轮消息和回答一起提交：

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/chat/stream -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"我买的耳机有杂音"},{"role":"assistant","content":"请提供订单号"},{"role":"user","content":"订单号是 A12345，我刚才遇到什么问题？"}]}'
```

结构化提取：

```powershell
curl.exe -X POST http://127.0.0.1:8000/extract/after-sales -H "Content-Type: application/json" -d '{"description":"订单 A12345 的耳机有杂音，我想退货退款"}'
```

运行标注评估集：

```powershell
python scripts/eval_ch01.py
```
