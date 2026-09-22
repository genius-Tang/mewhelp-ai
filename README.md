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
