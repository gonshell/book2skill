# backend.md — MinerU 网关契约与版本锁定

> 状态：2026-10-24 建档。**"已核实"值为实测；"待网关核实"项须由网关运维填写后方可冻结。**
> tbpipe 启动时校验实际指纹 ∈ 本文件允许集合，不符即退出码 40（见 docs/spec-cli.md §3）。

## 1. 网关端点与 API 契约（已核实——源自 run_blocks.py 实际调用）

| 项 | 值 | 说明 |
|---|---|---|
| 端点 | `http://<网关地址>:8000` | 内网自托管（形态一），数据不出组织 |
| 解析端点 | `GET/POST /v1/file_parse` | 整书超时，必须分块提交 |
| 调用串（实测原文） | `/v1/file_parse?tier=basic&response_format=zip&wait_timeout=900&page_range={s}-{e}` | run_blocks.py L76 |
| `tier` | `basic`（**锁定**） | OCR 质量档位直接决定 S1–S20 规则适用前提，变更须过基准回归 |
| `response_format` | `zip`（锁定） | md + images + middle_json 打包 |
| `wait_timeout` | `900` 秒 | 单块同步等待 |
| `page_range` | `N-M` 物理页 | 分块/续跑/试转换依赖此参数 |
| 限流退避 | 403 → 0/30/90s | 继承 run_blocks.py 策略 |
| ledger | 每块 `pending/done/failed` | 断点续跑；**须扩展 backend 指纹字段**（方案 §4.3.6(d)） |

## 2. zip 输出契约（已核实）

| 项 | 值 |
|---|---|
| 布局 | 根 `markdown.md` 或 `0001/` 子目录（两种均兼容） |
| 图片命名 | `page_K_*`（K=抽取页序，**实测 K 语义不稳定，见下 ⚠️**） |
| 页码映射 | `middle_json.json`：`pages[].page_idx` + `blocks[].type=="page_number"` → 物理页映射唯一来源 |
| 适配器职责 | 以上隐式约定由 MinerUAdapter 吸收，归一化为 Canonical Extraction v1（方案 §4.4.2） |

**⚠️ 图片名页号不可作为物理页号依赖（2026-10-25 真实样例对账确认）**：
同一批已验收产物中，块 47-86 的图片名页号 = 绝对页 − 1（page_46…85），
块 87-114 的 ≈ 绝对页（page_100…114）——跨块不一致，MinerU 侧命名不稳定。
因此唯一安全的不变量是：**合并重编号（`s+n-1`）后 md 引用与图片文件名同步
改名、一一对应**；重编号后的页号不保证 ≤ 全书物理页数（已验收产物存在
172–199 > 114 的现象，渲染与阅读不受影响）。契约样例金样本：
`tests/fixtures/blocks/…/block_87-114.zip`（断言见
`tests/test_extraction_contract.py`，说明见 `tests/fixtures/README.md`）。

## 3. 版本锁定表（后端侧）

| 层 | 钉什么 | 状态 | 值 |
|---|---|---|---|
| 网关封装版本 | wrapper 版本号 | ✅ **已核实（2026-10-26 远程）**：FastAPI "MinerU API"，API 版本 1.0.0，OpenAPI 3.1.0，19 端点，匿名访问；端点面快照见 `docs/gateway-openapi-20261026.json` | `/openapi.json` |
| 底层 MinerU 版本 | `mineru` 包版本 | ✅ **已核实（2026-10-26 远程）**：**4.0.12**（`/v1/health` `version` 字段；`/v1/tiers`、`/v1/models` 三处一致；无 `/version` 端点，版本在 `/v1/health`） | `/v1/health` |
| 模型权重 | basic 档 torch 8 权重，官方仓 `OpenDataLab/MinerU-4_models_torch`（854 MB） | ✅ **已核实：8/8 sha256**（ModelScope API 2026-10-26）；明细见工作区《MinerU自托管实操手册》§3.2 | ModelScope API |
| 服务端补丁 | `mineru/model/ocr/image.py` 裁剪维度补丁（`img_crop_width/height → int(max(1.0, round(...)))`），源见工作区 `patch3/4/5_mineru_image.py`（AST 幂等、同版本重装后重新应用） | ⚠️ 已知存在，哈希待登记 | patch_id: `img-crop-min1` |
| GPU 规格 | 型号 / 显存 / 驱动 | ✅ **已核实（2026-10-26 `nvidia-smi`）**：2 × NVIDIA TITAN X (Pascal)，各 12 GB，驱动 535.309.01，CC 6.1；**basic 档实测仅占 ≈784 MiB 单卡**（原文"6–8 GB / 算力 ≥7.0"经验值过于保守，作废） | §1.2 手册 |
| 部署形态 | 镜像 / 启动命令 / 挂载 | ✅ **已核实（2026-10-26 `docker inspect`）**：镜像 `mineru:pascal`，容器 `mineru-api`；`mineru-kit api-server --host 0.0.0.0 --port 8000 --tier basic --disable-image-analysis`；`--gpus all`、`-p 8000:8000`、**零挂载**（模型烘焙进镜像）、`restart unless-stopped` | 手册 §4.1 |
| 服务限额 | 1000 页/文件、200 MB/文件、100 文件/任务、`max_concurrent_jobs: 1`、文件保留 1 天 | ✅ **已核实（2026-10-26 远程）** | `/v1/usage` |

> ⚠️ **版本已核实（4.0.12）后的纪律仍然有效**：`tbp baseline` 是**唯一**的漂移防线——
> 网关侧任何升级前必须先跑 `baseline run`。已知图片数量类指标（悬空引用/缺图）
> 存在 run 间噪声（同版本重抽 18↔21），字符指标（±0.5% 容差）才是稳定锚点；
> `provenance.json` 版本字段自 2026-10-26 起可填 `4.0.12`（源：`/v1/health`）。

> **核实尝试记录**：① 2026-10-24 网关不可达（探测超时、ping 全丢包），当时无法定版本；
> ② 2026-10-26 远程：`/openapi.json`、`/v1/health`、`/v1/tiers`、`/v1/models`、`/v1/usage`
> 实测成功；③ 同日网关机：`docker inspect` + `nvidia-smi` 核实部署形态与 GPU。
> 服务端为 **MinerU 官方 `mineru-kit api-server`**（非自研 wrapper）。
> **唯一残留**：模型在镜像内的精确目录（`MOUNTS=[]`，`~/.cache/modelscope` 为空壳）。

## 4. 客户端对网关的假设清单（适配器实现依据）

1. 分块提交：40 页/块（run_blocks.py 现值，可配置）
2. 同步等待 + 403 退避 + ledger 续跑
3. zip 内布局 §2；违约 → Canonical Extraction schema 校验失败，退出码 40
4. 端点/tier/超时全部来自 `configs/backends/mineru-remote.json`，**代码零硬编码 IP**
