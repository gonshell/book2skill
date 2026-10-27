# arch.md — book2qa 实现架构设计

> 定位：讲清**谁干活、谁不许干活、失败怎么办、怎么测**。
> 数据契约见 [graph-spec.md](graph-spec.md)，产品设计见 [design.md](design.md)，
> 命令逐条规格见 `spec-cli.md`（待写，体例对齐 book2md）。
>
> 状态：**草案，待审**（2026-10-27）。§9 有三处必须由人裁的冲突。

---

## 1. 分层（沿用 book2md 已跑通的范式）

| 层 | 目录 | 只做 | 禁止 |
|---|---|---|---|
| 入口 | `book2qa/cli.py` | 参数解析、分发到命令函数 | 任何业务逻辑 |
| 命令 | `book2qa/commands/` | 编排：读配置 → 调 core → 写产物 → 出信封 | 自己实现算法 |
| 核心 | `book2qa/*.py`（structure / candidate / graph / …） | 纯计算，输入数据、输出数据 | 读写文件、打印、读环境变量 |
| 适配 | `book2qa/source.py` | 唯一碰 book2md 产物的地方 | 解析标题、切知识点 |

**三条铁律**：

1. **core 不 import commands**，依赖方向单向（§3）。
2. **`structure.py` 是纯函数**：`(markdown_text, page_marks) -> SectionTree`，零文件 IO。
   换来的是 20 条标题样本的测试不依赖 fixture 文件，直接喂字符串。
3. **只读 book2md 的产物文件，绝不 import book2md 的代码**。
   跨模块走文件产物是 `book2skill/README.md` 的约定 2，这里不破例。

## 2. 目录与模块职责

```
book2qa/
├── pyproject.toml            name=book2qa, CLI=b2q
├── run_tests.sh              一键回归
├── AGENT.md                  维护者须知（同 book2md）
├── README.md
├── docs/{design,graph-spec,arch,spec-cli,quality}.md
├── book2qa/
│   ├── cli.py                入口分发
│   ├── exit_codes.py         0/10/20/40/50（沿用 book2md 语义）
│   ├── paths.py              workspace 解析：--workspace > B2Q_WORKSPACE > ~/.book2qa/config.json > ./
│   ├── envelope.py           stdout JSON 信封（与 book2md 同形，技能壳可复用解析）
│   ├── source.py             读 markdown.md / page_map.md / images/，切页段
│   ├── structure.py          ★标题四分类 + 章名续行 + OCR 归并（纯函数）
│   ├── extract/
│   │   ├── exercises.py      ★题目抽取（题号 / 题干 / 跨页）
│   │   ├── figures.py        图号 ↔ 文件名映射
│   │   └── formulas.py       latex 抽取 + plain 文本化（graph-spec §6）
│   ├── candidate.py          ★按节切知识点候选 + 粒度报警（graph-spec §1.2）
│   ├── graph.py              质量闸 + 序列化 graph.jsonl（graph-spec §3/§7）
│   ├── report.py             build_report.md 生成（所有降级的唯一出口）
│   └── commands/
│       ├── build.py          四段 stage 编排
│       ├── config.py         配置读写
│       └──（ask/learn/drill/review 在 S2–S5 阶段加）
└── tests/
```

打 ★ 的三个模块是本模块的主要工作量，其余是装配。

## 3. 依赖方向

```
cli.py
  └─▶ commands/build.py
        ├─▶ source.py ──────▶ 文件系统（book2md 产物，只读）
        ├─▶ structure.py ───▶ 无依赖（纯函数）
        ├─▶ extract/*.py ───▶ 无依赖（纯函数）
        ├─▶ candidate.py ───▶ structure + extract 的数据结构
        ├─▶ graph.py ───────▶ candidate 的数据结构
        └─▶ report.py ◀────── 各段上报的 Issue 列表
```

`report.py` 只被写、不被读：任何模块产生"拿不准"的东西都往 `Issue` 列表里塞，
由 `build` 统一落成 `build_report.md`。**不许任何模块自己 print 警告**——
那会散落在 stderr 里，人看不见第二遍。

## 4. 关键数据结构

全部 `frozen=True`（不可变 + 可比较，重跑同输入必得同结构，便于断言）。

```python
@dataclass(frozen=True)
class Heading:
    line_no: int
    raw: str                                   # '## 3.2函数的基本性质' 原文
    kind: Literal["chapter","section","subsection","block"]
    number: str | None                         # "3.2" / "5"（章取"第五章"→5）
    title: str                                 # 归并后的干净标题

@dataclass(frozen=True)
class Section:
    heading: Heading
    start_line: int
    end_line: int                              # 半开区间 [start, end)
    physical_pages: tuple[int, int]            # 必填：由页界标记算出
    book_pages: tuple[int, int] | None         # 教材页；page_map 缺行则 None（见 §9.1）
    children: tuple["Section", ...]
    blocks: tuple["Block", ...]

@dataclass(frozen=True)
class Block:                                   # 提问块：练习/思考/探究/…
    kind: str
    start_line: int
    end_line: int
    items: tuple["Exercise", ...]

@dataclass(frozen=True)
class Exercise:
    label: str                                 # "练习 3" / "习题 2.1 第 5 题"
    page: int | None
    quote: str                                 # 题干前 40 字，重定位唯一依据
    spans_pages: bool                          # 题干是否跨页

@dataclass(frozen=True)
class FormulaPair:
    latex: str
    plain: str
    degraded: bool                             # plain 未按规则表转换（§6 降级）
    line_no: int

@dataclass(frozen=True)
class Issue:                                   # 所有降级的统一载体
    level: Literal["warn","todo"]               # todo = 必须人看
    code: str                                   # 稳定码，如 "pages_missing"
    where: str                                  # 行号或节点 id
    detail: str
```

`Issue.code` 必须稳定（用于统计与测试断言），不得写成自然语言句子。

## 5. build 四段的数据接力

| 段 | 入口 | 读 | 写 | 人介入 |
|---|---|---|---|---|
| `structure` | `structure.build_tree()` | markdown.md + page_marks | `structure.jsonl`（节树扁平化）+ 归并清单 | 否 |
| `extract` | `extract.*` | 同上 + images/ | `exercises.jsonl` / `figures.json` / 公式双轨 | 否 |
| `candidates` | `candidate.split()` | 上两段产物 | `candidates.jsonl`（节点初稿 + 锚点匹配度 + 粒度报警） | **裁边界与命名** |
| `graph` | `graph.emit()` | candidates（人改过的） | `graph.jsonl` + `build_report.md` | 确认 |

段与段之间**只通过文件传递**，不通过内存里的对象串起来。理由：任一段可单独重跑，
人改完 `candidates.jsonl` 只需重跑最后一段（几秒），不必重跑整条链。

## 6. 失败与降级（所有降级必须留痕）

| 情况 | 策略 | Issue code |
|---|---|---|
| `page_map.md` 缺该页 | `book_pages=None`，`physical_pages` 照给 | `pages_missing` |
| 某 `##` 四类全不匹配 | 归入提问块 → 并入正文，不产生边界 | `heading_unclassified` |
| 标题被 OCR 污染需归并 | 按 graph-spec §10.2 归并，记录原文 | `heading_merged` |
| 题号缺失 / 题干跨页 | 不算完整 Exercise，进待认领；跨页的标 `spans_pages` | `exercise_incomplete` |
| 公式 plain 转换失败 | 保留 latex 去符号版，`degraded=True` | `formula_plain_degraded` |
| 节的行区间为 0 | 不生成节点 | `section_empty` |
| 图号找不到文件 | 不进 `figures`，进待确认 | `figure_missing` |
| 粒度越界（页数/节点数超配额） | 不自动改，只报警 | `granularity_outlier` |

**不许静默**：任何 catch 到异常后继续的地方，必须产生一条 Issue。

## 7. 可测性设计

| 测试 | 测什么 | fixture |
|---|---|---|
| `test_structure_heading` | 四分类 + 编号缺空格 + 章名续行 | 从必修一抽的 20 条真实标题（**字符串内联，不用文件**） |
| `test_structure_merge` | OCR 归并 5 条：`da` / `••` / `3思考` / 空串 / 正常含"思考"的正文标题 | 同上 |
| `test_structure_pages` | 页界标记 → physical_pages；page_map 缺行 → `book_pages=None` + Issue | 30 行内联 md |
| `test_exercises` | 题号识别、跨页题干、缺号进待认领 | 1 个小节内联 md |
| `test_formula_plain` | graph-spec §6 规则表逐条 + 反例 | 内联 |
| `test_graph_schema` | 字段完整、id 唯一、prereq 指向存在、pages 为 null 的节点不得标 verified | 手写 3 节点 |

纯函数边界的意义：**前五个测试全不碰磁盘**，跑完不到 1 秒，可以进 CI 第一梯队。

## 8. CLI 面（细规入 spec-cli.md）

**写侧（build）**：

```
b2q build --book <册名> --stage {structure|extract|candidates|graph} [--workspace P] [--force]
b2q config {get|set} <key> [value]
b2q --version
```

**读侧（skill 运行时，见 [skill-io.md](skill-io.md)）**：

```
b2q recall  --book <册名> --query "<学生原话>" [--top 3]   # 定位 + 取料，返回候选与原文段落
b2q node    <节点 id>                                      # 单节点全料
b2q section --book <册名> --sec <3.2>                      # 该节节点顺序 + 前置
b2q due     --book <册名> [--limit 5]                      # 复习到期清单
b2q log     --event <ask|attempt|learn_progress|review_done> --node <id> [...]
```

读侧命令是 **skill 唯一的数据入口**：模型不读 `markdown.md`、不算页码、不判归属。
`recall` 在内存里现建索引（75 节点 + 约千段段落，毫秒级），不依赖 `index/` 落盘缓存。

| 退出码 | 语义 |
|---|---|
| 0 | 成功（含"有待确认项"——用 JSON 字段表达，不用退出码） |
| 10 | 质量闸未通过（graph 段：必填字段缺失 / id 重复） |
| 20 | 用法或配置错误 |
| 40 | 契约违约（candidates 被手工改坏，字段类型不符） |
| 50 | 输入文件不存在（markdown.md / page_map.md 缺失） |

stdout 单 JSON、stderr 人类日志——与 book2md 完全同形，技能壳不必写两套解析。

## 9. 与 graph-spec 的三处冲突（必须裁）

### 9.1 `pages` 必填 vs 可能算不出

graph-spec §3 把 `pages` 列为**必填**，但 `page_map.md` 缺行时算不出来。
三种走法：

| 方案 | 做法 | 代价 |
|---|---|---|
| A（推荐） | 字段保留必填，**值允许 `null`**；`graph.py` 质量闸规定：pages 为 null 的节点不得标 `verified`，且必须出现在 build_report | 契约措辞要改一句（在冻结前改，成本低） |
| B | 缺失即报错，整册不产出 | 一页映射缺失就废掉全册，太脆 |
| C | 用物理页冒充电材页 | 违反"页码溯源不得靠猜"，否决 |

### 9.2 节点命名由谁做

| 方案 | 做法 | 代价 |
|---|---|---|
| A | 机器只切区间 + 出锚点，**title/type/summary 全由人写** | 75 行 × 3 字段，约 1–2 小时；但每个字都是人负责 |
| B（推荐） | 机器出草稿（取节内首个定义句的主语），人批量改；`built_by="auto"` 让下游知道这是机器名 | 需要命名规则表 + 一轮人工通读 |
| C | 机器定名直接入库 | 命名错会传染到检索与出题，且无法验收，否决 |

### 9.3 `data/index/` 是否 v1 就建

design.md 的数据流画了 `index/`，但检索是 `ask` 阶段（S2）才需要。
**v1 不落盘**：`recall` 在内存里对 75 个节点 + 约千段段落现建 BM25（毫秒级），
`index/` 只在"启动耗时成为问题"时才作为缓存落盘。这样 build 不必背检索的复杂度，
而读侧命令已经能用（见 skill-io.md）。

## 10. 明确不做的事

| 不做 | 原因 |
|---|---|
| import book2md 的代码 | 跨模块走文件，见 README 约定 2 |
| 引入第三方依赖 | graph-spec 已定"标准库实现 BM25"；build 段更是零依赖 |
| 在 core 里 print / log | 会让 stderr 变成第二个真相源；一律 `Issue` 进 report |
| 自动改教材文本 | 只读；发现错误记 Issue，不改原文 |
| 增量构建（只重建改动的节） | v1 整册重跑约几秒到几十秒，复杂度不值得 |
