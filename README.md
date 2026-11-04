# book2skill

[![CI](https://github.com/gonshell/book2skill/actions/workflows/ci.yml/badge.svg)](https://github.com/gonshell/book2skill/actions/workflows/ci.yml)

教材 → 教学能力的工具集合。每个子目录是一个自包含模块（独立 Python 包、独立 CLI、
独立测试与技能壳），彼此不共享运行时代码。

**当前能力**：人教A版高中数学必修一/必修二已上线——PDF 已转 Markdown，
**159 个知识点节点**（78+81）冻结图谱运行于内网服务器，四个学习技能
（答疑/带学/刷题/复习）可装即用。

## 文档地图（从"你想干什么"进）

| 你想… | 去读 | 一句话 |
|---|---|---|
| 了解整个系统有哪些东西 | [docs/system-architecture.md](docs/system-architecture.md) | 五系统分层 + 服务谁 + 建设状态 |
| 看做到哪了/接下来做什么 | [docs/roadmap.md](docs/roadmap.md) | 里程碑状态表（权威） |
| **部署/运维服务器** | [docs/ops-runbook.md](docs/ops-runbook.md) | 要求清单→bootstrap→部署→回滚→备份→巡检→故障速查 |
| **制一本新书**（PDF→学生可用） | [docs/production-runbook.md](docs/production-runbook.md) | 八步剧本，一册≈半天，人工裁定是核心 |
| 组织学生试用 | [ops/试用指南-学生版.md](ops/试用指南-学生版.md)、[ops/试用-观察清单.md](ops/试用-观察清单.md) | 学生 5 分钟上手；运营周报三段式 |
| 改 book2qa 代码 | [book2qa/README.md](book2qa/README.md) | 十命令表+数据布局+154 测试 |
| 改图谱字段/锚点契约 | [book2qa/docs/graph-spec.md](book2qa/docs/graph-spec.md) | **冻结区**，改前先读规则 |
| 改检索/输出模板 | [book2qa/docs/retrieval.md](book2qa/docs/retrieval.md)、[book2qa/docs/skill-io.md](book2qa/docs/skill-io.md) | 五路召回、六模板、兜底三级 |
| 理解架构设计决策 | [book2qa/docs/arch.md](book2qa/docs/arch.md)、[book2qa/docs/design.md](book2qa/docs/design.md) | 分层/边界/红线 |
| 查历史评审与裁定 | [book2qa/docs/pending-review.md](book2qa/docs/pending-review.md)、[book2qa/docs/deployment-review.md](book2qa/docs/deployment-review.md) | 过程台账（部分已销） |

## 模块

| 目录 | 名称 | 职责 | 版本 |
|---|---|---|---|
| [`book2md/`](book2md/) | **book2md** | 教材 PDF → Markdown + 图片 + 公式 → 双版本单体 HTML（阅读版 / 知识库版） | v0.3.2 |
| [`book2qa/`](book2qa/) | **book2qa** | 教材 Markdown → 知识点图谱 → 学生问答 / 精学 / 练习 / 复习（双册已上线） | **v0.7.0** |

`book2md` 的前身是 `textbook-pipe`（2026-10-27 更名并迁入本仓库）。历史记录见
[book2md/CHANGELOG.md](book2md/CHANGELOG.md) 与 [book2md/docs/qa-ledger.md](book2md/docs/qa-ledger.md)。

## 快速开始

**book2qa（学习服务，当前主线）**：
```bash
git clone git@github.com:gonshell/book2skill.git
cd book2skill/book2qa
pip install -e .                                    # Python ≥ 3.12
b2q --version                                       # → b2q (book2qa) 0.7.0
b2q serve                                           # 本地起 API（8100）；部署见 ops-runbook
```
（图谱已冻结在仓库 `book2qa/data/<册>/`，克隆即有；向量索引按 runbook 重算或用发布产物。）

**book2md（抽取，制书上游）**：
```bash
cd book2md
pip install -e .          # 需要 Python ≥ 3.13
b2m --version             # → b2m (book2md) 0.3.2
b2m config set workspace /path/to/workspace
b2m config set backend_endpoint http://127.0.0.1:8000   # 示例值：网关与客户端同机；跨机换成实际地址
```

> 端点没有硬编码进代码，一律由 `B2M_BACKEND_API` 环境变量或 `~/.book2md/config.json`
> 的 `backend_endpoint` 决定（见 [book2md/docs/backend.md](book2md/docs/backend.md) §1）。
> 在**仓库根目录**执行 `python -m book2md.cli` 会失败（目录名与包名冲突）——用 `b2m`
> 命令，或先 `cd book2md`。

## 测试

```bash
cd book2qa && python -m unittest discover -s tests    # 154 例（真实语料类自动 skip）
cd book2md && bash run_tests.sh                       # 73 例，纯本地，约 1 分钟
B2M_PARITY_SOURCE=/path/to/history bash run_tests.sh  # 追加 5 套行为保持对账，约 20 分钟
```

说明：**对账测试**需要历史产物目录（内含教材原文，不入库）作裁判，缺失自动跳过；
**CI**（GitHub Actions）双 job：book2md 73 例 + book2qa 154 例。

## 约定

1. **命名**：`book2<产物形态>`——`book2md`（转 Markdown/HTML）、`book2qa`（问答/学练），
   未来的 `book2quiz`、`book2slides` 等。名字直接说明输入与输出。
2. **模块边界**：一个模块 = 一个 Python 包 + 一套 CLI + 一份 `AGENT.md` + 一套测试。
   模块之间不直接 `import`；跨模块协作走文件产物或显式接口。
3. **不入库的东西**：教材原件（gzsx-md）、学生数据（store.sqlite）、运行态
   （日志/绘图缓存/邀请码）。冻结图谱与裁定表**入库**（数据按册：`book2qa/data/<册>/`）。
4. **新增模块**前先在本文档的模块表登记一行，写明职责与状态。

## 环境基准

book2md：Python 3.13 / Node.js 22 ｜ book2qa：Python ≥ 3.12（服务器实测 3.12）。
依赖锁定见各模块 `docs/install.md` 或 pyproject。

## 许可证

[MIT](LICENSE)。仅授权代码本身；教材原文版权归原出版方，使用本工具处理教材
不改变教材的版权归属。
