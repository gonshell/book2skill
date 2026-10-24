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
| 图片命名 | `page_K_*`（K=抽取页序） |
| 页码映射 | `middle_json.json`：`pages[].page_idx` + `blocks[].type=="page_number"` → 物理页映射唯一来源 |
| 适配器职责 | 以上隐式约定由 MinerUAdapter 吸收，归一化为 Canonical Extraction v1（方案 §4.4.2） |

## 3. 版本锁定表（后端侧）

| 层 | 钉什么 | 状态 | 值 |
|---|---|---|---|
| 网关封装版本 | wrapper 版本号（若无则**需加 `/version` 端点**） | ❌ 待网关核实 | — |
| 底层 MinerU 版本 | `mineru` 包版本（patch 脚本经 `importlib.metadata.version("mineru")` 读取过，值在网关机） | ❌ 待网关核实 | — |
| 模型权重 | layout / OCR(PP-OCRv4) / 公式(UniMERNet) / 表格 各 commit/哈希 | ❌ 待网关核实 | — |
| 服务端补丁 | `mineru/model/ocr/image.py` 裁剪维度补丁（`img_crop_width/height → int(max(1.0, round(...)))`），源见工作区 `patch3/4/5_mineru_image.py`（AST 幂等、同版本重装后重新应用） | ⚠️ 已知存在，哈希待登记 | patch_id: `img-crop-min1` |
| GPU 规格 | 型号 / 显存 / 驱动（basic 档经验下限：算力 ≥7.0、显存 6–8GB；并发建议 16GB+） | ❌ 待网关运维核实 | — |

> ⚠️ **MinerU 版本未核实期间的纪律**：`provenance.json` 相关字段显式记 `null`
> （禁止占位假值）；基准回归（`tbp baseline`）在此期间是**唯一**的漂移防线——
> 网关侧任何升级前必须先跑 `baseline run`。

> **核实尝试记录（2026-10-24）**：① patch/test 脚本无版本留痕（运行时读取、未落盘）；
> ② 本机探测网关 `//version /docs /openapi.json` 全部超时，ping 100% 丢包——
> **网关当时不可达**，非"服务不暴露版本"。已知结构信息：pip 安装于
> `/usr/local/lib/python3.12/dist-packages/mineru/`（网关 Python 3.12，mineru 2.x 世代）。
> 补实途径：网关可达后执行 §3 三条命令，或运维加 `/version` 端点。

## 4. 客户端对网关的假设清单（适配器实现依据）

1. 分块提交：40 页/块（run_blocks.py 现值，可配置）
2. 同步等待 + 403 退避 + ledger 续跑
3. zip 内布局 §2；违约 → Canonical Extraction schema 校验失败，退出码 40
4. 端点/tier/超时全部来自 `configs/backends/mineru-remote.json`，**代码零硬编码 IP**
