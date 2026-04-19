# 开发设计文档 OpenSpec v1

当前项目的开发设计文档已按 `OpenSpec` 结构重组，不再以单一长文档维护，而是拆分为标准工件：

- `proposal.md`：说明为什么做、范围是什么
- `design.md`：说明怎么做
- `tasks.md`：说明实现任务和当前进度
- `specs/<domain>/spec.md`：说明需求增量与场景

## 文件位置

- [proposal.md](</C:/Users/Administrator/Desktop/财务统计软件/openspec/changes/desktop-finance-mvp/proposal.md>)
- [design.md](</C:/Users/Administrator/Desktop/财务统计软件/openspec/changes/desktop-finance-mvp/design.md>)
- [tasks.md](</C:/Users/Administrator/Desktop/财务统计软件/openspec/changes/desktop-finance-mvp/tasks.md>)
- [spec.md](</C:/Users/Administrator/Desktop/财务统计软件/openspec/changes/desktop-finance-mvp/specs/finance-reporting/spec.md>)

## 结构说明

本次重组采用 OpenSpec 官方推荐的变更目录结构：

```text
openspec/
  changes/
    desktop-finance-mvp/
      proposal.md
      design.md
      tasks.md
      specs/
        finance-reporting/
          spec.md
```

## 当前建议

后续如果你继续追加功能，不再直接改老的“开发设计文档”长文，而是按 OpenSpec 流程新增 change，例如：

```text
openspec/changes/<new-change-name>/
```

这样每次变更都有独立的提案、设计、任务和需求增量，后续更适合持续维护。
