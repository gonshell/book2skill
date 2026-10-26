# AGENT.md — AI 编码协作手册（AI 必读）

> 本文件是给任何在此仓库工作的 AI 编码助手（WorkBuddy / Claude Code / Cursor 等）的
> 任务书与缰绳。**人读 README，AI 读这里。每次开始任务前必须先读完本文件。**

## ⚠️ 当前状态（2026-10-25，v0.1.0）

**P1 核心包行为保持验收完成，系统级联调未做。**

### 已完成的验收（2026-10-25，`bash run_tests.sh` 一键复现，30 例全绿）

| 验收项 | 结论 | 复现方式 |
|---|---|---|
| 行为保持：五册修复产物逐字节一致 | ✅ | `tests/test_behavior_parity.py`（TBP_PARITY_SOURCE） |
| 行为保持：10 个 HTML 逐字节一致 | ✅ | `tests/test_render_parity.py`（约 10 分钟） |
| 行为保持：3 份探测报告全文本一致 | ✅ | `tests/test_inspectors_parity.py` |
| 行为保持：5 册合并输出一致 | ✅ | `tests/test_merge_parity.py` |
| 抽取契约（真实网关样例） | ✅ 8 例 | `tests/test_extraction_contract.py` |
| 命令冒烟（extract/onboard/run/baseline 离线全流程） | ✅ 17 例 | 三套 smoke 测试 |
| 安装冒烟（wheel 安装 + KaTeX 资产随包 + 渲染端到端） | ✅ | 一次性 venv 已实证并删除 |

### 欠账事项（QA debt）

| 欠账事项 | 状态 | 补做条件 | 备注 |
|---|---|---|---|
| 系统级 run 通测（五册真实数据走 `tbp run` 端到端） | ✅ 2026-10-26 完成 | 纯本地实测：五册六门全绿，markdown/images/双版 HTML 与 final 逐字节 SAME，质检报告数值一致，TOC 逐节一致；缺口 page_map.md 已补（13986c1）。临时产物已按用户裁定全删 | 阶段 A 至此全部完成 |
| 联调（WorkBuddy 技能壳端到端演练） | ❌ 未做 | P2 技能壳开工后 | |
| 网关实抽联测（extract 真实抽取） | ✅ 2026-10-26 完成 | 试验册 p51-57 真实网关抽取，对历史基线相似度 98.75%，zip 契约完好；详见工作区 待确定事项台账.md B1 |
| 基准回归实测（`tbp baseline run` 重抽比对） | ✅ 2026-10-26 完成（试验册） | init→run→RC40 三态正确；发现同版本重抽图片指标有噪声（18↔21）、字符稳定；整册基线需原始整书 PDF；详见台账 B2 |

**提醒义务（强制）**：AI 在任何阶段性交付、总结、汇报时，**必须主动提醒**用户：
"本项目除已列表的验收项外，系统级 run 通测、联调与网关侧功能均未实测。"——即使用户没有问。

## 1. AI Coding 输入清单（设计处 = 本节；冻结点 = 接口规格经用户审定）

开工前 AI 应拿到或生成以下输入；**缺项先问用户，不得自行假设**。

### 1.1 图纸（设计与规格）
- `../教材转换工具化方案.md`（工作区，仓库外）——架构、交付形态、workspace/路径契约、
  Canonical Extraction 契约（§4.4）、MinerU 后端契约（§4.3）
- `docs/spec-cli.md` 命令集接口规格——【待起草，是第一步产出；用户审定后冻结为本清单的确定项】

### 1.2 原材料（搬迁源码，均在 `../gzsx-md/`，只读原件）
- `fix_md.py`（1478 行，S1–S20 规则本体）、`md2html.py`、`scan3.py`、`scan_render.py`、
  `scan_md_preview.py`、`postprocess.py`、`rematch_merge.py`、`run_blocks.py`、
  `regen_toc_qa.py`、`run_pipeline.sh`、`render_formulas.js` + `katex/`、`tbpipe/` 骨架
  ——以上为**原件名**；搬迁后的新名一律按 `docs/conventions.md` 附录 A 对照表

### 1.3 裁判（验收基准）
- `../gzsx-md/final/<五册>/markdown.md` + 五册字符数基线——**行为保持对账的唯一裁判**
- `run_pipeline.sh` 的六道质量门原始语义
- 1–2 个 blocks zip 样例 + `ledger.json` 样例（抽取适配器契约测试用）

### 1.4 缰绳（纪律约束，违反即返工）
- **命名与编码规范：见 `docs/conventions.md`（v1.0，强制标准）**——文件/目录/代码命名、
  语言策略、stderr 日志纪律、测试约定、Git 约定均以它为准
- **行为保持**：搬迁只许参数化重组，不许"顺手优化"任何规则语义；过关线 = 五册字符数逐字节一致
- 纯 Python 标准库；Python 3.13 + Node.js；中文路径一律 UTF-8 + `pathlib.Path`
- 术语：包 `textbook-pipe` / 命令 `tbp`（别名 `tbpipe`）/ `baselines`；
  禁止口语比喻词（体检/黄金/钉死/兜底等）进入代码与注释
- 不写改 `../gzsx-md/` 原件与 `final/` 交付物
- 新正则先写覆盖备份全部真实形态的单元测试，再进管线（S20 吞括号教训）

## 2. 任务切法

- 按下方**路线图**（2026-10-25 用户确认版）逐步推进，每步 = 目标 + 涉及源文件 + 验收命令
- 一模块一 commit，message 注明源文件与搬迁方式
- **用户当前策略**：开发先行；联调放到最后（实测全部完成后）

### 路线图（2026-10-25 确认）

**阶段 A —— 纯本地**
1. ✅ 规格先行（spec-cli / install / backend / conventions 四手册）
2. ✅ 引擎搬迁（四套行为保持对账逐字节一致）
3. ✅ CLI 接线（七命令）+ P1 验收 + v0.1.0（run_tests.sh 30 例全绿）
4. ✅ 技能壳（P2）：SKILL.md + precheck 自检 + out 路径注入 + references（4aa7994，自测 10 例并入 run_tests.sh 共 40 例）
5. ✅ 系统级 run 通测：五册端到端（2026-10-26），md/images/双版 HTML 与 final 逐字节 SAME；run 补生 page_map.md（13986c1）

**阶段 B —— 实测（需外部条件）**

6. ✅ 网关实测（2026-10-26）：extract 实抽联测（相似度 98.75%）、`baseline run` 重抽比对（RC40 三态正确；图片指标有 run 间噪声、字符稳定）、MinerU 版本 4.0.12、8/8 权重 sha256、wrapper 端点面，并登机核实 **GPU（2×TITAN X 12GB / 驱动 535.309.01 / basic 档仅占 784 MiB）与完整 docker run 参数（`mineru:pascal` + 官方 `mineru-kit api-server`，零挂载，模型落地 `/root/.mineru/models/`）**——MinerU 侧待确认项全部清零
7. ⬜ 化学书实战：第一本化学教材端到端转换（依赖化学 PDF + 网关）

**阶段 C —— 联调（实测全部完成后）**

8. ⬜ WorkBuddy 技能壳端到端联调（对话指令 → 技能壳 → tbp → 产物回显）
9. ⬜ 全链路验收收尾、销账、视情况打 v0.2.0
