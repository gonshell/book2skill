# system-architecture.md — book2skill 顶层系统架构（唯一入口）

> 本文档是**唯一的全局视图**：研发完成后有哪些系统、服务谁、如何服务、
> 如何运营。各专项细节下钻到对应文档（§6 交叉索引）。
> 图自上而下：**使用者在顶层，支撑在底层**；越靠上离学生越近。

## 1. 分层架构

```mermaid
flowchart TB
    U["学生（初中生）<br/>手机 · 笔记本 · 电视（只读展示）· 零安装"]

    subgraph L2["场景层 · 四个 skill（智能体壳：WorkBuddy / 豆包等）"]
        direction LR
        ASK["ask 答疑"]
        LEARN["learn 带学"]
        DRILL["drill 练习"]
        REV["review 复习"]
    end

    subgraph L3["服务层 · 学习服务系统 b2q serve（自控服务器，未来公网）"]
        direction LR
        API["排序检索 API<br/>R1 词表 · R2 段落<br/>R3 结构 · R4 向量"]
        STORE[("学生库 store<br/>掌握度 · 错题<br/>排程 · 会话")]
        LIB[("教材只读库<br/>原文 · 图片 · 图谱")]
    end

    subgraph L4["生产与运营层 · 运营者专用"]
        direction LR
        BUILD["制书流水线<br/>MinerU → book2md<br/>→ build → 裁定站"]
        TOOLS["运营工具<br/>发布 · 巡检<br/>备份 · 邀请码"]
        QUALITY["质量系统<br/>gold 评测<br/>质量闸 · 巡检报告"]
    end

    U --> L2
    L2 -- "HTTPS + 账号 token" --> API
    API --> STORE
    API --> LIB
    BUILD -- "发布知识库数据包" --> LIB
    QUALITY -.-> "评审 · 巡检 · 放行" .-> TOOLS
    QUALITY -.-> "放行/拦截" .-> BUILD
```

## 2. 各层职责与服务对象

| 层 | 系统 | 组成 | 部署位置 | 服务谁 | 状态 |
|---|---|---|---|---|---|
| 场景层 | 四个 skill（智能体壳） | 人设 + 输出模板 + API 调用薄壳 | 学生的 WorkBuddy / 豆包等平台 | **学生** | 待开发（skill-io §3/§4 已定义） |
| 服务层 | 学习服务系统 | `b2q serve`：排序检索引擎 + store + 教材只读库 | 172.20.4.209（试用）→ 公网（生产） | 场景层（间接服务学生） | 引擎已有（recall 72%）；serve/store/R4 待开发 |
| 生产与运营层 | 制书流水线 + 运营工具 + 质量系统 | MinerU 网关 + book2md + build 四段 + 裁定站；发布/巡检/备份/邀请码；gold 评测 + 质量闸 | 开发机 + 服务器 | 运营者 | MinerU/book2md/评测已有；裁定站与运营工具待开发 |

## 3. 学生视角：四个场景

| skill | 场景 | 服务端调用 | 关键约束 |
|---|---|---|---|
| ask | 任何疑问随时问 | /recall + /log | 答案必带教材依据；模板按意图分叉 |
| learn | "带我学 3.2" | /section + /node + /log | 前置检查（prereq）；讲完即练 |
| drill | 出题判分 | /log（store 取薄弱点） | 教材原题优先；errors 当错因映射 |
| review | 今天复习什么 | /due + /log | ≤3 句 + 1 题，只唤起不重讲 |

学生设备零安装；教材事实全部来自服务层 API，AI 只出讲法（红线 1）。

## 4. 运营者视角：四条运营线

| 线 | 节奏 | 动作 | 用到的层 |
|---|---|---|---|
| 内容线 | 每册数天 | 制书剧本：抽取 → build → **裁定站**（唯一不可自动化环节）→ 冻结 → index → 发布 | 生产层 → 服务层 |
| 质量线 | 每周 | gold 评测跑分防退化；未命中巡检 → 补 aliases / gold | 质量系统 |
| 用户线 | 持续 | 邀请码发放、试用反馈、学情报表 | 运营工具 |
| 保障线 | 每月 + 每次发布 | 备份三件套（gzsx-md / git / store）、回滚演练 | 运营工具 |

## 5. 数据归属（隐私与重建边界）

| 数据 | 位置 | 性质 |
|---|---|---|
| 教材侧（图谱/原文/图片/向量索引） | 服务层，随发布更新 | 只读、**可重建**、无隐私 |
| 学生侧（store） | 服务层，账号维度 | 只增、**不可重建**、隐私（匿名邀请码，不采实名，不出自控域） |
| 源头（PDF/抽取产物/代码/评测集） | 开发机 + 备份仓 | gzsx-md 为孤本，备份是硬要求 |

## 6. 交叉索引（细节下钻）

| 主题 | 文档 |
|---|---|
| 产品定义与知识形态 | design.md |
| 服务层引擎与检索 | retrieval.md · serving.md |
| 场景层契约（人设/模板/取料） | skill-io.md |
| 知识库条目契约（id/字段/锚点） | graph-spec.md（冻结区） |
| 制书流水线与产物 | pipeline.md |
| 部署形态与多平台发布 | deployment-review.md |
| 服务器与工具 | infra-server.md |
| 部署/发布/备份操作手册 | ops-runbook.md（✅ 部署运维手册） |
| **制书全流程剧本（PDF→学生）** | **production-runbook.md** |
| **里程碑计划与状态（权威）** | **roadmap.md** |
| 评审批次 | book2skill-review-report.md（仅本地） |

## 7. 建设状态总览（截至 2026-11-02）

- ✅ 已有：MinerU 网关、book2md（转换+渲染+质检）、book2qa build 四段、
  排序引擎三路（Recall@5 72%）、gold 评测集（待冻结）、质量闸
- 🔨 待开发：裁定站辅助、R4（index+向量路）、b2q serve + store、
  四个学生 skill、运营工具六件、ops-runbook
- ⏸ 等待决策：pending-review 裁定（S1 关账）、gold 冻结、部署位置与账号体系
  （deployment-review §3）
