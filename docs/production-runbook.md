# production-runbook.md — 制书运营手册（PDF → 学生可用，全流程剧本）

> 一册新教材从 PDF 到学生可用的**完整操作剧本**。每步给出命令 / 角色 / 耗时 /
> 验收标准 / 已知坑。分段原理见各专项文档（文末索引）；本文只管"照着做"。
> 基线：必修一（78 节点）与必修二（81 节点）双册上线，v0.7.0。

## 总览与角色

| 步 | 做什么 | 角色 | 耗时 |
|---|---|---|---|
| 0 | 前提核对 | 机器 | 2 分钟 |
| 1 | build 四段（结构→抽取→候选→图谱预跑） | 机器 | ~10 分钟 |
| 2 | 导出裁定 Excel + 机器初稿 | 机器 | ~2 分钟 |
| 3 | **人工裁定** + AI 自审 | **人**★ | 1–2 小时 |
| 4 | 写回 + graph 冻结（质量闸） | 机器 | ~5 分钟 |
| 5 | 向量索引 | 机器 | ~3 分钟/册 |
| 6 | 发布 | 机器 | ~10 分钟 |
| 7 | 发布验证探针 | 机器 | ~2 分钟 |
| 8 | 试用循环（周报/迭代） | 人+机器 | 持续 |

**一册的净周期 ≈ 半个工作日**，其中人工裁定是唯一不可自动化环节。

---

## 第 0 步：前提核对

确认 book2md 产物五件齐全（路径 `<gzsx-md>/final/<册名>/`）：

```bash
ls <gzsx-md>/final/<册名>/{markdown.md,page_map.md,images}
```

- [ ] 五件全在（markdown.md / page_map.md / images/ …）
- [ ] book2md 质检报告（`质检报告.md`）无未处置的红色项
- 坑：`page_map.md` 缺失会导致页锚定整体降级（RV-C1 语义：报 pages_missing 继续，但节点全 unverified）——缺失先回 book2md 补

## 第 1 步：build 四段

```bash
cd book2skill/book2qa
for st in structure extract candidates graph; do
  b2q build --book <册名> --stage $st
done
```

| 段 | 验收（以必修一/二实测为参照） |
|---|---|
| structure | exit 0；`issues` 里 page_mark_unparsed=0（有则查页界标记格式） |
| extract | exercises ≥500（两册实测 584/5xx）；figures ≥100 |
| candidates | 候选数 45–55；id 全唯一 |
| graph | 此步**只是预跑**——闸可能拦（如公式破损降级 26–32 条属正常），节点数暂不追求达标 |

**产物落点**：`data/<册>/`（按册隔离；⚠️ 不会碰其他册的冻结图谱——M3-4 修过）。
坑：候选里例题/练习的题归属可能有边界重叠（必修二 S4C-K02/K03 曾挂同批题）——登记到裁定表备注，drill 精修时处理，不阻塞。

## 第 2 步：导出裁定表 + 机器初稿

```bash
b2q review-export --book <册名> --out data/<册名>/review-v1.xlsx
python scripts/draft_review.py data/<册名>/review-v1.xlsx
```

机器初稿规则：页跨度≥5 且题≥8 → 拆"定义/方法(method)"，跨度≥8 加"例题(application)"；
题≥14 补 method 位；method 块后缀按内容定制（运算法则与计算/判定与证明/应用与求解…）；
OCR 噪音标题自动清理（如 `$3^{\ast}$` →（选学））。

## 第 3 步：人工裁定（★ 核心工序，唯一不可自动化）

**AI 先自审一遍**（逐条对照教材证据：summary/锚点/题标签），修三类问题——
后缀用词、OCR 噪音、题归属疑点——然后交人终审。

人看什么（顺序即优先级）：
1. **拆分行**：子标题像不像学生说法；method/application 标得对不对
2. **总数与配额**（导入预览会给）：总数 72–88；method 25–30%（超了删几个方法块）
3. **别名**：口语叫法（巡检报告的低置信聚类是最好的素材源）
4. 同意的不动，不同意的整行清空批注列

产出：批注后的 xlsx（建议命名 review-final.xlsx）。

## 第 4 步：写回 + 冻结

```bash
b2q review-import --book <册名> --file <批注表>            # 先预览 diff（不写回）
b2q review-import --book <册名> --file <批注表> --apply    # 确认写回
b2q build --book <册名> --stage graph                      # 质量闸
```

- 验收：graph exit 0；节点数 **72–88**；issues 里只剩 `broken_formula_in_quote`
  （源级公式破损 → 降级 unverified，属正常，两册实测 26–32 条）
- 坑：闸若报 `graph_missing_field: anchors` → 拆分块锚点共享逻辑未生效（已修，
  出现说明代码回退）；`EXIT_GATE_FAIL` 未定义 → build.py 导入缺失（已修）

## 第 5 步：向量索引

```bash
b2q index --book <册名>
```
验收：encoded ≈ 段落数（两册 2133/2179）、dim 512、exit 0。

## 第 6 步：发布

```bash
B2Q_PYTHON=<python≥3.12> bash book2qa/deploy/deploy.sh
```
自动：测试前置断言 → 按册同步 data + book2md 原文 → build 镜像 → up →
healthz 轮询 30 秒 → 失败自动回滚。幂等可重跑。

## 第 7 步：发布验证探针

```python
# healthz：节点数 = 各冻结册之和；auth:on
# recall：每册抽 1 问（如必修二"余弦定理怎么求第三边"→ 应命中该章系列）
# plot：/plot 出 PNG；/img 出教材原图（带 key 200，无 key 401）
```
（探针脚本模式见 `Temp/b2q_two_book_probe.py` 的写法：urllib + serve.json 取 key。）

## 第 8 步：进试用循环（持续）

- 每周：`scp` 服务器 request_log → `scripts/inspect_report.py` 出周报 →
  按 `ops/试用-观察清单.md` 处置（补 aliases / 加 gold）
- aliases/gold 改动 → 重跑 graph（+index）→ deploy —— **学生数据永不动**
- 防孤本：`ops/backup.sh`（周）+ `--full`（月/发版后）

---

## 剩余排产与已知风险

| 册 | 状态 | 预估 |
|---|---|---|
| 必修第一册 | ✅ 冻结 78 节点上线 | — |
| 必修第二册 | ✅ 冻结 81 节点上线 | — |
| 选择性必修第一册 | 待跑（产物在 gzsx-md） | 半个工作日 |
| 选择性必修第二/三册 | 待跑 | 各半天 |

已知风险（按册递查）：
1. **选学内容**（`$3^{\ast}$` 类星号节）：初稿会自动清理命名，但保不保留由裁定定
2. **题归属边界**：相邻节共享例题（必修二解三角形实测）→ 备注登记，drill 精修
3. **aliases 空缺**：每册都需要人补口语叫法（巡检聚类是素材）
4. **选必册可能结构不同**（活动章/数学建模）：build 若出畸形候选（无题无锚大壳），
   属预期，裁定站处理

## 专项文档索引

| 段 | 深读 |
|---|---|
| PDF→MD | book2md/README.md、book2md/docs/、MinerU 网关手册 |
| build 契约 | book2qa/docs/pipeline.md、design.md |
| 图谱契约（冻结区） | book2qa/docs/graph-spec.md |
| 检索/输出模板 | book2qa/docs/retrieval.md、skill-io.md |
| 部署运维 | docs/ops-runbook.md、docs/infra-server.md |
| 试用运营 | ops/试用指南-学生版.md、ops/试用-观察清单.md |
