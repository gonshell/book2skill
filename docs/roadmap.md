# roadmap.md — book2qa 里程碑计划（权威计划层）

> **本文件是计划的唯一权威载体**。执行状态三标：⏳进行中 / ✅完成 / ⏸等待（写明卡谁）。
> 每次里程碑状态变更必须更新此文件并提交。
> 执行细节在会话任务清单里，历史记录在 memory 日志——本文件只放"计划与状态"。
> 顶层架构见 system-architecture.md；旧 S1–S4 计划作废（映射见 §4）。

## M1 服务层 MVP ⏳

一切的地基。四件互相独立，可并行。

| # | 任务 | 验收 | 状态 |
|---|---|---|---|
| M1a | `b2q serve`（FastAPI：/recall /node /healthz + API key + 内存索引 + 请求日志） | HTTP 契约测试全绿 + uvicorn 冒烟 | ✅ 2026-11-03（121 例全绿） |
| M1b | store（sqlite WAL：account/attempt/mastery/next_due/context）+ /log /due /mastery /context | 学情读写回归全绿 + SM-2 语义测试 | ✅ 2026-11-03（132 例全绿） |
| M1c | R4：`b2q index`（本地建索引 2133 段×512 维）+ recall 接第 5 路名次制 + embed.py（CLS 池化/查询指令前缀） | gold 经 HTTP 评测 **Recall@5 ≥ 80%** | ✅ 2026-11-03（**80% 达标**，MRR 0.660；修 NameError 静默吞错——R4 此前未生效） |
| M1d | 部署：docker 镜像化落地（Dockerfile/compose/deploy.sh 三件套；bundle 流水线；uid 对齐；env_file 供 key；**回滚演练 200/200**） | 一条命令起服务 + 回滚演练 | ✅ 2026-11-03（**M1 全部收官，v0.6.0**） |

交付：v0.6.0（v0.2–v0.3.2 已被 book2md 时代占用；后续 M3=v0.7.0、M4=v0.8.0）。

## M2 场景层最小闭环（ask 先行） ✅ 2026-11-03

- 六种输出模板 → ask skill：`skills/book2qa-ask/SKILL.md`（铁律四条 / confidence 分流 / 六模板路由 / 引用可溯校验 / 失联话术）
- /section /context 端点：✅（/section 整节节点序列+prereq；/context 7 天 TTL 在 store 层）
- **验收 ✅：10 轮模拟对话全通**（`scripts/simulate_ask.py` = SKILL.md 可执行契约：取料/分流/模板/校验/落库全链，含 clarify/low 确认/前提错/stuck/too_broad/追问承接）
- 服务器实测：/section 5.4.2 ✓、/log→mastery 1.0→next_due ✓、R4 容器内生效 ✓、回滚演练 ✓
- 过程修真 bug：deploy.sh heredoc `$(id -u)` 未转义（本地 uid 197609 传给服务器 → 容器用户错位 → WAL 只读）；compose 空插值覆盖 env_file
- 交付：ask skill + 演示 ✓（当前线上 tag=18e2842）

## M3 生产层成型 + 制书第二册 ⏳ **已解锁（M2 ✅）——等用户裁定即可开工**

- 裁定辅助（candidates ↔ Excel）、发布工具（含回滚）、巡检脚本、备份 cron
- **⚠️ 用户介入点：pending-review.md A/B 裁定 → graph 冻结 → index → 发布演练**
- 验收：制书全流程走通（含一次回滚演练）
- 交付：ops-runbook.md + v0.7.0

## M4 全场景 + 内网试用 ⏸ 等待 M2/M3

- learn/drill/review skill + 邀请码 + context 跨设备
- 内网试用 3–10 名学生
- 验收：第一份未命中巡检报告 + 试用反馈
- 交付：v0.8.0 + 试用报告

## M5 公网与多平台（触发式，不预做） ⏸ 触发条件 = M4 试用验证价值

- 公网化（HTTPS/域名/API key/限流）+ 豆包适配层 + 版权控制
- 明确不预做：学情报表、Gitea、GPU 推理、离线场景

## 旧计划映射（S1–S4 作废）

S1 剩余（裁定）→ M3 ｜ S2 剩余（R4）→ M1 ｜ S3/S4 → 被 M2/M4 服务化形态取代。

## 依赖与风险

- M1 不依赖用户裁定，可立即开工
- graph 冻结依赖 pending-review 裁定；评测基准依赖 gold 冻结（用户过目）
- R4 需服务器下载 bge 模型（hf-mirror 可达已验证）；SSH 免密已通（localgpu）
