# AGENT.md — AI 编码协作手册（AI 必读）

> 本文件是给任何在此仓库工作的 AI 编码助手（WorkBuddy / Claude Code / Cursor 等）的
> 任务书与缰绳。**人读 README，AI 读这里。每次开始任务前必须先读完本文件。**
>
> **更名说明（2026-10-27）**：本仓库原名 `textbook-pipe`（命令 `tbp`），v0.3.0 起更名
> `book2md`（命令 `b2m`），并迁入平台目录 `book2skill/`。本文中如遇历史记录里的旧名，
> 指的都是本包。

## ⚠️ 当前状态（2026-10-27，v0.3.0）

**全链路实测与联调完成：五册系统级通测、网关实抽/基准回归、化学书端到端、技能壳五步交付全通。**
遗留：仅 E 人工复核队列（TOC OCR 噪音、2 条损坏公式按 PDF 补录等，故意不自动改写）。
下一版本候选方向：覆盖层（L2）规则加载机制、更多学科接入。

### 已完成的验收（2026-10-27，`bash run_tests.sh` 一键复现，67 例 + 5 套对账全绿）

| 验收项 | 结论 | 复现方式 |
|---|---|---|
| 行为保持：五册修复产物一致（含 9 行已声明改动） | ✅ | `tests/test_behavior_parity.py`（B2M_PARITY_SOURCE） |
| 行为保持：10 个 HTML 逐字节一致 | ✅ | `tests/test_render_parity.py`（约 14 分钟） |
| 行为保持：3 份探测报告全文本一致 | ✅ | `tests/test_inspectors_parity.py` |
| 行为保持：5 册合并输出一致（含 4 行已声明改动） | ✅ | `tests/test_merge_parity.py` |
| 抽取契约（真实网关样例） | ✅ 8 例 | `tests/test_extraction_contract.py` |
| 命令冒烟（extract/onboard/run/baseline 离线全流程） | ✅ 19 例 | 三套 smoke 测试（含 baseline 测量口径对等 2 例） |
| S16 损坏公式降级 + 行内标签白名单 | ✅ 13 例 | `tests/test_s16_and_inline_tags.py` |
| 指纹实测填充 + 抽样三级优先 | ✅ 11 例 | `tests/test_fingerprint_and_sampling.py` |
| 技能壳四脚本（真实交付布局） | ✅ 18 例 | `tests/test_skill_scripts.py` |
| 安装冒烟（wheel 安装 + KaTeX 资产随包 + 渲染端到端） | ✅ | 一次性 venv 已实证并删除 |

> **已声明改动（2026-10-26，B4 化学书实战产出）**：引擎修复两个跨学科缺口后，数学书产物
> 相对已验收 final 出现 **9 行**有意差异，逐行登记在
> `tests/fixtures/parity_delta_allowlist.json`（`rules` 段 5 行 = S16③ 修复 OCR 拆散数字，
> 如 `1.414\;3→1.4143`；`merge` 段 4 行 = HTML 表格 `src=` 引用同步改写，历史为悬空）。
> 除登记项外**任何差异仍判失败**——白名单不是通行证，已用反例验证（未登记改动/行数变化/
> 无白名单册三种情形均正确报错）。下次整册重跑时若刷新 final 基线，清空该文件即可。

### 欠账事项（QA debt）

| 欠账事项 | 状态 | 补做条件 | 备注 |
|---|---|---|---|
| 系统级 run 通测（五册真实数据走 `b2m run` 端到端） | ✅ 2026-10-26 完成 | 纯本地实测：五册六门全绿，markdown/images/双版 HTML 与 final 逐字节 SAME，质检报告数值一致，TOC 逐节一致；缺口 page_map.md 已补（13986c1）。临时产物已按用户裁定全删 | 阶段 A 至此全部完成 |
| 联调（WorkBuddy 技能壳端到端演练） | ✅ 2026-10-26 完成 | 全新工作区 `b2m-ws-c` 化学书整册：convert（抽取 4 块 368 图 + run 七门）→ 壳三脚本 → 覆盖层登记全通；产物与此前 onboard+run 路径逐字节相同。修复壳侧 4 处断点 + 打通 issues 的 C 档闭环；详见台账 D1 |
| 网关实抽联测（extract 真实抽取） | ✅ 2026-10-26 完成 | 试验册 p51-57 真实网关抽取，对历史基线相似度 98.75%，zip 契约完好；详见 [docs/qa-ledger.md](docs/qa-ledger.md) B1 |
| 基准回归实测（`b2m baseline run` 重抽比对） | ✅ 2026-10-26 完成（试验切片 + 整册） | 试验切片：init→run→RC40 三态正确；同版本重抽图片指标有噪声（18↔21）、字符稳定。**整册（化学书 139 页）：4 块重抽全部 `status 一致`**，并修掉两个测量口径缺陷——`_measure` 不带图导致 D10 全量假悬空、run 侧未过 S 规则导致假漂移（详见台账 B5）。指纹仍全 null（网关无 `/version`） |
| 化学书实战（第一本化学教材端到端） | ✅ 2026-10-26 完成 | onboard 网关实抽 139 页 → run 七门全绿，产物齐全（双版 HTML 各 11.5 MB / 315 图 / TOC 268 条）。暴露并修复 3 缺口：merge 表格 `src=` 二次偏移漏改、S16 结构性损坏公式降级通道、md2html 转义白名单放行 sup/sub/u；详见台账 B4 |
| D2 五步交付流程复验（b2m-ws-c） | ✅ 2026-10-27 完成 | precheck（exit 0，探活 200 version=4.0.12）→ verify_delivery（exit 0，gaps=[]，双版 HTML selfcontain 外部引用 0，315 图，issues A0/B0/C2）→ adjudicate_sheet（exit 0，复核表 2 items）→ overlay_scaffold（骨架在案，昨日登记 1 条不重复追加）→ convert（D1 已逐字节验证 convert ≡ onboard+run，不重跑）。指纹欠账已清：collect_fingerprint 实测填 4.0.12（来源 /v1/health），化学书基线已按新口径重建 |

**提醒义务（历史口径，2026-10-27 起改写）**：原纪律为"AI 必须主动提醒系统级 run 通测、
联调与网关侧功能均未实测"。上述实测已于 2026-10-26/27 全部完成（见上表），提醒义务
相应改为：**"内容保真关口只在渲染与结构层；与原书一致性靠人工抽检，E 队列未清零前
产物不得定稿发布"**——即使用户没有问。

## 1. AI Coding 输入清单（设计处 = 本节；冻结点 = 接口规格经用户审定）

开工前 AI 应拿到或生成以下输入；**缺项先问用户，不得自行假设**。

### 1.1 图纸（设计与规格）
- `docs/design.md`（原工作区《教材转换工具化方案》，2026-10-27 归档入库）——架构、交付形态、workspace/路径契约、
  Canonical Extraction 契约（§4.4）、MinerU 后端契约（§4.3）
- `docs/spec-cli.md` 命令集接口规格——已按 v0.2 实现并随 v0.2.0 实测；
  【状态：待用户审定后冻结，冻结前修改须升版本号并经用户确认】
- `deploy/mineru-gateway/`（原工作区根，2026-10-27 归档入库）——网关镜像
  `Dockerfile.pascal` + 补丁三代 `patch3/4/5_mineru_image.py` + 七变体测试
  `test_patch5.py`；配套部署手册 `docs/mineru-selfhost.md`
- `docs/qa-ledger.md`（原工作区《待确定事项台账》）——A/B/C/D 销项记录、
  E 人工复核队列、F 归档记录；交付前必读

### 1.2 原材料（搬迁源码，均在 `../../gzsx-md/`，只读原件）
- `fix_md.py`（1478 行，S1–S20 规则本体）、`md2html.py`、`scan3.py`、`scan_render.py`、
  `scan_md_preview.py`、`postprocess.py`、`rematch_merge.py`、`run_blocks.py`、
  `regen_toc_qa.py`、`run_pipeline.sh`、`render_formulas.js` + `katex/`、`b2m/` 骨架
  ——以上为**原件名**；搬迁后的新名一律按 `docs/conventions.md` 附录 A 对照表

### 1.3 裁判（验收基准）
- `../../gzsx-md/final/<五册>/markdown.md` + 五册字符数基线——**行为保持对账的唯一裁判**
- `run_pipeline.sh` 的六道质量门原始语义
- 1–2 个 blocks zip 样例 + `ledger.json` 样例（抽取适配器契约测试用）

### 1.4 缰绳（纪律约束，违反即返工）
- **命名与编码规范：见 `docs/conventions.md`（v1.0，强制标准）**——文件/目录/代码命名、
  语言策略、stderr 日志纪律、测试约定、Git 约定均以它为准
- **行为保持**：搬迁只许参数化重组，不许"顺手优化"任何规则语义；过关线 = 五册字符数逐字节一致
- 纯 Python 标准库；Python 3.13 + Node.js；中文路径一律 UTF-8 + `pathlib.Path`
- 术语：包 `book2md` / 命令 `b2m` / `baselines`（2026-10-27 更名，旧名 textbook-pipe /
  命令 tbp / 环境变量 TBP_* 已废止，历史记录中出现的旧名即本包）；
  禁止口语比喻词（体检/黄金/钉死/兜底等）进入代码与注释
- 不写改 `../../gzsx-md/` 原件与 `final/` 交付物
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

6. ✅ 网关实测（2026-10-26）：extract 实抽联测（相似度 98.75%）、`baseline run` 重抽比对（试验切片 RC40 三态正确；**整册化学书 139 页 4 块全部一致**；图片指标有 run 间噪声、字符稳定）、MinerU 版本 4.0.12、8/8 权重 sha256、wrapper 端点面，并登机核实 **GPU（2×TITAN X 12GB / 驱动 535.309.01 / basic 档仅占 784 MiB）与完整 docker run 参数（`mineru:pascal` + 官方 `mineru-kit api-server`，零挂载，模型落地 `/root/.mineru/models/`）**——MinerU 侧待确认项全部清零
7. ✅ 化学书实战（2026-10-26）：第一本化学教材端到端转换，onboard（网关实抽 139 页）→ run 七门全绿；修复 merge 表格引用偏移、新增 S16 损坏公式降级、md2html sup/sub/u 白名单（详见台账 B4）

**阶段 C —— 联调（实测全部完成后）**

8. ✅ 技能壳端到端联调（2026-10-26，全新工作区 b2m-ws-c 化学书整册）：convert 七门全 PASS，产物与此前 onboard+run 路径**逐字节相同**（md/双版 HTML/images 315）；实测修复壳侧 4 处断点（precheck 端点解析+health 探活、verify_delivery 真实 HTML 布局、C 档复核表数据源）并打通 issues 的 C 档闭环（详见台账 D1）
9. ✅ 全链路验收收尾、销账、打 v0.2.0（2026-10-27）：D2 五步交付复验全通；回归 67 例 + 5 套对账全绿（render 对账 827s，KaTeX 0 错误）；指纹欠账清零（/v1/health 实测 4.0.12）；baseline 抽样改按块自动覆盖；CHANGELOG + tag v0.2.0。**至此路线图全部完成，遗留仅 E 人工复核队列**
