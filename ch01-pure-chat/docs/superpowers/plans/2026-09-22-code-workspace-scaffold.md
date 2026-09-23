# Tutorial Workspace Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a minimal, independently versioned Python practice project under `MewHelp_AI/code` for following the tutorial from chapter one.

**Architecture:** Keep the upstream `python/` repository read-only and place every new artifact inside the independent `code/` Git repository. Start with a small Python package, a test directory, chapter notes, and project metadata; add runtime dependencies only when a tutorial chapter needs them.

**Tech Stack:** Python 3.12+, standard `pyproject.toml`, Git, PowerShell verification commands

**Spec:** `docs/superpowers/specs/2026-09-22-code-workspace-layout-design.md`

## Global Constraints

- `MewHelp_AI/python` remains unchanged and is used only as tutorial reference source.
- All new code, configuration, tests, documentation, and development notes live under `MewHelp_AI/code`.
- `code/` remains an independent local Git repository with no GitHub remote configured.
- Do not reuse or move the existing `MewHelp_AI/.venv`; a project-local `code/.venv` may be created later.
- Record chapter-one process notes in `dev-notes/ch01.md` as development proceeds.

## Review Focus

- A local `.env` or `.venv` must not be committed; `.gitignore` explicitly excludes both.
- Python bytecode and test caches must not pollute Git status; `.gitignore` covers `__pycache__`, `*.py[cod]`, and `.pytest_cache`.
- The project metadata must parse as valid TOML under Python 3.12; verification uses `tomllib`.
- Empty source and test directories must remain tracked; each contains an `__init__.py` file.
- The reference repository must remain untouched; final verification checks `git -C ../python status --short` is empty.

---

### Task 1: Create the tutorial practice-project scaffold

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `tests/__init__.py`
- Create: `dev-notes/ch01.md`

**Interfaces:**
- Consumes: The repository boundary and layout defined in `docs/superpowers/specs/2026-09-22-code-workspace-layout-design.md`.
- Produces: An importable `app` package, a tracked `tests` package, valid project metadata, and the chapter-one process log.

- [ ] **Step 1: Record the clean reference-repository baseline**

Run:

```powershell
git -C ..\python status --short
```

Expected: no output. If output exists, preserve it and do not modify those paths.

- [ ] **Step 2: Create `.gitignore`**

```gitignore
# Secrets and local configuration
.env
.env.*
!.env.example

# Virtual environments
.venv/
venv/

# Python output
__pycache__/
*.py[cod]
*.egg-info/
build/
dist/

# Test and tool caches
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/

# Editors and operating systems
.vscode/
.idea/
.DS_Store
Thumbs.db
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "mewhelp-learning"
version = "0.1.0"
description = "从头跟随 MewHelp 教程开发的练习项目"
readme = "README.md"
requires-python = ">=3.12"
dependencies = []

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: Create the tracked Python directories**

Create `app/__init__.py`:

```python
"""MewHelp 教程练习项目的应用包。"""
```

Create `tests/__init__.py`:

```python
"""MewHelp 教程练习项目的测试包。"""
```

- [ ] **Step 5: Create `README.md`**

```markdown
# MewHelp 学习项目

这里存放跟随 MewHelp 教程从头开发的代码和过程记录。

## 目录约定

- `app/`：自己编写的应用代码
- `tests/`：自动化测试
- `dev-notes/`：按章节记录开发过程
- `docs/superpowers/`：设计与实施计划
- `../python/`：教程参考源码，不在练习过程中修改

## 环境约定

项目使用 Python 3.12 或更高版本。依赖随教程章节推进加入 `pyproject.toml`，本地密钥写入被 Git 忽略的 `.env`。
```

- [ ] **Step 6: Create `dev-notes/ch01.md`**

```markdown
# 第 1 章开发记录

本文件随第一章开发过程逐步追加，不覆盖先前记录。

## Brainstorm 定稿

## 计划评审

## 任务与 Code Review

## 阶段 Finish

## 关键原话与产出路径

## 拒绝或纠偏

## 翻车与返工
```

- [ ] **Step 7: Validate metadata, tracking, ignores, and repository isolation**

Run:

```powershell
python -c "import pathlib, tomllib; p=pathlib.Path('pyproject.toml'); data=tomllib.loads(p.read_text(encoding='utf-8')); assert data['project']['requires-python'] == '>=3.12'; required=['README.md','.gitignore','app/__init__.py','tests/__init__.py','dev-notes/ch01.md']; assert all(pathlib.Path(x).is_file() for x in required); print('scaffold-ok')"
git check-ignore .env .venv\Scripts\python.exe __pycache__\sample.pyc .pytest_cache\README.md
git -C ..\python status --short
git status --short
```

Expected:

- The first command prints `scaffold-ok`.
- `git check-ignore` prints all four supplied ignored paths.
- The reference-repository status prints nothing.
- The new scaffold files appear as untracked files in the `code` repository.

- [ ] **Step 8: Commit the scaffold**

```powershell
git add .gitignore README.md pyproject.toml app tests dev-notes
git diff --cached --check
git commit -m "chore: scaffold tutorial workspace"
git status --short
```

Expected: the commit succeeds and final `git status --short` prints nothing.
