# book2qa

教材 PDF（经 book2md 产物）→ 知识点图谱 → 四场景学习技能（答疑/带学/刷题/复习）。

> 顶层系统视图：[docs/system-architecture.md](../docs/system-architecture.md) ｜
> 里程碑状态：[docs/roadmap.md](../docs/roadmap.md) ｜ 部署运维：[ops-runbook.md](../docs/ops-runbook.md)

## 快速开始（已装好的环境）

```bash
b2q serve                     # 启动 API（8100）；或 docker compose（见 ops-runbook）
# 学生侧：WorkBuddy 装四个 skill（skills/book2qa-{ask,learn,drill,review}）
# 配置：~/.book2qa/serve.json（serve_url / api_key / account）
```

## 命令一览（`b2q <cmd>`）

| 命令 | 用途 | 关键产物 |
|---|---|---|
| `build --book X --stage structure` | 页锚定+标题结构 | data/X/structure.jsonl, para_meta.jsonl |
| `build --stage extract` | 题目/图号/公式抽取 | exercises/figures.jsonl |
| `build --stage candidates` | 知识点候选（机器初稿） | candidates.jsonl |
| `build --stage graph` | **质量闸**+prereq → 正式图谱 | graph.jsonl（闸不过不落盘） |
| `review-export --book X` | 裁定辅助：候选 → Excel（人批注） | review-X.xlsx |
| `review-import --book X --file f [--apply]` | 批注执行（拆/并/改名/别名），不带 --apply 只预览 diff | 新 candidates + diff |
| `index --book X` | R4 向量索引（bge 512 维） | vectors.npz |
| `recall --book X --query "…"` | 五路检索（词表/段落/结构/向量+RRF） | 信封（intent/candidates） |
| `node <id>` | 单节点全料 | — |
| `serve` | FastAPI 运行主体（/recall /node /section /due /log /context /plot /img） | — |

另：`scripts/eval_recall.py`（gold 评测）、`scripts/inspect_report.py`（巡检周报）、
`scripts/simulate_ask.py` / `simulate_m4.py`（skill 契约模拟）、`scripts/draft_review.py`（裁定初稿）。

## 目录与数据布局

```
book2qa/
├── data/<册>/          # 冻结产物（入 git）：structure/para_meta/candidates/
│                       #   graph/exercises/figures.jsonl + vectors.npz + review*.xlsx
├── data/eval_gold.jsonl # 评测基准（入 git）
├── data/store.sqlite    # 学生学情（不入 git，走备份）
├── data/request_log.jsonl / plots/ / inspect/ / trial/   # 运行态（不入 git）
└── tests/               # 154 例；真实语料类自动 skip
```

## 文档索引

| 主题 | 文档 |
|---|---|
| 产品与里程碑 | docs/design.md、docs/roadmap.md |
| 图谱契约（冻结区） | docs/graph-spec.md |
| 检索与输出模板 | docs/retrieval.md、docs/skill-io.md |
| 部署与运维 | docs/infra-server.md、**docs/ops-runbook.md** |
| 架构 | docs/arch.md、docs/system-architecture.md |

## 测试与质量

```bash
python -m unittest discover -s tests   # 154 例全绿才算改完
```
三层质量关：build 质量闸（结构阻断/内容降级）→ 输出校验（skill 侧防编造）→
巡检（request_log 未命中周报）。
