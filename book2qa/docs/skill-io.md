# skill-io.md — skill 运行时：读什么、怎么组 prompt、输出怎么校验

> 回答"skill 去哪里读什么"。核心原则一句话：
> **检索与取料在代码里确定性完成，模型只负责把料讲成话。**
> 模型不读 `markdown.md`，不自己找页码，不自己判断"这属于哪个知识点"。

---

## 0. 为什么不让模型自己读 markdown

| 让模型读 md | 走 `b2q recall` |
|---|---|
| 5–8 万字全文或大段切片进上下文 | 只进 top1–2 节点的 3–5 段原文（≤1500 字） |
| 页码靠模型数，可能数错 | 页码由 `page_map` 换算，写死在 JSON 里 |
| 命中哪个知识点靠模型感觉 | 命中理由（`why`）可复现、可回归测试 |
| 无法做掌握度（没有节点 id） | 每个答复都带 `node_id`，能落库 |

## 1. 五个运行时命令（skill 只调这五个，不碰文件）

| 命令 | 用途 | 谁调 |
|---|---|---|
| `b2q recall --book X --query "原话" [--top 3] [--scene ask]` | 定位 + 取料；`--scene` 决定候选池与排序侧重（serving.md §4），默认 ask | ask / learn / drill / review |
| `b2q node <id>` | 取单节点全料 | learn / drill |
| `b2q section --book X --sec 3.2` | 取某节节点顺序 + 前置 | learn |
| `b2q due --book X [--limit 5]` | 到期复习清单 | review |
| `b2q log --event <类型> --node <id> [...]` | 落库（掌握度/错题/互动） | 全部 |

### 1.1 `b2q recall` 的真实返回（对应 P76 那个问题）

```bash
b2q recall --book 必修第一册 --query "单调性为什么一定要说任意两个数" --top 3
```

```json
{"cmd":"recall","ok":true,"exit_code":0,
 "intent":"concept_why","confidence":"high",
 "candidates":[
  {"node_id":"M1-C3-S2A-K01","title":"函数单调性的定义","type":"concept",
   "pages":[76,78],"score":0.87,
   "why":"术语命中 单调性(title×3); 段落命中 任意(思考块 P76)",
   "summary":"在区间 I 内任取 x1<x2，由 f(x1) 与 f(x2) 的大小关系定义增函数与减函数。",
   "quotes":[
     {"role":"definition","page":76,"block":null,
      "text":"一般地，设函数f(x)的定义域为D，区间 I⊆D。如果 ∀x1,x2∈I，当 x1<x2 时，都有 f(x1)<f(x2)，那么就称函数 f(x) 在区间I上单调递增……"},
     {"role":"motivation","page":76,"block":"思考",
      "text":"(1) 设A是区间I上某些自变量的值组成的集合，而且 ∀x1,x2∈A 当 x1<x2 时，都有 f(x1)<f(x2)，我们能说函数 f(x) 在区间I上单调递增吗？你能举例说明吗？"}],
   "formulas":[{"latex":"$x \\leqslant 0$","plain":"x <= 0"}],
   "errors":["用两个特殊值代替『任意 x1<x2』判断单调性","忽略区间前提，直接说 f(x) 是增函数"],
   "exercises":[{"label":"P77 例1","page":77,"quote":"根据定义，研究函数 f(x)=kx+b(k≠0) 的单调性。"}]}],
 "fallback":null}
```

字段约定（skill 只认这几个，其余忽略）：

| 字段 | 用途 |
|---|---|
| `intent` | 选输出模板 |
| `confidence` | `high` / `low` / `none` 决定是否先反问 |
| `candidates[].quotes[]` | **唯一可引用的原文**，`role=motivation` 优先用于"为什么" |
| `candidates[].errors[]` | 易错点段落直接引用，不许改写 |
| `candidates[].exercises[]` | 出题用的原题 |
| `fallback` | 非空时表示没命中，`options` 给 3 个切入点 |

低置信 / 无命中时：

```json
{"ok":true,"intent":"too_broad","confidence":"none",
 "candidates":[],"fallback":{"type":"clarify",
 "options":[{"label":"函数的概念","sec":"3.1","hint":"从定义域、值域讲起"},
            {"label":"单调性","sec":"3.2","hint":"从图象直观讲起"},
            {"label":"奇偶性","sec":"3.2","hint":"从图象对称讲起"}]}}
```

## 2. ask 的一次完整调用

```
① 学生：「单调性为什么一定要说"任意"两个数？」
② skill 执行：b2q recall --book 必修第一册 --query "<原话>" --top 3
③ 拿到 JSON（上例，confidence=high）
④ 按 intent=concept_why 组 prompt（§3 模板）
⑤ 模型输出四段（§4 校验）
⑥ skill 执行：b2q log --event ask --node M1-C3-S2A-K01 --intent concept_why --hit true
⑦ 回给学生文本
```

skill 自己**只做两件事**：调命令、拼 prompt。凡是"这个知识点在哪一页""这句话教材怎么写的"，
一律来自 JSON。

## 3. prompt 装配（固定七块，顺序不能变）

```
【角色】你是人教A版高中数学的答疑老师，说话简短，不用套话。

【红线】只能使用下面【教材原文】里的内容。原文没有的，直接说"本节未涵盖"，
       不要用你的常识补。引用必须带页码。

【学生的问题】单调性为什么一定要说"任意"两个数？

【命中知识点】函数单调性的定义（必修第一册 P76–78，概念）

【教材原文】
（P76 · 定义）一般地，设函数f(x)的定义域为D，区间 I⊆D。如果 ∀x1,x2∈I……
（P76 · 思考）(1) 设A是区间I上某些自变量的值组成的集合……我们能说函数 f(x) 在区间I上单调递增吗？

【易错点】
- 用两个特殊值代替『任意 x1<x2』判断单调性
- 忽略区间前提，直接说 f(x) 是增函数

【输出格式】按四段，标题照抄：
直答：一句话
教材怎么说：引用上面【教材原文】的原句（带页码）
换个角度看：举一个"没有这个条件就不成立"的反例
易错点与依据：结合【易错点】给一句提醒，末尾写"依据：必修一 P76 §3.2.1"
```

### token 预算

| 块 | 上限 |
|---|---|
| 教材原文 | ≤1200 字（3–5 段） |
| 易错点 + 公式 + 题目 | ≤300 字 |
| 输出 | ≤400 字 |

超了先砍候选（top3 → top1），不砍原文——砍原文等于让模型开始编。

## 4. 输出校验（skill 侧，不靠模型自觉）

| 检查 | 不通过怎么办 |
|---|---|
| 四段小标题齐全 | 重试一次（附"缺少 X 段"）；仍缺则降级为只给"直答 + 依据"并说明 |
| 含"依据：…P{页}" | 同上 |
| 引用句能在 `quotes[]` 中找到（前 12 字匹配） | **视为编造**，重试一次；再失败则回问并记 `issue=hallucination_suspect` |
| 出现"本节未涵盖"时不含具体结论 | 直接返回，不做二次加工 |

最后一条是 `test_no_hallucination` 的运行时对应物：测试守的是这条链路。

## 5. review 的一次完整调用

```
① 学生：「今天该复习什么」
② skill：b2q due --book 必修第一册 --limit 5
   → {"items":[{"node_id":"M1-C5-S3-K01","title":"诱导公式（一~四）","due":"2026-10-27","mastery":0.4,
                "last_error":"符号判断错","exercises":[…]}]}
③ 不进讲解，直接出题（题从 items[].exercises 取；不足则按 errors 造反式，标"非教材原题"）
④ 学生答完 → b2q log --event attempt --node … --correct false --error_tag 符号判断错
```

学生中途说「诱导公式我忘了」→ 走 `recall` → 命中 3 个节点 → **复习模式 prompt**：
原文最多 200 字、只讲一句、立刻 1 题，禁止长篇（retrieval.md §7）。

## 6. 五个 skill 的读取清单

| skill | 调什么 | 读哪些字段 | 写什么 |
|---|---|---|---|
| ask | `recall` | `intent` `confidence` `quotes` `errors` `formulas` `exercises` | `log --event ask` |
| learn | `section` → `node` | `nodes[]` 顺序、`prereq`、`quotes`、`errors` | `log --event learn_progress` |
| drill | `node` / `recall` | `exercises`、`errors`（判分依据） | `log --event attempt` |
| review | `due` → `node` | `due` `mastery` `last_error` `exercises` | `log --event attempt` / `review_done` |
| build | 不调（写侧） | — | 产出 §1 五件产物 |

## 7. 失败路径（skill 必须照做，不许临场发挥）

| 情况 | 动作 |
|---|---|
| `confidence=none` + `fallback.type=clarify` | 把 `options` 三条原样给出去，问"你想从哪个开始"；**一个结论都不许给** |
| `confidence=low` | 开头一句"你问的是不是『X』？"，答完再问"如果不是，告诉我关键词" |
| 命令非零退出 / 超时 | 明说"我这边查教材出了点问题"，不许改用常识回答 |
| 学生连续 3 次要求"直接给答案" | 照给，末尾加一句"建议先自己写到卡住的地方再看"（design.md 红线 3） |
