# textbook-pipe 命令集接口规格（spec-cli）

> 版本：v0.1 草案 · 2026-10-24 · 状态：**待用户审定，审定后冻结**（AGENT.md §1.1）
> 本文件是核心包 CLI 与 WorkBuddy 技能壳共同的接口地基。实现以本文件为准；
> 修改本文件必须经用户确认并升版本号。

---

## 1. 范围

定义 `tbp` 命令行工具的全部命令、参数、输出契约、退出码与数据文件 schema。
设计目标按优先级：

1. **stdout 恒为合法 JSON**——技能壳与 CI 只需解析 stdout，零脆弱文本匹配
2. **非交互**——任何命令不得等待键盘输入（CI/无人值守前提）
3. **幂等可续跑**——同一命令重复执行安全；抽取按 ledger 断点续跑
4. **行为保持**——阶段 B 语义与 gzsx-md 六道质量门流水线完全一致，仅做参数化重组

## 2. 全局约定

| 约定 | 内容 |
|---|---|
| 流分离 | **stdout = 单个 JSON 结果对象；stderr = 人类可读进度/日志**。技能壳只解析 stdout，人只看 stderr |
| 编码 | 全链路 UTF-8；路径一律 `pathlib.Path`（中文工作区路径为常态） |
| 非交互 | 不提供任何交互提示；需要决策的场景输出到 issues.json 交给调用方（人/技能壳）裁决 |
| 路径解析 | workspace 按 §4.2.4 四层优先级：`--workspace` > 环境变量 `TBP_WORKSPACE` > `~/.tbp/config.json` > 当前目录 `./out` |
| 命令别名 | `tbp` 为主名，`tbpipe` 为过渡别名，行为完全一致 |
| 确定性 | 除时间戳与指纹外，同输入同输出；规则引擎无随机性 |

## 3. 退出码

| 码 | 语义 | 典型来源 |
|---|---|---|
| 0 | 成功（含"有 C 档待裁定"这类非致命情况——用 JSON 字段表达，不用退出码） | 全部命令 |
| 10 | 质量门未通过（带病输出不存在：失败即无产物更新） | `run` / `convert` |
| 20 | 用法/配置错误（参数缺失、科目配置不存在、workspace 不可写） | 全部命令 |
| 30 | 抽取后端错误（网关不可达、HTTP 4xx/5xx、超时） | `extract` / `onboard` / `convert` |
| 40 | 契约违约（zip 布局/middle_json 字段/Canonical Extraction schema/版本指纹不符） | 涉及抽取的命令 |
| 50 | 输入文件不存在（PDF/md/图缺失） | 全部命令 |

## 4. 工作区与产物布局

```
<workspace>/
├── out/<book>/                  ← 产物（book = PDF 文件名去扩展名，允许中文）
│   ├── markdown.md              修复终版 md（数学方言 $...$ / $$...$$）
│   ├── images/                  物理页命名图片
│   ├── html/<book>.html         阅读版单体 HTML（KaTeX 预渲染 + 字体内联）
│   ├── kb_html/<book>.html      知识库版单体 HTML
│   ├── TOC.md / 质检报告.md      目录与人工复核队列
│   ├── issues.json              A/B/C 三级问题清单（schema 见 §6.2）
│   ├── provenance.json          版本指纹（schema 见 §6.3）
│   └── qa_gate.log              六道质量门逐关记录
├── extract/<book>/              抽取中间产物（Canonical Extraction v1，见方案 §4.4.2）
│   ├── contract.json            canonical 契约文件
│   ├── markdown.md / images/    适配器输出的规范化 md 与图片
│   └── native/                  适配器原始输出（zip 解包，供追溯）
├── overlays/<book>/             该书 C 档裁定规则（用户数据，人工/技能壳维护）
├── blocks/<book>/               网关分块缓存（断点续跑）
├── ledger.json                  抽取账本 + 版本指纹
└── baselines-local/             本地基准回归比对结果
```

## 5. 通用 JSON 结果信封

所有命令的 stdout 均为：

```jsonc
{
  "cmd": "run",                    // 命令名
  "ok": true,                      // 退出码 0 与之等价
  "exit_code": 0,
  "workspace": "D:/教材工作区",     // 实际解析后的绝对路径
  "book": "化学必修第一册",
  "out_dir": "D:/教材工作区/out/化学必修第一册",
  "artifacts": {                   // 本命令产出/更新的文件（绝对路径）
    "markdown": "D:/教材工作区/out/化学必修第一册/markdown.md"
  },
  "warnings": [],                  // 非致命事项（如 C 档待裁定条数）
  "elapsed_sec": 612.3,
  "error": null                    // 失败时为 {"code":10, "gate":"kaTeX", "message":"..."}
}
```

## 6. 命令详规

### 6.1 `tbp config` — 查看/设置用户配置

```
tbp config get [key] | set <key> <value> | path
```

| 参数 | 说明 |
|---|---|
| `get [key]` | 显示 `~/.tbp/config.json` 全部或单项（stdout JSON） |
| `set <key> <value>` | 写入个人默认值（workspace / backend / subjects） |
| `path` | 输出配置文件路径 |

### 6.2 `tbp issues` schema（`onboard`/`scan` 产出）

```jsonc
{
  "schema": "tbp.issues/v1",
  "book": "化学必修第一册",
  "generated_at": "2026-10-24T23:00:00+08:00",
  "counts": { "A": 3, "B": 23, "C": 4 },
  "items": [
    { "id": "I-0007", "tier": "C",              // A=形式错误(引擎可修) B=学科通病(规则包) C=内容存疑(人工)
      "detector": "D3",                          // 探测器编号或规则名
      "line": 1203, "excerpt": "……$\\mathcal{P}$……",
      "suggestion": "花体 P → 小写 p（出处：人教A版官网教学设计）" }
  ]
}
```

### 6.3 `tbp provenance` schema（每次抽取生成，随产物交付）

```jsonc
{
  "schema": "tbp.provenance/v1",
  "source_pdf": {"name": "化学必修第一册.pdf", "sha256": "…"},
  "adapter": "mineru-remote",
  "gateway": {"endpoint": "http://<网关地址>:8000", "tier": "basic"},
  "backend": {"gateway_version": null, "mineru_version": null,   // 网关未上报则为 null——缺口本身要可见
              "model_hashes": {}, "patched_files": []},
  "contract": "tbpipe.extraction/v1",
  "extracted_at": "…"
}
```

### 6.4 `tbp onboard` — 新书接入（人机协作回路的入口）

```
tbp onboard --subject <id> --pdf <path> [--workspace <path>] [--page-range N-M]
```

- 动作：建工作区目录 → 科目配置不存在则生成模板并**报 20 退出** → 调抽取（续跑）→
  全量基线扫描（探测器矩阵 + 渲染验证）→ 写 `out/<book>/issues.json` + `provenance.json`
- 产出：`extract/`、`issues.json`、`provenance.json`；**不产出 HTML**（裁定后再 run）
- 调用方（技能壳）拿到 issues.json 后进入 C 档人机裁定循环

### 6.5 `tbp extract` — 仅抽取

```
tbp extract --book <名> --pdf <path> [--force] [--page-range N-M]
```

- 动作：PdfExtractor 适配器执行抽取 → 归一化为 Canonical Extraction v1 →
  写 `extract/<book>/contract.json`；ledger 断点续跑；**契约校验失败 → 退出码 40**
- `--force` 忽略已完成块重跑

### 6.6 `tbp run` — 阶段 B 全流水线（质量门）

```
tbp run --book <名> --subject <id> [--gates all|render|selfcontain|preview|scan3|toc] 
```

- 动作：以 `extract/<book>/` 为输入 → S1–S20 修复（+ packs + overlays 规则）→
  公式双表示（知识库 alt）→ 双版本 HTML（KaTeX 预渲染+字体内联+自包含校验）→
  三套检测 → TOC/质检报告 → 全部产物写 `out/<book>/`
- 任一质量门失败：**退出码 10，产物目录保持上一版状态**（失败不落盘）
- 输入缺失 `extract/<book>/contract.json` → 退出码 50

### 6.7 `tbp convert` — 一条命令全流程（无人值守）

```
tbp convert --pdf <path> --subject <id> [--workspace <path>]
```

- 等价 `onboard` 去掉交互意图 + `run`：抽取 → 流水线 → 全套产物
- C 档内容按引擎默认处理并**全部列入质检报告复核队列**——未裁定不影响交付，但必在
  质检报告中可见
- CI/定时任务与"懒得逐步来"的场景用它；人机协作精修用 `onboard → (裁定) → run`

### 6.8 `tbp scan` — 只读体检（不改任何文件）

```
tbp scan --book <名> [--subject <id>] [--source out|extract]
```

- 动作：对现有产物或抽取物跑探测器矩阵 + 渲染验证 → 更新 `issues.json`
- 用途：规则修改后的回归自查；技能壳的裁定清单刷新

### 6.9 `tbp report` — 重生 TOC 与质检报告

```
tbp report --book <名> | --all
```

- 等价现有 regen_toc_qa.py 语义：只读 md，重建 `TOC.md` / `质检报告.md`

### 6.10 `tbp baseline` — 基准回归（防后端漂移）

```
tbp baseline init --subject <id>     # 从五册/已验收书抽取固定页入 baselines/ + 记录基线指标
tbp baseline run                     # 重抽基准页 → 跑探测器矩阵 → 与基线比对 → 超阈值告警(退出码 40)
```

- 指标：D1–D10 命中数、KaTeX 错误数、字符数（基准页级）
- 这是方案 §4.3.3/§4.3.6 版本指纹机制的执行入口

## 7. 依赖与预检

| 依赖 | 预检时机 | 缺失行为 |
|---|---|---|
| Python ≥ 3.13（包自身） | 安装时 | pip 拒绝 |
| Node.js（KaTeX 预渲染） | `run`/`convert` 启动前 | 退出码 20，stderr 指引 |
| katex/ 资产随包 | 同上 | 退出码 20 |
| MinerU 网关连通性 | `extract`/`onboard`/`convert` 启动前 | 退出码 30 |
| 网关版本指纹 ∈ 契约允许集合 | 同上；`backend.patched_files` 补丁在场校验 | 退出码 40 |

## 8. 冻结与变更流程

1. 用户审定本文件 → 状态改为 **v1.0 冻结**，写入 AGENT.md §1.1 的确定项
2. 此后任何接口变更：升 `v1.x`，兼容性变更（新增可选参数/字段）可并入；
   破坏性变更必须升 `v2` 且技能壳同步改版
3. 实现与本文不符 = 缺陷；以本文为准
