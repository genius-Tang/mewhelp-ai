# 教程练习工作区设计

## 目标

在 `MewHelp_AI/code` 中从头跟随教程开发，并让所有新代码、新配置、测试、文档和开发记录都位于该目录下。现有的 `MewHelp_AI/python` 保持不变，只作为教程源码参考。

## 项目边界

- `python/`：上游教程源码，不在练习过程中修改。
- `code/`：独立的练习项目，也是独立的本地 Git 仓库。
- 暂不创建 GitHub 远程仓库；需要云端备份或协作时再添加。
- 不移动或复用仓库根目录已有的 `.venv`，后续在 `code/` 内建立自己的开发环境。

## 初始目录

```text
code/
├─ app/                   # 跟随教程编写的应用代码
├─ tests/                 # 自动化测试
├─ dev-notes/
│  └─ ch01.md             # 第一章开发过程记录
├─ docs/
│  └─ superpowers/specs/  # 设计文档
├─ .gitignore
├─ pyproject.toml
└─ README.md
```

## 开发记录约定

`dev-notes/ch01.md` 按阶段追加记录：

- brainstorm 定稿
- 计划评审结论
- 任务实现与 code review 结论
- 阶段 finish 结论
- 关键原话和关键产出路径
- 拒绝或纠偏事项
- 翻车与返工记录

## 验收标准

1. `code/` 是独立的本地 Git 仓库。
2. 新增开发产物全部位于 `code/` 内。
3. `python/` 参考源码没有被修改或移动。
4. 初始目录、说明文件和第一章开发记录已创建。
5. Git 状态能够正常显示并提交这些文件。
