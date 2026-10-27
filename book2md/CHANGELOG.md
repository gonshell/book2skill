# 更新日志（Changelog）

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；
版本号遵循语义化版本（SemVer）。验收结论与欠账台账见 [AGENT.md](AGENT.md)。

## [0.2.0] - 2026-10-27

首个全实测锚点版本：五册系统级通测 + 网关实抽/基准回归实测 + 化学书（首本非数学
教材）端到端 + 技能壳联调。详见 AGENT.md 验收表与工作区《待确定事项台账.md》。

### Added
- 系统级 `tbp run` 通测（阶段 A-5）：五册端到端六门全绿，markdown / images /
  双版 HTML 与已验收 final 逐字节一致；run 补生 page_map.md（13986c1）
- 技能壳（P2 / 阶段 C）：`SKILL.md` + 四脚本（precheck / verify_delivery /
  adjudicate_sheet / overlay_scaffold），stdout JSON 信封，退出码 0/10/20/30/40/50；
  `tbp convert` 与 `onboard+run` 产物逐字节相同（链路确定性实证）
- S16 结构性损坏公式降级通道：嵌套 textcircled / 空 array 无限嵌套等不可还原形态
  → 占位 + `broken_formulas.tsv` 人工补录清单（C 档）
- baseline 测量口径对等：`_measure` 按实际引用带图（杜绝 D10/缺图假阳性）；
  run 侧重抽产物过同一套 S1–S20 再比对（杜绝规则可修复形态假漂移）
- baseline init 抽样三级优先：`baseline.pages` 显式页列表 > `baseline.blocks:"all"`
  （按账本抽取块全覆盖，免手填页码）> 默认首/中/尾各 2 页
- `collect_fingerprint` 实测填充：版本取 GET `/v1/health`（官方 mineru-kit 无
  `/version`，实测 4.0.12）；未配置端点/探活失败仍一律 None（纪律不变）
- 测试扩至 **67 例** + 5 套行为保持对账：S16/行内标签 13 例、baseline 测量口径 2 例、
  指纹与抽样 11 例、技能壳脚本用例（真实交付布局）

### Changed
- merge：HTML 表格 `src="images/page_N_"` 引用随块偏移同步改写（此前只改 markdown
  引用；化学书 32 引用 0 缺失）
- render：`prose_inline` 转义白名单放行原生 `<sup>/<sub>/<u>`（正文与表格单元格
  两路径；带属性标签与 `$a<b$` 仍转义）——修复化学书 74 处上下标被打露
- rules：S16 附带安全修复（`\;` 拆散数字如 `1.414\;3→1.4143`、裸 `^` 无基底）；
  隔离目标同名冲突改 `-dup` 唯一命名
- `detectors.run` 增返 `details`（命中串含行号）；`_issues.collect` 填 line/excerpt
  并读 `broken_formulas.tsv` 生成 C 档条目（复核表不再空表）
- 行为保持对账引入**已声明改动白名单**：B4 引擎修复使数学书产物相对历史 final 有
  9 行有意差异（rules 5 行 + merge 4 行），逐行登记
  `tests/fixtures/parity_delta_allowlist.json`；除登记项外任何差异仍判失败

### Fixed
- 技能壳四断点（联调实测）：precheck 端点误传参恒判未配置 + 探活改 `/v1/health`；
  verify_delivery HTML 路径对齐真实布局 `out/<book>/html|kb_html/`；C 档复核表
  数据源断链（`broken_formulas.tsv` 跨行原串按行首序号切分）
- `pyproject.toml` version 0.0.1 → 0.2.0（v0.1.0 打 tag 时漏改）

## [未发布]

### Added
- CLI 七命令全部接线（`docs/spec-cli.md` v0.2）：
  `config` / `extract` / `onboard` / `run` / `convert` / `report` / `scan` / `baseline`
- `tbp run` 质量门编排：deps → fix → html → selfcontain → render → preview →
  scan3+toc；staging 原子落盘（失败不晋升，旧版挪 `.prev-<时间戳>`），
  `qa_gate.log` 逐关记录随册
- `tbp baseline` 基准回归：`init` 从已验收册按页界标记抽样计量入库；
  `run` 走网关重抽同页比对（字符 ±0.5% / 探测器 ±0 / KaTeX ±0 / 版本指纹）
- 抽取契约真实样例入库（`tests/fixtures/`，MinerU 网关原始 zip + 裁剪账本）
- `run_tests.sh` 一键回归（契约+冒烟不依赖历史产物；四套行为保持对账需
  `TBP_PARITY_SOURCE`）

### Changed
- JSON 信封新增可选顶层 `extra` 合并字段（spec §8 兼容变更，v0.1 → v0.2）

### Fixed
- `pyproject.toml` 补 `package-data`：此前 wheel 安装后 `assets/katex`
  （20 字体 + css + 渲染脚本）不随包分发，非源码安装方式渲染必然失败
  （安装冒烟排雷项，已实证修复）
- 页界标记剥离正则漏 `===== -->` 空格变体（基线比对假漂移根因）
- 搬迁缺陷修复（对账/冒烟测试抓获）：
  - `integrity.py` / `texmath.py` 的 `books` 参数被硬编码白名单覆盖，
    非默认册名被静默丢弃
  - `extract_pdf` 缺 `merge_all` 导入、合并产物误写 `out/`（spec §4 规定
    `extract/<book>/`）、`process_block` 传参路径重复拼接
  - `texmath.py` 空 `print()` 误写 stdout（JSON 信封污染）

## [0.1.0] - 2026-10-25

P1 核心包首个锚点版本：五册行为保持搬迁完成 + 七命令接线 + 验收对账全绿。

### Added
- 引擎模块（自 gzsx-md 行为保持搬迁，只参数化 IO 不改规则语义）：
  - `engine/rules.py`（← fix_md.py，S1–S20）+ `engine/reporting.py`（← postprocess.py）
  - `engine/render.py`（← md2html.py）+ `assets/katex/`（0.16.11 随包快照）
  - `engine/inspectors/`：detectors（D1–D10）/ integrity / texmath
  - `extractors/`：mineru.py（网关适配 + 抽取编排）/ merge.py（页序重合并）
- CLI 骨架与退出码体系（0 / 10 质量门 / 20 配置 / 30 网关 / 40 契约 / 50 缺失），
  JSON 信封 stdout 单出口
- 文档四件：spec-cli（接口规格）/ install（版本锁定）/ backend（网关契约）/
  conventions（命名与编码规范）
- 测试八套：抽取契约 8 例 + 冒烟三套 17 例 + 行为保持对账四套
  （五册 md / 10 HTML / 探测报告 / 合并输出逐字节，30 例全绿）
- 安装冒烟：一次性 venv + pip 安装验证（入口 / 资产随包 / 渲染端到端）

### 验收基线（v0.1.0 时点）
- 行为保持：五册修复产物逐字节一致；10 个 HTML 逐字节一致；
  3 份探测报告全文本一致；5 册合并输出一致
- 安装路径：wheel 安装 + KaTeX 资产随包定位 + 离线渲染端到端通过
- 未覆盖（挂账）：网关实抽联测、baseline run 重抽实测、MinerU 版本确定
  ——见 AGENT.md 欠账台账
