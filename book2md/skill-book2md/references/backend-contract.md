# 网关契约速查（references/backend-contract.md）

权威版本在核心包 `docs/backend.md`（含探测记录）；本文件是技能壳侧的速查卡。
冲突时以 docs/backend.md 为准。

## 端点与调用

- 网关：`http://127.0.0.1:8000`（自托管 MinerU 服务；版本**待确定**，探测记录见 backend.md）
- 端点配置优先级：环境变量 `B2M_BACKEND_API` > `b2m config set backend_endpoint`，**禁止硬编码**
- 健康检查：`GET {endpoint}/version`
- 解析请求：`POST /v1/file_parse?tier=basic&response_format=zip&wait_timeout=900&page_range=N-M`

## 返回 zip 契约（适配器消费前提）

| 项 | 值 |
|---|---|
| 布局 | 根 `markdown.md` 或 `0001/` 子目录（两种均兼容） |
| 页码映射 | `middle_json.json`：`pages[].page_idx`（0 基绝对页号）+ `blocks[].type=="page_number"` |
| 图片命名 | `page_K_*`——**跨块不稳定，页号不可当物理页用**（详见 ocr-patterns.md §二） |

## 状态与处置

- 端点未配置 → 退出码 30（NO_ENDPOINT）：提示用户设环境变量或 config
- 网关不可达 → 退出码 30（GATEWAY_UNREACHABLE）：离线命令（run/scan/report）仍可用
- 抽取失败块 → 账本 `ledger.json` 记 pending，**断点续跑**：重跑同一命令自动跳过已完成块
- 版本指纹：contract.json `meta.backend` 记录网关指纹；`b2m baseline run` 防静默漂移
