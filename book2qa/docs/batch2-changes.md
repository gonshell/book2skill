# BATCH-2 字段表变更清单（评审 BATCH-2 + RV-Q7，触冻结区）

> **本清单需你过目后才动手**（评审台账 §4.2 风险约定：触冻结区先出变更清单）。
> 每项标明：改什么、影响哪些已产出数据、是否需要迁移。

## 一、graph-spec §3 字段表变更（冻结区，4 处）

| # | 变更 | 变更前 | 变更后 | 已产出数据影响 | 迁移 |
|---|---|---|---|---|---|
| 1 | `pages` 可空（RV-C1 尾巴，arch §9.1 已有用户裁定背书） | 必填 ✅ | 必填 ✅ 但**值允许 null**；缺页报 `graph_no_pages` 且节点强制 `unverified`（质量闸已按此实现） | 现有 46 节点全部有 pages，无实际影响 | 无 |
| 2 | 新增 `aliases`（RV-C3） | 无此字段 | ⬜ 可选，`string[]`，语义 = 口语/俗称/旧称；产出方 = build 后期从节标题+题干抽取，v1 允许空缺 | 无（新字段） | 无 |
| 3 | 新增 `errors` 与 `summary` 产出方说明（RV-C4） | `errors`/`summary` 已在字段表但无产出方 | `summary` 产出方 = **candidates 阶段**（机器出初稿+人改，现状已如此）；`errors` 产出方 = **graph 阶段人工/后续规则**，v1 允许空缺 | summary 已有内容 ✓ | 无 |
| 4 | `physical_page` 消歧改名（RV-C7） | anchors 内字段名 `page`，文档混用"PDF 物理页/物理页/教材页" | **字段名不变**（`page` 存教材页，与现有产物一致），文档统一术语表：`物理页 = 印刷页`、`PDF 页 = 扫描序号`、`教材页 = 页码标注页`；graph-spec §5 样例值 76 改为物理页 83 或标注教材页 | 无（字段名不动，避免破坏既有产物） | 无 |

> 说明：RV-C7 评审建议改名 `phys_page`/`tb_page`，但 anchors 里存的是**教材页**且产物已发布口径——改名会破坏"已产生数据不错位"原则。采用术语表消歧代替改名，效果等价、零迁移。

## 二、issue code 归一（RV-Q3，实现层）

| # | 变更 | 说明 |
|---|---|---|
| 5 | arch.md §"降级清单"重写 | 以 report.py `_CODE_TITLES` 为**唯一权威**（15 个码 + 质量闸 9 个码），arch 里旧 8 码表删除；新增的 `page_mark_unparsed` / `pages_missing` 一并登记 |
| 6 | `page_marks_absent` 已修为字典格式 | 本轮已做（commit d367d86），登记入档 |

## 三、kind 口径回写（RV-Q4，以实现为准）

| # | 变更 | 实现（权威） | 文档修正处 |
|---|---|---|---|
| 7 | 标题 kind 枚举 | `chapter / section / subsection / prompt / ch_end / item / noise / minor / meta`（9 值）+ 结构行 `kind: chapter/section/subsection/meta/ch_end/front` | transform.md §S2、graph-spec §10、pipeline.md |
| 8 | 章末行为 | `复习参考题N` 切出章级附属行 `C{n}-END`，不归最后子节（防污染，本轮实测抓到） | graph-spec §10 补一条 |

## 四、图号与产物表（RV-C6 / RV-C8 / RV-Q7）

| # | 变更 | 说明 |
|---|---|---|
| 9 | 图号格式统一三段 `图{章}.{节}-{序}`（RV-C6） | 改 design.md:168、graph-spec.md:94 两处错误示例；与真实产物 `图1.2-1` 一致 |
| 10 | `pipeline.md` 产物表：`figures.json` → `figures.jsonl`（RV-C5 文档侧） | 已改名，文档同步 |
| 11 | `pipeline.md` 产物表补 `para_meta.jsonl` 一行（RV-C8） | 结构→抽取段的硬依赖，4333 行/册 |
| 12 | 规模数字标注口径（RV-C10 顺手修） | structure 63 行/册、exercises 584 条/册、figures 106 条/册（必修一实测），五册 ×5 估 |
| 13 | **exercise label 唯一性**（RV-Q7，已提前） | 现状 584 条中 22 组同 label（跨章同页同块号）。方案：label 加章节前缀 `3.2-习题2` 或加唯一 `eid`；**推荐后者**（label 保持人读，eid 供索引），candidates/graph 的 exercises[] 增加 `eid` 字段——这是冻结区字段内容变更，同样待你批 |

## 五、不动手项（本批明确排除）

- RV-C9 / RV-Q11：仅文档补"下游不继承上游质检结论""未装模型=三路正常形态"两句（已获你确认的降级修法）
- RV-Q1 / RV-I4 / RV-I5：读侧命令属 BATCH-3，与 S2 开发合并做
