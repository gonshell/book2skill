# roadmap.md — book2qa 里程碑计划（权威计划层）

> **本文件是计划的唯一权威载体**。执行状态三标：⏳进行中 / ✅完成 / ⏸等待（写明卡谁）。
> 每次里程碑状态变更必须更新此文件并提交。
> 执行细节在会话任务清单里，历史记录在 memory 日志——本文件只放"计划与状态"。
> 顶层架构见 system-architecture.md；旧 S1–S4 计划作废（映射见 §4）。

## M1 服务层 MVP ⏳

一切的地基。四件互相独立，可并行。

| # | 任务 | 验收 | 状态 |
|---|---|---|---|
| M1a | `b2q serve`（FastAPI：/recall /node /healthz + API key + 内存索引 + 请求日志） | HTTP 契约测试全绿 | ⏳ |
| M1b | store（sqlite WAL：account/attempt/mastery/next_due/context）+ /log /due | 学情读写回归全绿 | ⏳ |
| M1c | R4：`b2q index`（服务器跑）+ recall 接向量路 | gold 经 HTTP 评测 **Recall@5 ≥ 80%** | ⏳ |
| M1d | 部署：172.20.4.209 docker compose + 部署脚本（push→pull→restart）。**SSH 已通（ssh localgpu），模型下载源已验证** | 一条命令起服务 | ⏳ 就绪 |

交付：v0.2.0 tag + OpenAPI schema。怎么做：本地写 → push → 服务器 pull 重启 → 评测直连 HTTP。

## M2 场景层最小闭环（ask 先行） ⏸ 等待 M1

- 六种输出模板 → ask skill（WorkBuddy 形态）
- /section /context 端点；失联降级话术
- 验收：10 轮模拟对话，答案带页码依据、学情落库
- 交付：ask skill 可安装 + 演示

## M3 生产层成型 + 制书第二册 ⏸ 等待 M1 + 用户裁定

- 裁定辅助（candidates ↔ Excel）、发布工具（含回滚）、巡检脚本、备份 cron
- **⚠️ 用户介入点：pending-review.md A/B 裁定 → graph 冻结 → index → 发布演练**
- 验收：制书全流程走通（含一次回滚演练）
- 交付：ops-runbook.md + v0.3.0

## M4 全场景 + 内网试用 ⏸ 等待 M2/M3

- learn/drill/review skill + 邀请码 + context 跨设备
- 内网试用 3–10 名学生
- 验收：第一份未命中巡检报告 + 试用反馈
- 交付：v0.4.0 + 试用报告

## M5 公网与多平台（触发式，不预做） ⏸ 触发条件 = M4 试用验证价值

- 公网化（HTTPS/域名/API key/限流）+ 豆包适配层 + 版权控制
- 明确不预做：学情报表、Gitea、GPU 推理、离线场景

## 旧计划映射（S1–S4 作废）

S1 剩余（裁定）→ M3 ｜ S2 剩余（R4）→ M1 ｜ S3/S4 → 被 M2/M4 服务化形态取代。

## 依赖与风险

- M1 不依赖用户裁定，可立即开工
- graph 冻结依赖 pending-review 裁定；评测基准依赖 gold 冻结（用户过目）
- R4 需服务器下载 bge 模型（hf-mirror 可达已验证）；SSH 免密已通（localgpu）
