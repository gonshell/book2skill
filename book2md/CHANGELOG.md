# 更新日志（Changelog）

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；
版本号遵循语义化版本（SemVer）。验收结论与欠账台账见 [AGENT.md](AGENT.md)。

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
