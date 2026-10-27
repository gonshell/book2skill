# book2md

教材 PDF → Markdown + 图片 + 公式 → 双版本单体 HTML（阅读版 / 知识库版）的独立转换工具。
`book2skill` 平台的第一个模块（前身 `textbook-pipe`，2026-10-27 更名）。

源自人教A版高中数学 5 册转换项目沉淀的引擎，产品化重构为可复用工具包，
供后续学科教材（化学 / 物理）接入复用。设计文档见 [docs/design.md](docs/design.md)，
网关部署见 [docs/mineru-selfhost.md](docs/mineru-selfhost.md)。

> **状态（2026-10-27）**：v0.3.0（更名 + 迁入 book2skill）—— 七命令接线完毕，五册系统级通测、
> 网关实抽 / 基准回归实测、化学书（首本非数学教材）端到端、技能壳联调全部完成
> （回归 69 例 + 5 套行为保持对账全绿）。遗留仅人工复核队列（TOC OCR 噪音、
> 损坏公式按 PDF 补录）——见 [AGENT.md](AGENT.md) 欠账台账。

## 安装

依赖版本锁定见 [docs/install.md](docs/install.md)（Python 3.13 / Node.js 22 / KaTeX 0.16.11 随包）。

```bash
pip install book2md          # 或从仓库目录：pip install .
b2m --help                         # 入口命令（等价 python -m book2md.cli）
```

KaTeX 渲染资产随包分发，无需另装；渲染需要系统有 Node.js（v22 实测）。

## 五分钟上手

```bash
# 0) 工作区初始化（默认取 B2M_WORKSPACE 或当前目录）
b2m config set workspace /path/to/workspace

# 1) 新书接入：生成科目配置模板 → 编辑 → 抽取 + 基线扫描
b2m onboard --subject chem-renjiao --pdf 化学必修第一册.pdf

# 2) 全流水线：修复 → 双版渲染 → 自包含校验 → 三套扫描 → 报告
b2m run --book 化学必修第一册 --subject chem-renjiao

# 3) 查看质量门结果
b2m report --book 化学必修第一册
```

所有命令输出 JSON 信封（stdout 单出口），退出码：
`0` 成功 · `10` 质量门未过 · `20` 配置缺失 · `30` 网关失败 · `40` 契约违约 · `50` 资源缺失。

## 命令一览

| 命令 | 用途 |
|---|---|
| `b2m config` | 工作区 / 端点 / 科目配置读写 |
| `b2m extract` | PDF → Canonical Extraction v1（网关抽取 + 页序归一化） |
| `b2m onboard` | 新书接入（配置模板 + 网关预检 + 抽取 + 基线扫描） |
| `b2m run` | 质量门流水线（staging 原子落盘，失败不覆盖旧版） |
| `b2m convert` | extract + run 原子组合 |
| `b2m report` | 质检报告 + 目录重生成 |
| `b2m scan` | 只读扫描（`--source extract` 评估规则包覆盖 / `--source out` 回归过关线） |
| `b2m baseline` | 基准回归 init/run（防后端静默漂移） |

详见 [docs/spec-cli.md](docs/spec-cli.md)。

## 工作区目录契约

```
<workspace>/
├── blocks/<book>/        抽取块缓存（断点续跑，Adapters 原始返回）
├── extract/<book>/       归一化抽取产物（contract.json + markdown.md + images/）
├── out/<book>/           流水线终产物（markdown/HTML/issues/qa_gate.log）
├── out/<book>.prev-*/    上一次成功版本（run 晋升时自动轮换）
├── html/ kb_html/        阅读版 / 知识库版 HTML（run 产出）
├── ledger.json           抽取账本（块状态断点续跑）
└── baselines/<subject>/  基准回归基线（baseline.json + 样本）
```

## 回归测试

```bash
bash run_tests.sh                                  # 契约 + 冒烟（不依赖历史产物）
B2M_PARITY_SOURCE=<gzsx-md> bash run_tests.sh      # 追加四套行为保持对账（约 11 分钟）
```

## 文档

- [AGENT.md](AGENT.md) — AI 协作手册、欠账台账（人读 README，AI 读这里）
- [docs/spec-cli.md](docs/spec-cli.md) — 命令集接口规格（实现以此为准）
- [docs/install.md](docs/install.md) — 版本锁定表
- [docs/backend.md](docs/backend.md) — MinerU 网关契约与探测记录
- [docs/conventions.md](docs/conventions.md) — 命名与编码规范
- [CHANGELOG.md](CHANGELOG.md) — 变更日志

## 结构（一核一壳）

```
book2md/           核心包（P1，本版本交付）：引擎 + 适配器 + CLI（b2m）
├── engine/              rules（S1–S20）/ render / inspectors / reporting
├── extractors/          mineru（网关适配）/ merge（页序归一化）
├── commands/            七命令实现 + JSON 信封
├── configs/             backends 网关契约 + 科目配置
├── packs/               L1 学科规则包（math 已有，chem/physics 预研）
└── assets/katex/        KaTeX 0.16.11 预渲染资产（随包分发）
skill-book2md/     WorkBuddy 技能壳（P2）：SKILL.md + 4 脚本 + 4 参考文档 + 报告模板
tests/                   九套测试 + 抽取契约真实样例（fixtures/）
docs/                    四手册（spec / install / backend / conventions）
```
