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

### 6.1 `tbp config` — 用户配置管理

**用途**：查看/设置 `~/.tbp/config.json`（§4.2.4 第 3 优先级的个人默认值）。
**调用方**：安装后一次性设置（人）；技能壳 precheck 脚本（AI）。

```
tbp config get [key]        # 查看全部或单项
tbp config set <key> <val>  # 写入单项
tbp config path             # 显示配置文件绝对路径
```

| key | 取值 | 说明 |
|---|---|---|
| `workspace` | 绝对路径 | 默认工作区（四层解析的第 3 层） |
| `backend` | `mineru-remote` \| `local-mineru` \| `manual` | 抽取后端，对应 extractors/ 下的适配器 |
| `subjects` | 逗号分隔科目 id | 已接入科目，如 `math-renjiao-a,chem-renjiao` |

**处理流程**：`set` 时校验 key 合法 → `workspace` 需可创建（试建目录）→ 写回 JSON
（未提及的键原样保留）；`get` 时直接读。配置文件损坏 → 备份为 `config.json.bak-<时间戳>`
并按空配置继续（stderr 警告），不崩溃。

**stdout 示例**：

```json
{"cmd":"config","ok":true,"exit_code":0,
 "config":{"workspace":"D:/教材工作区","backend":"mineru-remote",
           "subjects":["math-renjiao-a"]},
 "config_path":"C:/Users/xiesh/.tbp/config.json"}
```

**错误**：未知 key → 20；`set workspace` 路径不可创建 → 20。

---

### 6.2 issues.json schema（`onboard` / `scan` 的核心产物）

```jsonc
{
  "schema": "tbp.issues/v1",
  "book": "化学必修第一册",
  "generated_at": "2026-10-24T23:00:00+08:00",
  "counts": { "A": 3, "B": 23, "C": 4 },
  "items": [{
    "id": "I-0007",          // 稳定 id：同一书内重扫不漂移（按 探测器+行号 定序生成）
    "tier": "C",             // A=形式错误(引擎可修) B=学科通病(规则包批量修) C=内容存疑(人工裁定)
    "detector": "D3",        // 探测器编号（scan3 D1–D10）或修复规则名
    "line": 1203,            // md 行号（对 extract 源或 out md，见 --source）
    "excerpt": "……$\\mathcal{P}$……",          // 命中上下文（≤60 字符）
    "suggestion": "花体 P → 小写 p（出处：人教A版官网教学设计）"
  }]
}
```

字段约定：`tier` 枚举固定 A/B/C；`excerpt` 截断不换行；`suggestion` 可为 null
（A 档由引擎自动修复，无需建议）。

### 6.3 provenance.json schema（每次抽取生成，随产物交付）

```jsonc
{
  "schema": "tbp.provenance/v1",
  "source_pdf": {"name": "化学必修第一册.pdf", "sha256": "…"},   // PDF 是唯一事实源，指纹必须含哈希
  "adapter": "mineru-remote",
  "gateway": {"endpoint": "http://<网关地址>:8000", "tier": "basic"},
  "backend": {
    "gateway_version": null,     // 网关未上报 → 显式 null（缺口可见，禁止填占位假值）
    "mineru_version": null,      // 同上；上报后为字符串
    "model_hashes": {},          // layout/OCR/公式/表格 权重哈希（docs/backend.md 契约）
    "patched_files": [{"path": "mineru/model/ocr/image.py",
                        "patch_id": "img-crop-min1", "present": true}]  // §4.3.6(e) 补丁在场校验结果
  },
  "contract": "tbpipe.extraction/v1",
  "extracted_at": "2026-10-24T23:00:00+08:00"
}
```

### 6.4 `tbp onboard` — 新书接入（人机协作回路入口）

**用途**：一本新书的第一条命令。建工作区 → 抽取 → 全量基线扫描 → 产出 A/B/C 问题清单，
**不产出 HTML**（裁定完成后由 `run` 产出）。**调用方**：技能壳（onboard 后进入 C 档
裁定循环）；人（想先看体检结果再决定怎么修）。

```
tbp onboard --subject chem-renjiao --pdf "D:/教材/化学必修第一册.pdf"
            [--workspace D:/教材工作区] [--page-range 7-46] [--force]
```

| 参数 | 必选 | 默认 | 说明 |
|---|---|---|---|
| `--subject` | ✅ | — | 科目 id，须存在 `textbook_pipe/configs/<id>.json` |
| `--pdf` | ✅ | — | 教材 PDF 路径 |
| `--workspace` | ❌ | 四层解析 | 覆盖工作区位置 |
| `--page-range` | ❌ | 全书 | 物理页范围 `N-M`，试转换/抽查用 |
| `--force` | ❌ | off | 忽略 ledger 已完成块，强制重抽 |

**处理流程**：① 解析 workspace（四层）并建目录树（§4 布局）→ ② 加载科目配置，
**不存在则生成配置模板后以退出码 20 结束**（stderr 指引"编辑 configs/chem-renjiao.json 后重跑"，
模板含 TOC 章目正则占位与规则包引用骨架）→ ③ 网关连通性 + 版本指纹 + 补丁在场预检 →
④ 抽取（ledger 续跑）→ Canonical Extraction v1 归一化 → ⑤ 全量基线扫描
（探测器矩阵 + 渲染验证栈）→ ⑥ 写 `issues.json` + `provenance.json`。

**stdout 示例**：

```json
{"cmd":"onboard","ok":true,"exit_code":0,
 "workspace":"D:/教材工作区","book":"化学必修第一册",
 "out_dir":"D:/教材工作区/out/化学必修第一册",
 "artifacts":{"issues":"D:/教材工作区/out/化学必修第一册/issues.json",
              "provenance":"D:/教材工作区/out/化学必修第一册/provenance.json"},
 "warnings":["C 档 4 条待人工裁定，见 issues.json items[tier=C]"],
 "elapsed_sec":1023.7,"error":null}
```

**错误场景**：

| 条件 | 退出码 | stderr 提示要点 |
|---|---|---|
| PDF 文件不存在 | 50 | 给出传入路径 |
| 科目配置不存在 | 20 | 已生成模板 + 模板路径 + 需编辑的字段 |
| 网关不可达 / HTTP 错误 / 超时 | 30 | 端点、HTTP 状态、重试建议 |
| zip 布局 / middle_json 字段 / 指纹不符 / 补丁缺失 | 40 | 哪个契约点违约（对应 docs/backend.md 条目） |
| ledger 损坏 | 40 | 建议删 blocks/<book>/ 重抽（ledger 可再生，产物不受影响） |

发现 C 档**不是错误**：exit 0，`warnings` 提示条数——裁定是人机循环的下一步，不是故障。

### 6.5 `tbp extract` — 仅抽取（分步调试用）

**用途**：只做"PDF → Canonical Extraction"，不扫描不修复。**调用方**：调试适配器、
重跑某页段、基准回归的底层。

```
tbp extract --book 化学必修第一册 --pdf "D:/教材/化学必修第一册.pdf" [--force] [--page-range N-M]
```

| 参数 | 必选 | 说明 |
|---|---|---|
| `--book` | ✅ | 书 id（=PDF 文件名去扩展名；与 --pdf 不一致时以文件名为准并告警） |
| `--pdf` | ✅ | 源 PDF |
| `--force` | ❌ | 忽略已完成块重跑 |
| `--page-range` | ❌ | 物理页范围 |

**处理流程**：① ledger 检查未完成块 → ② 按块提交网关（`page_range`、`tier`、
`response_format=zip`、超时与 403 退避策略继承 run_blocks.py）→ ③ zip 解包 →
④ **归一化**：块完成序 → 物理页序重排、图片物理页重命名、数学方言 coerce、
`middle_json` → 页码映射 → ⑤ 组装 Canonical Extraction v1（方案 §4.4.2）→
⑥ schema 校验（页数完整、图片引用存在、数学定界符配对）→ ⑦ 写
`extract/<book>/{contract.json, markdown.md, images/, native/}`。

**产物 `contract.json`**：即方案 §4.4.2 的合约文件（schema/tool 指纹/pages/images/markdown/blocks）。
校验失败 → 退出码 40，**不写 contract.json**（半成品契约不存在）。

### 6.6 `tbp run` — 阶段 B 全流水线（六道质量门）

**用途**：以已抽取内容为输入，执行修复→渲染→检测→报告全链路，产出全部交付物。
**调用方**：技能壳（裁定完成后）；人；CI。

```
tbp run --book 化学必修第一册 --subject chem-renjiao
        [--gates all] [--workspace D:/教材工作区]
```

| 参数 | 必选 | 默认 | 说明 |
|---|---|---|---|
| `--book` | ✅ | — | 书 id，须存在 `extract/<book>/contract.json` |
| `--subject` | ✅ | — | 科目配置（决定规则包、探测器组合、TOC 正则、知识库特性开关） |
| `--gates` | ❌ | `all` | 逗号分隔子集：`deps,fix,html,selfcontain,render,preview,scan3,toc`（调试单关用） |

**质量门序列**（= run_pipeline.sh 六关语义，行为保持）：

| # | 门 | 内容 | 失败行为 |
|---|---|---|---|
| 1 | deps | Node.js / katex 资产 / 输入契约存在性 | 20 |
| 2 | fix | S1–S20 + packs/<学科> + overlays/<书> 修复；公式双表示（知识库线性 alt） | 10 |
| 3 | html | 双版本 HTML：KaTeX 预渲染（0 错误要求）+ 20 字体内联 | 10 |
| 4 | selfcontain | 自包含校验：0 外部引用、0 裸 LaTeX | 10 |
| 5 | render+preview | 渲染完整性（游离 $$/奇数 $）+ texmath dollars 语义 | 10 |
| 6 | scan3+toc | D1–D10 探测器（7 通用 + 学科专用）+ TOC/质检报告重生 | 10 |

**失败不落盘的实现语义**：全部产物先写 `<out>/<book>.staging/`，六门全绿后原子
rename 到 `<out>/<book>/`——任何失败时上一版产物完好无损。

**规则来源优先级**：`overlays/<book>`（书级，最高）> `packs/<subject>`（学科级）>
引擎内置 S 规则（通用级）。同 pattern 冲突时高优先级生效并在 `qa_gate.log` 记录覆盖关系。

**stdout artifacts**（全绿时）：`markdown` / `html` / `kb_html` / `toc` / `qa_report` /
`issues` / `qa_gate_log` 七项绝对路径。

**错误**：`extract/<book>/contract.json` 缺失 → 50；任一门失败 → 10，
`error.gate` 字段指明关卡、`qa_gate.log` 留全程记录。

### 6.7 `tbp convert` — 一条命令全流程（无人值守）

**用途**："PDF 进、全套产物出"的最终体验。CI / 定时任务 / 不想分步的人。
**语义 = `extract` + `run` 的原子组合**，C 档内容按引擎默认处理。

```
tbp convert --pdf "D:/教材/化学必修第一册.pdf" --subject chem-renjiao
```

| 参数 | 必选 | 说明 |
|---|---|---|
| `--pdf` / `--subject` / `--workspace` | 同上 | 同 6.4/6.6 |

**C 档默认处理策略**：引擎按现有规则处理全部内容（宁可保留原文形态也不臆改），
所有存疑条目**无一遗漏列入 `质检报告.md` 复核队列**并计入 issues.json——未裁定不影响
交付，但交付物自带"哪里存疑"的完整清单。这是 `convert` 与 `onboard→裁定→run` 的
唯一实质差异。

**与 `onboard`+`run` 的对比**：

| | `convert` | `onboard` → `run` |
|---|---|---|
| 产物 | 全套（一次到位） | issues 先行，裁定后才有 HTML |
| C 档 | 默认处理 + 复核队列 | 人工裁定后规则生效 |
| 适用 | 批量/试转换/CI | 首本精修书、质量要求高的书 |

### 6.8 `tbp scan` — 只读体检

**用途**：不改任何转换产物，仅跑探测器矩阵 + 渲染验证，刷新 issues.json。
**调用方**：规则修改后的回归自查；技能壳刷新裁定清单。

```
tbp scan --book 化学必修第一册 --subject chem-renjiao [--source out|extract]
```

| 参数 | 必选 | 默认 | 说明 |
|---|---|---|---|
| `--source` | ❌ | `out` | `out`=扫描修复终版 md；`extract`=扫描抽取原始 md（测规则覆盖率） |

**语义**：`--source out` 时五册产物应 D 类探测器全零（回归过关线）；
`--source extract` 时输出的是"规则尚未生效的原始错识量"，用于评估规则包完备度。
issues.json 按 `detector+line` 重新生成，保证 id 稳定可比。

### 6.9 `tbp report` — 重生目录与质检报告

**用途**：只读 `out/<book>/markdown.md`，重建 `TOC.md` 与 `质检报告.md`
（语义 = regen_toc_qa.py，行为保持）。md 本体永不改动。

```
tbp report --book 化学必修第一册        # 单册
tbp report --all                       # workspace 内全部已转换书
```

### 6.10 `tbp baseline` — 基准回归（防后端静默漂移）

**用途**：方案 §4.3.3/§4.3.6 版本指纹机制的执行入口。固定"已知良好"页样本，
后端升级/换适配器后重抽比对，超阈值即拦截。

```
tbp baseline init --subject math-renjiao-a     # 首次：从已验收书抽页入库 + 记录基线
tbp baseline run [--subject <id>]              # 例行：重抽 → 同页扫描 → 指标比对
```

**init 规则**：每本已验收书抽固定页集（默认每册首/中/尾各 2 页，可经科目配置
`baseline.pages` 覆盖）；原始页图与抽取产物入 `baselines/`；记录基线指标。

**比对指标与阈值**：

| 指标 | 阈值（默认） | 超限行为 |
|---|---|---|
| D1–D10 各探测器命中数 | 允许 ±0 | stderr 详情 + 退出码 40 |
| KaTeX 错误数 | 允许 ±0 | 同上 |
| 基准页字符数 | 允许 ±0.5% | 同上 |

**run 结果三态**：一致（exit 0，"后端指纹未漂移"）；**漂移（exit 40，列出各指标差异
+ 当前 provenance vs 基线 provenance 对比）**；基线不存在（exit 20，提示先 init）。

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
