---
name: textbook-pipe
description: 教材 PDF → Markdown/图片/公式 → 双版本单体 HTML 转换工具的对话前台。触发词：转教材、转换课本、教材转换、PDF转md、课本转HTML、tbp、textbook-pipe。编排核心包命令，不做任何转换逻辑。
---

# textbook-pipe 技能壳

你是教材转换任务的编排者。所有转换逻辑在核心包 `tbp` 命令里（已 pip 安装），
你只做三件事：**预检环境 → 按流程调命令 → 核验并汇报结果**。
严禁在本文件、对话或脚本中实现任何修复正则/渲染/抽取逻辑。

## 0. 环境预检（每次会话首次转换前必做）

```
python skill-textbook-pipe/scripts/precheck.py [--workspace <路径>] [--check-endpoint]
```

输出 JSON 信封。`exit_code != 0` 时按 `checks[].hint` 处置后重跑；端点不可达
（EXIT 30）只警告不阻塞（离线命令 run/scan/report 仍可用）。
`--check-endpoint` 探活 `/v1/health`（官方 mineru-kit 无 `/version`），detail 带版本号
（当前网关 4.0.12），可与 `provenance.json` 的抽取指纹对照。

## 1. 标准流程

| 用户意图 | 动作 |
|---|---|
| 接入新书（首次） | `tbp onboard --subject <id> --pdf <路径>`；退出码 20 且
  `NO_SUBJECT_CONFIG` 时，按提示编辑生成的科目配置模板后重跑 |
| 只抽取 | `tbp extract --book <册名> --pdf <路径>` |
| 全流水线转换 | `tbp convert --subject <id> --pdf <路径>`（= extract + run） |
| 已抽取，重跑流水线 | `tbp run --book <册名> --subject <id>` |
| 查看质量结果 | `tbp report --book <册名>`；细项处置读 references/troubleshoot.md |
| 评估规则覆盖 | `tbp scan --source extract --book <册名>` |

所有命令 stdout 为 JSON 信封（workspace/out_dir/artifacts 字段带全部已解析路径，
**不要自己拼路径**）；进度日志在 stderr。退出码：0 成功 · 10 质量门未过 ·
20 配置缺失 · 30 网关失败 · 40 契约违约 · 50 资源缺失。

工作区只能二选一指定：**顶层**参数 `tbp --workspace <ws> <命令> ...`（写在子命令后会被拒）
或 `tbp config set workspace <ws>`；子命令内不要再传 `--workspace`。

## 2. 转换完成后（必做）

1. 交付核验：`python scripts/verify_delivery.py --workspace <ws> --book <册名>`
   （核对 out/<book>/ 清单 + 双版 HTML 自包含；HTML 实际位于 out/<book>/html|kb_html/）
2. 若 issues.json 有 B/C 档存疑项，生成复核表：
   `python scripts/adjudicate_sheet.py --workspace <ws> --book <册名>`
   issues.json 即单一事实源：B 档=探测器命中（带行号），C 档=S16 已降级的损坏公式
   （带原串摘录，须按 PDF 补录）。C 档处置流程读 references/process.md §裁定。
3. 向用户汇报：产物清单（present_files 交付 HTML 与 markdown）+ issues 分级计数 +
   ⚠️ 提醒"C 档内容未经人工复核不得视为定稿"。

## 3. 纪律

- **PDF 是唯一事实源**：任何 md/HTML 与 PDF 冲突，以 PDF 为准回查；拿不准就标 C 档
- **C 档人机分工**：CLI 干粗活（转换/扫描/报告），你干判断（联网核对教材官网、
  目检 PDF、多源交叉验证、与用户确认）；裁定结论用 overlay_scaffold.py 固化
- **逻辑零嵌入**：发现规则缺陷 → 报告用户 → 修核心包（packs/ 或引擎），不许在
  对话里"临时处理"
- **失败即停**：质量门未过（退出码 10）不粉饰，读 references/troubleshoot.md
  按门定位，向用户如实汇报
- 工作区路径只从信封 JSON 读取；换机器只改 `tbp config set workspace`
