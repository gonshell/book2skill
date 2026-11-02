# serving.md — 向量层选型、索引与五 skill 场景总设计

> 回答四个问题：**向量库怎么写、怎么读、选什么模型、五个 skill 各自怎么用**。
> 分工：[retrieval.md](retrieval.md) 管问题分类与兜底，[skill-io.md](skill-io.md) 管命中后的
> prompt 组装与校验，本文管**中间那层**——索引形态、四路召回管线、按场景的排序与取料。
> 阶段归属：本文全部内容属 **S2（检索）**；`build --stage=graph`（S1）不产出索引。

---

## 1. 选型定版

### 1.1 向量库：不用向量数据库，用 `.npy` + `jsonl`

| 方案 | 判断 |
|---|---|
| Milvus / Qdrant / FAISS 服务 | ❌ 单册 4000 条向量，装服务是给自己找运维活 |
| **numpy 暴力内积** | ✅ 4000 × 512 维 × float32 ≈ **8 MB**，全量内积 <1 ms，唯一依赖 numpy |

落盘形态（每册一套，互不混）：

```
data/index/
├── vectors_必修第一册.npy      # 4000×512 float32，已 L2 归一化（内积=余弦）
├── payload_必修第一册.jsonl    # 与 .npy 行号一一对应
└── meta_必修第一册.json        # {"model":"bge-small-zh-v1.5","dim":512,
                               #  "md_sha256":"…","built_at":"…"}
```

**两条纪律**：

1. **索引是缓存，不是事实源**。原文只在 `markdown.md`，图谱只在 `graph.jsonl`；
   索引损坏 / 换模型 / 换 chunk 规则，一律全量重建（CPU 几秒），不做增量更新。
2. **hash 绑定**。`meta.md_sha256` 不匹配当前 `markdown.md` 时，`recall` 拒绝使用
   向量路（降级三路）并报 `issue=index_stale`——防止"向量是旧书的、原文是新书的"。

### 1.2 模型：bge-small-zh-v1.5，ONNX 运行时

| 项 | 决定 | 理由 |
|---|---|---|
| 模型 | `bge-small-zh-v1.5`（BAAI，MIT 许可） | 中文短文本实测最强的小模型；段落全部 <512 token，**512 维** |
| 权重格式 | ONNX（~100 MB） | 避开 sentence-transformers 拖 PyTorch（~2 GB） |
| 运行时 | `onnxruntime`（~50 MB），纯 CPU | 单条 query 编码 5–20 ms，满足交互 |
| base/m3 何时考虑 | 评测集说话 | bge-base 若 Recall@5 提升显著再换，签名不变 |

**降级开关**：`B2Q_EMBED=off` 或模型未下载时，R4 自动关闭，`recall` 照常工作
（三路）。四个 skill 的 prompt 组装不感知差异——R4 只是多一路候选。
**三路是正常形态而非故障态**（RV-Q11 口径）：模型分发在 S2 落地时再定，
文档中的向量维度以 bge-small-zh-v1.5 实际输出 **512 维**为准（此前写 384 系笔误）。

## 2. 写入：三个池，payload 只存指针

切分**不按固定字数**，按语义自然边界（教材结构是现成的）：

| 池 | 一条是什么 | 量级 | 送进模型的文本 | payload |
|---|---|---|---|---|
| `node` | 一个知识点 | 75 | `title + aliases + summary + errors + formulas.plain` | `node_id, section, pages` |
| `para` | 一个正文/思考/例题段 | ~3000 | `节路径 + 小节标题 + 段落正文`（公式 plain 化，去图片标记） | `node_id?, section, physical_page, block_kind, quote_head` |
| `ex` | 一道题 | 500–700 | `节路径 + 题干`（plain 化） | `node_id, label, page, quote_head` |

- **payload 不存全文**：命中后凭 `quote_head` 回 `markdown.md` 取原文，与锚点纪律一致。
- 三个池**分开检索**（一次 query 向量，分别对三池内积，各取 top20 进融合）——
  题干和正文语义密度不同，混在一个池里题目会被正文淹没。
- 建库命令：`b2q index --book X [--rebuild]`（S2）。读 graph/structure/exercises 产物 +
  markdown 原文，产出上面三个文件，`--rebuild` 忽略 hash 直接重算。

## 3. 读出：四路召回 + RRF 融合（统一管线）

```
query ──归一化──► 意图词剥离（为什么/怎么/是不是 → 删）
   ├─ R1 词表锚定：graph 的 title/aliases/errors 最长匹配 → 节点名次
   ├─ R2 两段式 BM25：先词表定节，再节内段落排序 → 段落名次
   ├─ R3 结构精确：正则抽 P76 / 3.2 / 练习3 → 精确命中
   └─ R4 向量内积：query 编码一次 → node/para/ex 三池各 top20
        ▼
   RRF 融合：score = Σ 1/(60 + 名次)，各路名次都靠前者胜出
        ▼
   场景加权（§4 矩阵，每场景一套 bias）→ top5 候选
        ▼
   取料：quote_head → markdown 原文全文 → skill-io.md §3 组 prompt
```

- RRF **只比名次不比分值**：BM25 分和余弦分不同纲，名次天然可比。
- R4 的 `why` 写成 `语义近邻(0.82)`，与其他路同格式，进回归测试。
- 兜底三级（显著领先 / 接近 / 全低）沿用 retrieval.md §8。

## 4. 五个 skill 场景总矩阵

**同一管线，不同场景只改四件事：主入口、候选池、排序策略、图扩展。**

| | ask 答疑 | learn 精学 | drill 练习 | review 复习 | build 建库 |
|---|---|---|---|---|---|
| **主入口** | 自由文本 | 节号/节点名 | 无输入 | due 列表 或"我忘了X" | —（写侧） |
| **召回** | 四路全开 | **R3 精确主路**，R1/R4 兜底"学生说人话找入口" | **不检索**，store 驱动 | 排程不检索；唤起走 R1+R2+R4 | — |
| **候选池** | node+para+ex | node | ex | node | — |
| **排序** | RRF + intent 加权：`concept_why` 提 `role=motivation` 段；`check_work` 提 `errors`；`stuck` 提 ex 池 | **结构拓扑序，不用分数**——节内按 id 序，学习路径不是相关度路径 | mastery 升序 → 教材原题优先 → 变式 | due 日期早优先 → 有错题记录优先 | — |
| **图扩展** | 不拉 prereq（答案要聚焦可溯源） | **拉**：prereq 邻居 mastery 低则先补，这是 learn 的本义 | 变式题按 `errors` 反向生成 | 不拉 | — |
| **输出** | intent 分叉模板（retrieval §6） | 每节点 3 分钟讲解 + 1 题 | 题面，判分用 errors 当错因表 | ≤3 句唤起 + 立刻 1 题 | graph.jsonl |
| **落库** | `log ask` | `log learn_progress` | `log attempt` | `log attempt/review_done` | — |

### 4.1 ask：唯一"自由检索"的场景

学生原话进管线全四路。两个场景特有规则：

1. **题干优先**：query 含数字/符号且 >15 字时，ex 池名次 ×2——"这题第二问不会"
   应该先找到那道题，再由题映射回节点。
2. **check_work 不走相似题**：学生贴自己的解法求判错时，R4 的"相似题目"是干扰
   （他的错解和任何原题都不相似），候选只从命中节点的 `errors` 取。

### 4.2 learn：检索只是入口，顺序来自图

学生说"学 3.2"→ R3 精确定位，**此后不用检索器**：`section` 取节点序列，
逐个 `node` 取料。检索器只在"函数那块我不懂"这种入口模糊时兜底定起点。
前置检查是硬流程：`prereq` 邻居查 store，mastery < 0.6 先讲邻居（这就是
"GraphRAG 邻域扩展"的人工审边版本）。

### 4.3 drill：store 驱动，检索器只管"相似题"

出题主路径：`store` 里 mastery 低的节点 → 该节点 `exercises`（教材原题优先）
→ 不够按 `errors` 造变式（标注"非教材原题"）。检索器唯一用途：学生贴一题说
"来道类似的"→ R4 ex 池相似检索，**排除原题本身**。

### 4.4 review：两个分支，检索器只服务唤起

- 排程型（"今天复习什么"）→ `b2q due`，不进检索；
- 唤起型（"诱导公式我忘了"）→ 走管线命中 → **复习模式**：原文 ≤200 字、
  一句话唤起、立刻 1 题（retrieval §7 硬约束）。
- 学情报告小节：store 聚合，与检索无关。

## 5. 评测先行（R4 与权重的裁判）

在写检索器之前先建评测集：**30–50 条真实问法 + 人工标定 gold**（期望命中的
节点/段落）。每次跑四路各自与融合的 **Recall@5 / MRR**：

- R4 加入前后对比 → 决定向量路去留与 base 升级；
- 场景加权初值是拍的，评测后调；
- gold 初稿由问法分类表生成，**标定需人工过目**（定版见 §6 ①）。

## 6. 三项裁决记录（2026-11-01 用户确认）

| # | 事项 | 定版 |
|---|---|---|
| ① | 评测集 gold 标定 | 我出初稿（半小时人工量），用户过目签字后冻结 |
| ② | 运行时依赖边界 | onnxruntime + bge ONNX（~150 MB）+ numpy；**模型为可选依赖**，未装 R4 自动关闭降级三路 |
| ③ | ask 拉 prereq 与否 | ask 不拉（聚焦、可溯源）；learn 拉（前置检查本义） |

## 7. 与现有文档的接口

- retrieval.md §9（"scorer 可替换"）→ 本文即其落地，签名 `recall(query, k) -> list[Candidate]` 不变；
- skill-io.md §1 的五个命令不变，`recall` 增加 `--scene {ask|learn|drill|review}`（默认 ask）；
- arch.md §9.3 "v1 不建 index" → 修正为"**S1 不建，S2 由 `b2q index` 建**"，无矛盾。
