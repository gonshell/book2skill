# MinerU 自托管实操手册

> **版本**：v1.3 · 2026-10-26（补模型落地路径 `/root/.mineru/models/`，§8 六项全部销账）
> **版本历史**：v1.2 · 2026-10-26（登录网关机：GPU、docker run 参数、wrapper 来源）｜v1.1 · 2026-10-26（远程：版本 4.0.12、8/8 sha256、端点面/限额）｜v1.0 · 2026-10-25（首版）
> **定位**：在本组织内网（GPU 服务器）自托管 MinerU 文档解析服务的**完整复现手册**——从裸机 Docker 构建、模型离线部署、已知崩溃修复，到服务接入契约。
> **证据来源**：本手册全部内容来自实际部署留痕（`deploy/mineru-gateway/Dockerfile.pascal`、`deploy/mineru-gateway/patch3/4/5_mineru_image.py`、`deploy/mineru-gateway/test_patch5.py`、`docs/backend.md`）与 ModelScope API 实时核实（2026-10-25）。
> **标注约定**：所有不确定信息一律以 **【待核实】** 标记，并附核实途径；禁止把推测当事实。已核实的标注 **【已核实】** 并注明来源。

---

## 目录

1. [背景与硬件约束](#1-背景与硬件约束)
2. [镜像构建：Dockerfile 逐段精讲](#2-镜像构建dockerfile-逐段精讲)
3. [模型仓与离线部署](#3-模型仓与离线部署)
4. [启动与 CUDA 验证](#4-启动与-cuda-验证)
5. [裁剪崩溃修复：补丁迭代实录](#5-裁剪崩溃修复补丁迭代实录)
6. [服务化与接入契约](#6-服务化与接入契约)
7. [版本锁定与运维纪律](#7-版本锁定与运维纪律)
8. [待确认清单](#8-待确认清单网关恢复后采集)
- [附录 A：踩坑索引](#附录-a踩坑索引)
- [附录 B：相关文件清单](#附录-b相关文件清单)

---

## 1. 背景与硬件约束

### 1.1 为什么自托管

教材转换涉及整本书的版权内容，必须保证**数据不出组织**。因此选择 MinerU 开源引擎自托管（内网地址 `127.0.0.1:8000`），而非公有云 API。【已核实，见 backend.md §1】

### 1.2 GPU 硬约束：Pascal 老卡【已核实，Dockerfile.pascal 头部注释 + 2026-10-26 `nvidia-smi` 实测】

部署目标卡为 **NVIDIA TITAN X（Pascal 架构，Compute Capability 6.1）**。这决定了全部三个技术决策：

| 约束 | 后果 |
|---|---|
| CUDA 12.8/12.9/13.x 已**移除 Pascal 内核**（sm_61） | 基础镜像必须选 CUDA 12.6（最后一个带 Pascal 支持的线），报错表现为 **804 错误（无解，换镜像）** |
| PyTorch cu128/cu129 构建不再编译 sm_61 内核 | torch 必须锁 **cu126** 构建，且与 torchvision **同时锁**（否则 pip 自动拉最新 cu128 = 前功尽弃） |
| Pascal 不支持 vLLM | 不安装 vLLM，跑 **basic 档**：纯小模型 GPU 管线（版面 + OCR + 公式 + 表格全部 GPU 执行） |

**实测硬件规格**（网关机 `nvidia-smi --query-gpu`）：

| 项 | 值 |
|---|---|
| GPU | **2 × NVIDIA TITAN X (Pascal)**，各 **12,288 MiB（12 GB）** |
| 驱动 | **535.309.01**（`nvidia-smi` 报 CUDA 12.2 上限，容器内 12.6.2 靠 minor version compatibility，见 §4.2） |
| 算力 / 功耗 | CC **6.1** / 250 W |
| 实际占用 | basic 档解析时 GPU0 仅 **≈784 MiB**（单进程），GPU1 **完全闲置**——即双卡并未利用 |
| 并发能力 | wrapper 限额 `max_concurrent_jobs: 1`（§6.3）；GPU 显存余量充足，理论上可再起实例，但需先过基准回归 |

> **对 backend.md "basic 档需 6–8 GB 显存、算力 ≥7.0" 经验值的修正**：实测 CC 6.1 + **784 MiB** 就跑通 basic 档，原文的算力下限与显存估算均过于保守（显存高估约 8–10 倍）。以实测为准。若需提高并发，瓶颈不在显存而在单进程串行（且 Pascal 无 vLLM）。

---

## 2. 镜像构建：Dockerfile 逐段精讲

完整文件：`deploy/mineru-gateway/Dockerfile.pascal`【已核实，全文如下】。

### 2.1 三个关键决策（再看一遍，构建前必须理解）

1. **基础镜像 = `nvidia/cuda:12.6.2-runtime-ubuntu22.04`**
   自带 `cuda-compat-12-6`，对驱动 **535/R525+** 前向兼容；更新的镜像（cu129/13.0）无 Pascal 内核，804 无解。
2. **torch = `2.8.0+cu126`、torchvision = `0.23.0+cu126`（双双锁死）**
   MinerU 要求 torch≥2.7；2.8.0+cu126 是最后一个仍带 sm_61 内核的构建。
3. **不装 vLLM，跑 basic 档**
   Pascal 不支持 vLLM；basic 档 = 纯小模型 GPU 管线，无需 VLM 推理引擎。

### 2.2 系统依赖段（每行都有踩坑原因）

```dockerfile
FROM docker.m.daocloud.io/nvidia/cuda:12.6.2-runtime-ubuntu22.04

# apt 换阿里云源 + 非交互预选时区（见附录 A 坑 #1）
RUN sed -i 's|http://security.ubuntu.com|https://mirrors.aliyun.com|g; s|http://archive.ubuntu.com|https://mirrors.aliyun.com|g' /etc/apt/sources.list && \
    echo 'tzdata tzdata/Areas select Asia' | debconf-set-selections && \
    echo 'tzdata tzdata/Zones/Asia select Shanghai' | debconf-set-selections && \
    DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 ca-certificates curl software-properties-common tzdata && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3.12-dev && \
    ln -sf /usr/bin/python3.12 /usr/local/bin/python3 && \
    ln -sf /usr/bin/python3.12 /usr/local/bin/python && \
    python3.12 -m ensurepip --upgrade && \
    python3.12 -m pip install --upgrade pip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# cuda-compat 优先加载——驱动 535 前向兼容的关键
ENV LD_LIBRARY_PATH=/usr/local/cuda/compat:${LD_LIBRARY_PATH}
```

### 2.3 Python 依赖段（锁版本的核心）

```dockerfile
# --extra-index-url 让 nvidia-* 12.6 运行库从 PyTorch 源解析；
# torch/torchvision 必须同时锁定，否则 pip 拉最新 cu128 构建 = Pascal 不可用
RUN python3 -m pip install -U --no-cache-dir \
        'mineru[torch]>=4.0,<5' \
        torch==2.8.0+cu126 torchvision==0.23.0+cu126 \
        -i https://mirrors.aliyun.com/pypi/simple \
        --extra-index-url https://download.pytorch.org/whl/cu126

ENV MINERU_MODEL_SOURCE=modelscope \
    MINERU_MODEL_SMALL_BACKEND=torch \
    MINERU_MODEL_VLM_ENGINE=llama-cpp

# 预下载 basic 档模型（ModelScope 源）
RUN mineru-kit models download --tier basic --small-backend torch -s modelscope

# 与官方镜像一致：启动时切换本地权重，运行期不联网
ENTRYPOINT ["/bin/bash", "-c", "export MINERU_MODEL_SOURCE=local && exec \"$@\"", "--"]
```

### 2.4 构建命令【✅ 镜像 tag 已实测核实；构建命令行本身未留痕，下列为等价复现】

```bash
docker build -t mineru:pascal -f deploy/mineru-gateway/Dockerfile.pascal .
```

> 现网容器用的是 **`mineru:pascal`**（`docker inspect` 实测），手册早期推导的 `mineru-pascal:4.x` 与之不符——**以 `mineru:pascal` 为准**（tag 不带版本号，故升级/回滚必须另打 tag 或在镜像 ID 上做记录，否则会丢失版本对应关系）。

> **MinerU 版本说明**：安装约束 `>=4.0,<5`【已核实，Dockerfile】；实际装到的**精确版本 4.0.12**【已核实 2026-10-26，网关 `/v1/health` 返回 `"version":"4.0.12"`，`/v1/tiers`、`/v1/models` 三处一致】。backend.md 中"mineru 2.x 世代"的备注与此矛盾，**以实测为准**（backend.md 该备注写于 Dockerfile 复盘之前）。

---

## 3. 模型仓与离线部署

### 3.1 官方模型仓【已核实，ModelScope API 2026-10-25】

| 项 | 值 |
|---|---|
| 仓库 | **`OpenDataLab/MinerU-4_models_torch`**（MinerU 官方维护者发布） |
| 链接 | https://www.modelscope.cn/models/OpenDataLab/MinerU-4_models_torch |
| 镜像 | https://gitcode.com/OpenDataLab/MinerU-4_models_torch |
| 许可证 | Apache License 2.0 |
| 仓库总大小 | **894,884,928 B ≈ 854 MB**（API 实测；Dockerfile 注释"1–2 GB"为高估，实际更小） |
| 任务标签 | document-understanding |
| 模型卡片 | **官方未填写介绍**（"贡献者未提供模型介绍"）——以下清单来自**仓库文件树**，比卡片更权威 |

下载命令（与 Dockerfile 内一致）：

```bash
mineru-kit models download --tier basic --small-backend torch -s modelscope
# 或直接 SDK 快照下载：
python -c "from modelscope import snapshot_download; snapshot_download('OpenDataLab/MinerU-4_models_torch')"
```

### 3.2 basic 档（torch 小模型）模型清单【4 模块 8 权重，与官方仓文件树核对一致；8/8 sha256 已核实】

| 模块 | 模型 | 仓库内路径 | 格式 | 大小 | sha256【8/8 已核实，ModelScope API 2026-10-26】 |
|---|---|---|---|---|---|
| 版面检测 | **PP-DocLayoutV2**（DETR 架构，backbone hgnet_v2_L；25 类版面元素 + 阅读顺序预测） | `Layout/PP-DocLayoutV2/model.safetensors` | safetensors | 214,798,436 B | `e60f3725aeedc88fd319416ef166bda79171a41516a301c27cab9132dc2739d2` |
| 公式识别 | **PP-FormulaNet_plus-M** | `MFR/pp_formulanet_plus_m/PP-FormulaNet_plus-M.pth` | pth | 617,465,525 B | `bd9d40fd9c7759805e93cb54f14f5e91448a80b14aadc2bfb25c4c948b2974e8` |
| 文字检测 | PP-OCRv6 tiny det | `OCR/paddleocr/ch_PP-OCRv6_tiny_det_infer.safetensors` | safetensors | 1,786,412 B | `cae3c88d2a9902fd0293e6b17990428f54bfa7ec98f800a4368e95423a754d16` |
| 文字识别 | PP-OCRv6 small rec | `OCR/paddleocr/ch_PP-OCRv6_small_rec_infer.safetensors` | safetensors | 21,204,736 B | `f65a332afe5aa663f0b9d5706f4ae8457b5b4058a842d5c1eb22df505c27d642` |
| 印章检测 | PP-OCRv4 seal det | `OCR/paddleocr/seal_PP-OCRv4_det_infer.pth` | pth | 14,506,268 B | `a7777ca66448ab90948ce5a3257e4c959d6eacf0489fbadd5133dbe8f89662ae` |
| 表格分类 | PP-LCNet x1.0 | `Table/PP-LCNet_x1_0_table_cls.onnx` | onnx | 6,776,877 B | `c84bf1d79c1c74d534b5b12adb14dd12151c42f7ae3e4be4f1042b830f80b949` |
| 表格结构 | SLANet-plus | `Table/slanet-plus.onnx` | onnx | 7,758,305 B | `d57a942af6a2f57d6a4a0372573c696a2379bf5857c45e2ac69993f3b334514b` |
| 表格结构(UNet) | UnetStructure | `Table/unet.onnx` | onnx | 8,335,007 B | `0ea48d3a17e35ef5c2e498a5e799566073234d39b1079ca21d9f4fafe73c6d20` |

> ⚠️ **重要更正**：`Dockerfile.pascal` 头部注释写公式模型为 "UniMERNet"——那是 MinerU 2.x/3.x pipeline 时代的配置。**4.x torch 档实际使用 PP-FormulaNet_plus-M**（官方仓文件树为准）。Dockerfile 注释已过时，本手册以官方仓为准；Dockerfile 注释可自行顺手修正。
> 8 项 sha256 全部来自 ModelScope API 文件清单（`/api/v1/models/OpenDataLab/MinerU-4_models_torch/repo/files`），搬运后仍应按 §3.3 逐文件校验落地副本。

### 3.3 完整性校验（离线搬运后必做）

模型落地根目录（实测，见 §3.4）：容器内 **`/root/.mineru/models/MinerU-4_models_torch/`**，其下按 `Layout / MFR / OCR / Table` 分模块。

```bash
# 现网容器里校验（宿主机终端执行，命令跑在容器内）
docker exec mineru-api sha256sum \
  /root/.mineru/models/MinerU-4_models_torch/Layout/PP-DocLayoutV2/model.safetensors
# 期望：e60f3725aeedc88fd319416ef166bda79171a41516a301c27cab9132dc2739d2

# 离线搬运到新机的场景：在目标机（非容器）上，换成实际落地路径
sha256sum /path/to/models/Layout/PP-DocLayoutV2/model.safetensors
```

```bash
# 一次性全量校验 8 个权重（现网容器）
docker exec mineru-api bash -lc '
cd /root/.mineru/models/MinerU-4_models_torch
find . -type f \( -name "*.safetensors" -o -name "*.pth" -o -name "*.onnx" \) -exec sha256sum {} \;'
# 逐行对照 §3.2 表
```

### 3.4 完全离线部署路径

1. 在有网机器执行 `snapshot_download('OpenDataLab/MinerU-4_models_torch')`（或 `mineru-kit models download`）；
2. 整目录拷贝到内网机（U 盘 / 内网共享均可）；
3. 运行期环境变量切本地：

```bash
export MINERU_MODEL_SOURCE=local
```

（Dockerfile 的 ENTRYPOINT 已内置这一步——容器内启动自动切 local，运行期零联网。）

> ⚠️ **实测部署形态（2026-10-26）：模型烘焙在镜像内，零挂载**。`docker inspect` 显示
> `MOUNTS=[]`，`/root/.cache/modelscope` 仅 8 KB（空壳）——模型既不在缓存目录、也不在
> volume 上，而是**打进 `mineru:pascal` 镜像层**。**实测落地路径**：
>
> ```
> /root/.mineru/models/MinerU-4_models_torch/{Layout,MFR,OCR,Table}/...
> ```
>
> 即 `MINERU_MODEL_SOURCE=local` 的默认根目录是 **`/root/.mineru/models/`**（不是
> `~/.cache/modelscope`），其下以 `<仓库名>/` 再分模块。运维含义：
> ① 换模型 = **重建镜像**（或 `docker cp` 进容器，但容器一重建就丢），不能像常见做法那样
> 只换挂载目录；② 回滚也靠镜像 tag，镜像体积因此偏大；
> ③ 校验落地副本必须 `docker exec <容器> sha256sum /root/.mineru/models/...`，宿主机路径无效。
>
> **宿主 vs 容器（易混）**：`docker exec` 虽在宿主机终端敲，命令却**跑在容器内**；
> 这些模型目录在宿主机文件系统上**不可见**（无挂载），只能经 `docker exec` / `docker cp` 访问。

### 3.5 历史对照【已核实，ModelScope API】

MinerU 2.x 时代旧仓 `opendatalab/PDF-Extract-Kit`（8.8 GB，含 StructEqTable/UniMERNet/TableMaster 等旧管线模型，Apache-2.0，2024-10 最后更新）仍在——**不要下错**。4.x torch 档请认准 `MinerU-4_models_torch`。

---

## 4. 启动与 CUDA 验证

### 4.1 启动【✅ 实测核实 2026-10-26，`docker inspect` 采集】

现网容器（`Up 4 days`）：容器名 **`mineru-api`**，镜像 **`mineru:pascal`**，无任何挂载。等价的完整启动命令：

```bash
docker run -d --name mineru-api --gpus all -p 8000:8000 \
  --restart unless-stopped \
  mineru:pascal \
  mineru-kit api-server --host 0.0.0.0 --port 8000 --tier basic --disable-image-analysis
```

| 参数 | 实测值 | 说明 |
|---|---|---|
| 镜像 / 容器 | `mineru:pascal` / `mineru-api` | 注意 tag 是 `pascal`，非本手册早期推导的 `mineru-pascal:4.x` |
| `--gpus` | `DeviceRequests{Count:-1, Capabilities:[["gpu"]]}` = `--gpus all` | 双卡均可见 |
| 端口 | `0.0.0.0:8000->8000/tcp` | 对外暴露 |
| **挂载** | **`MOUNTS=[]`——零挂载** | 模型权重**烘焙在镜像内**，不靠 volume（见 §3.4 影响） |
| restart | `unless-stopped` | 崩溃/重启自动拉起 |
| runtime | `runc` | 非 nvidia runtime 全程接管，靠 `--gpus` 注入 |
| ENTRYPOINT | `/bin/bash -c 'export MINERU_MODEL_SOURCE=local && exec "$@"' --` | 启动即把模型源切 local（覆盖镜像 ENV 的 `modelscope`） |
| CMD | `mineru-kit api-server --host 0.0.0.0 --port 8000 --tier basic --disable-image-analysis` | **`--tier basic` 在进程级锁定**，与 API 契约一致；`--disable-image-analysis` 关闭图片分析（无 VLM 的必然选择） |

镜像 ENV 关键项（实测）：`MINERU_MODEL_SOURCE=modelscope`（被 ENTRYPOINT 覆盖为 local）、`MINERU_MODEL_SMALL_BACKEND=torch`、`MINERU_MODEL_VLM_ENGINE=llama-cpp`（未启用）、`CUDA_VERSION=12.6.2`。

> ⚠️ **`docker exec` 环境变量陷阱**：`docker exec mineru-api printenv` 显示 `MINERU_MODEL_SOURCE=modelscope`，这是因为 exec 起的是**新进程**，不继承 ENTRYPOINT 里的 `export`；**主进程才是 local 模式**。排查"模型从哪来"时不能据 exec 的环境变量下结论。

**服务进程形态**✅：wrapper 不是自研代码，而是 **MinerU 官方 `mineru-kit api-server` 子命令**（解释 §6.3 的 FastAPI 19 端点与 `/docs`）。容器内进程结构：1 个主进程 `python3 /usr/local/bin/mineru-kit api-server ...` + 3 个 `multiprocessing.spawn` worker（PID 111–114）。

### 4.2 CUDA 生效验证【已核实，工艺流程.md 留痕 + 2026-10-26 现网复核】

首次启动曾出现 **libcuda 加载路径问题**，排查手段为 `LD_LIBRARY_PATH`。重建后的确认标志：日志中出现 **`CUDA: True`**。

> ⚠️ **与踩坑记录的出入（以实测镜像为准）**：现网容器 ENV 的 `LD_LIBRARY_PATH` 实测为 `/usr/lib/x86_64-linux-gnu`，**未见 `/usr/local/cuda/compat` 前置**——即附录 A 坑 4 的解法在最终跑通的镜像里并未以该形式生效（`libcuda` 由 nvidia-container 注入到系统库路径）。手册早期写的"已在 Dockerfile 固化 compat 前置"与实际镜像不符，Dockerfile 若仍带该行属冗余，不必据此排障。

**驱动/CUDA 版本关系**（易踩坑）：`nvidia-smi` 报 `CUDA Version: 12.2`（驱动 535.309.01 支持的上限），而容器内运行时是 **CUDA 12.6.2**——两者共存靠 **CUDA minor version compatibility**（12.x 系列内驱动向下兼容）；镜像的 `NVIDIA_REQUIRE_CUDA` 声明也明确接受 `driver>=535,<536`。据此**不要**误判"容器 CUDA 12.6 必须配 560+ 驱动"。

```bash
# 快速自检（容器内）
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# 期望：True TITAN X(...)；False = 回看 §2.1 的三个决策是否被破坏
```

---

## 5. 裁剪崩溃修复：补丁迭代实录

### 5.1 症状【已核实】

OCR 图片裁剪环节（`mineru/model/ocr/image.py`）中：

```python
img_crop_width  = int(max(np.linalg.norm(points[0] - points[1]), np.linalg.norm(points[2] - points[3])))
img_crop_height = int(max(np.linalg.norm(points[1] - points[2]), np.linalg.norm(points[3] - points[0])))
```

四点坐标退化（如整块重叠）时 `max(...)` 可为 0/负值 → `int()` 后得到非法裁剪尺寸 → **运行中崩溃**。

**修复思路**：包一层下限保护 → `int(max(1.0, round(max(...))))`。

### 5.2 三次迭代（弯路即教材）【已核实，patch3/4/5 源码】

| 版本 | 策略 | 结局 |
|---|---|---|
| **patch3** | 双行**精确字符串替换** | ① 曾因目标文件被外部改坏而 MISS（用 pip 同版本 `--force-reinstall --no-deps` 恢复后重打成功）；② 行布局/空白差异导致脆弱 |
| **patch4** | 正则匹配（容空白差异、容尾注释） | 稳定性提升，但正则仍有语义盲区（如多行换行写法） |
| **patch5**（**最终版**） | **AST 级**：解析源码→定位 `img_crop_width/height` 的 `int(max(a,b))` 赋值节点→重写 | 幂等（已打过自动跳过）、先备份 `.bak-prepatch`、写后语法验证 + import 冒烟、失败自动回滚 |

`test_patch5.py` 用 7 种行写法变体（A 原版 / B 顺序交换 / C 无空格 / D 尾注释 / E 多行 / F 逗号索引 / **G 变量名错——应失败**）本地验证补丁行为与数学语义（退化点 → (1,1)，正常点 → (30,10)）。

### 5.3 应用补丁（patch5 全文见 `deploy/mineru-gateway/patch5_mineru_image.py`，此处列用法）

```bash
# 先把 deploy/mineru-gateway/patch5_mineru_image.py 拷进容器，再在容器内执行
python patch5_mineru_image.py
# 期望输出链：FOUND: [('img_crop_width', ..), ('img_crop_height', ..)]
#   → REPLACE lines .. → WRITTEN | clamp-count: 2 | backup: ..bak-prepatch
#   → IMPORT-SMOKE: OK → PATCH-DONE

# 幂等：重复执行输出 ALREADY-PATCHED, nothing to do（安全）
```

**退出码语义**（运维排障用）【已核实，patch5 源码】：

| 码 | 含义 | 处置 |
|---|---|---|
| 0 | 已打或打成功 | — |
| 2 | 磁盘文件语法损坏 | 脚本已自动 `pip install --force-reinstall --no-deps mineru==<当前版本>` 恢复，**重新执行本命令** |
| 3 | 找不到两个赋值（结构大改） | 看脚本 dump 的 88–106 行，人工确认新结构 |
| 4 | 写后 clamp 计数 < 2 | 自动回滚 |
| 5 | import 冒烟失败 | 自动回滚 |

### 5.4 运维纪律【强制】

- **pip 重装 / 镜像重建 / mineru 升级后，补丁会消失，必须重打**（backend.md §3 已登记 patch_id: `img-crop-min1`）；
- 重打前先跑 `test_patch5.py` 变体测试（改 mineru 版本后行结构可能变，G 变体应失败、A–F 应通过）；
- 补丁文件与 `.bak-prepatch` 备份一起留档。

---

## 6. 服务化与接入契约

以下为**客户端实测契约**【已核实，run_blocks.py 实际调用 + docs/backend.md §1–2】；服务端为 **MinerU 官方 `mineru-kit api-server`**（非自研 wrapper），框架/端点面/启动参数均已核实（§4.1、§6.3）。

### 6.1 解析端点

```
GET/POST http://127.0.0.1:8000/v1/file_parse
         ?tier=basic&response_format=zip&wait_timeout=900&page_range={s}-{e}
```

| 参数 | 值 | 说明 |
|---|---|---|
| `tier` | `basic`（**锁定**） | OCR 质量档位直接决定下游 S1–S20 修复规则的适用前提；变更必须先过基准回归（`b2m baseline run`） |
| `response_format` | `zip`（锁定） | 返回 md + images + middle_json 打包 |
| `wait_timeout` | `900` 秒 | 单块同步等待；整书提交会超时，**必须分块** |
| `page_range` | `N-M` 物理页 | 分块 / 断点续跑 / 试转换都依赖它 |

### 6.2 客户端调用纪律【已核实，backend.md §4】

1. **分块提交**：40 页/块；
2. **限流退避**：HTTP 403 → 0/30/90 s 三段退避；
3. **ledger 断点续跑**：每块记 `pending/done/failed`，失败重跑只补 pending；
4. **zip 输出契约**：根 `markdown.md` 或 `0001/` 子目录（两种均兼容）；图片命名 `page_K_*`——**⚠️ K 语义不稳定，不可当物理页号用**（实测跨块不一致：块 47-86 为绝对页−1，块 87-114 ≈ 绝对页）。唯一安全不变量：合并重编号后 **md 引用与图片文件名同步改名、一一对应**（真实样例金样本：`tests/fixtures/blocks/选择性必修第二册/block_87-114.zip`）；
5. **物理页映射唯一来源**：`middle_json.json` 的 `pages[].page_idx`（0 基绝对页号）+ `blocks[].type=="page_number"`。

### 6.3 服务信息端点【已核实 2026-10-26，网关实测；`/docs`（Swagger UI）开放，OpenAPI 3.1.0】

wrapper 为 **FastAPI**（`title: "MinerU API"`，API 版本 1.0.0），共 19 个端点。无需认证（`/v1/usage` 报 `access_level: anonymous`）。关键信息端点：

| 端点 | 返回要点 |
|---|---|
| `GET /v1/health` | `{"status":"ok","version":"4.0.12","features":{"webhook":false,"output_formats":["markdown","middle_json","structured_content","zip"],"sources":["file_id","url","inline"]}}` —— **`version` 字段即 MinerU 精确版本**，替代缺失的 `/version` |
| `GET /v1/tiers` | 本机实际可服务档位：`flash`、`basic`（current_model 均为 `mineru-4.0.12`；standard/advanced 未列——与 Pascal 无 vLLM 一致） |
| `GET /v1/models` | 虚拟模型 `mineru-4.0.12`：id 只标服务器版本，档位在请求级 `tier` 参数选择 |
| `GET /v1/usage` | 限额契约：1000 页/文件、200 MB/文件、100 文件/任务、**`max_concurrent_jobs: 1`**、文件保留 1 天；计费期自 2026-10-21 起 |

完整端点面快照（19 端点）已存档：`docs/gateway-openapi-20261026.json`。
其余端点：uploads（create/content/complete/cancel）、files（list/get/content/delete）、parse/jobs（create/list/get/delete）、tasks（create/get/delete/result）、`/v1/file_parse`（同步一站式）。

---

## 7. 版本锁定与运维纪律

### 7.1 版本锁定表（后端侧）

| 层 | 钉什么 | 状态 | 值 |
|---|---|---|---|
| 基础镜像 | CUDA 12.6.2-runtime-ubuntu22.04 | ✅ 已核实 | Dockerfile |
| Python | 3.12（deadsnakes） | ✅ 已核实 | Dockerfile |
| MinerU 包 | `>=4.0,<5` 约束 + **精确版本 4.0.12** | ✅ 已核实（网关 /v1/health 三处一致） | §2.4 / §6.3 |
| torch / torchvision | 2.8.0+cu126 / 0.23.0+cu126 | ✅ 已核实 | Dockerfile |
| 模型权重 | `OpenDataLab/MinerU-4_models_torch`（854 MB，8 权重） | ✅ 已核实（**8/8 sha256**） | §3.2 |
| 模型落地路径 | 容器内 `/root/.mineru/models/MinerU-4_models_torch/`（镜像层，宿主不可见） | ✅ 已核实 | §3.3 / §3.4 |
| 服务端补丁 | `img-crop-min1`（§5） | ✅ 已核实，哈希待登记 | patch5 |
| wrapper 框架 | **MinerU 官方 `mineru-kit api-server`**（非自研）：FastAPI"API 1.0.0"，OpenAPI 3.1.0，19 端点，匿名访问 | ✅ 已核实（/openapi.json + docker inspect + ps） | §4.1 / §6.3 |
| 启动参数 | `mineru-kit api-server --host 0.0.0.0 --port 8000 --tier basic --disable-image-analysis`；`--gpus all`、零挂载、`restart unless-stopped` | ✅ 已核实（docker inspect） | §4.1 |
| GPU 规格 | 2 × TITAN X (Pascal) 12 GB，驱动 535.309.01，CC 6.1；basic 档实测占用 ≈784 MiB（单卡） | ✅ 已核实（nvidia-smi） | §1.2 |

### 7.2 纪律【强制，继承 backend.md】

1. **升级前必跑基准回归**：`b2m baseline run` 是**唯一**的漂移防线——网关侧任何升级（含模型权重更新）前先跑，逐指标比对通过才允许升级（已知：图片数量类指标天然有 run 间噪声，字符指标才是稳定锚点）；
2. **provenance 禁占位假值**：版本未核实期间 `provenance.json` 相关字段显式记 `null`；
3. **重建镜像 = 重打补丁 + 重校模型 sha256**（§5.4 + §3.3）；
4. tier/response_format 是**契约**，改动等同破坏下游修复规则前提。

---

## 8. 待确认清单（2026-10-26 全部销账）

网关恢复后分两轮核实：**远程 API 3 项 + 登录网关机 3 项**，全部完成：

| # | 待确认项 | 状态 | 核实方式与结论 |
|---|---|---|---|
| 1 | MinerU 精确版本号 | ✅ **4.0.12** | `curl /v1/health` → `version`；`/v1/tiers`、`/v1/models` 交叉一致 |
| 2 | 8 个模型权重完整 sha256 | ✅ **8/8** | ModelScope API `repo/files`，全量回填 §3.2 |
| 3 | wrapper 实现与版本端点 | ✅ **已核实** | **官方 `mineru-kit api-server`**（非自研），启动命令与进程结构见 §4.1；版本在 `/v1/health`（无 `/version`） |
| 4 | GPU 型号 / 显存 / 驱动 | ✅ **已核实** | `nvidia-smi`：2 × TITAN X (Pascal) 12 GB，驱动 535.309.01，CC 6.1，basic 档占用 ≈784 MiB（§1.2） |
| 5 | docker run 完整参数 | ✅ **已核实** | `docker inspect`：`mineru:pascal`、`--gpus all`、`-p 8000:8000`、**零挂载**、`restart unless-stopped`、CMD 含 `--tier basic --disable-image-analysis`（§4.1） |
| 6 | 模型实际存放路径 | ✅ **已核实** | **容器内 `/root/.mineru/models/MinerU-4_models_torch/`**（`Layout/MFR/OCR/Table` 分模块）；烘焙在镜像层、宿主不可见（§3.3/§3.4） |

采集命令留档（复现用）：

```bash
# 远程（任意可达网关的机器）
curl http://127.0.0.1:8000/v1/health    # 版本 + 能力
curl http://127.0.0.1:8000/v1/tiers     # 实际可服务档位
curl http://127.0.0.1:8000/v1/usage     # 限额契约
curl http://127.0.0.1:8000/openapi.json # 完整端点面（快照：docs/gateway-openapi-20261026.json）

# 网关机宿主机（只读）
CID=$(docker ps -q --filter publish=8000 | head -1)
docker ps --no-trunc --format '{{.Names}}|{{.Image}}|{{.Ports}}|{{.Status}}'
docker inspect "$CID" --format '{{json .HostConfig.PortBindings}} {{json .Mounts}} {{json .HostConfig.DeviceRequests}} {{json .Config.Cmd}}'
nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv
```

---

## 附录 A：踩坑索引

| # | 坑 | 症状 | 解法 | 出处 |
|---|---|---|---|---|
| 1 | tzdata 交互卡死 | docker build 卡在时区选择（无终端） | `debconf-set-selections` 预选 Asia/Shanghai + `DEBIAN_FRONTEND=noninteractive` | Dockerfile |
| 2 | CUDA 804 错误 | 新版 CUDA 基础镜像 + Pascal 卡启动即失败 | 换 CUDA 12.6 镜像（新版已移除 sm_61 内核，无解只能换） | Dockerfile 注释 |
| 3 | pip 拉错 torch 构建 | 装完 `torch.cuda.is_available()=False` | torch/torchvision **同时**锁 `+cu126`，配 `--extra-index-url` pytorch 源 | Dockerfile 注释 |
| 4 | libcuda 加载失败 | 容器内 CUDA 不可用 | `LD_LIBRARY_PATH` 处理（⚠️ 现网镜像实测为 `/usr/lib/x86_64-linux-gnu`，未见 compat 前置，见 §4.2 出入说明） | Dockerfile / 实测 |
| 5 | 运行期联网拉模型 | 内网机解析时静默失败/卡住 | 预下载 + `MINERU_MODEL_SOURCE=local`（ENTRYPOINT 已固化） | Dockerfile / 社区实测 |
| 6 | 补丁目标文件被改坏 | patch3 报 DISK-FILE-BROKEN | patch5 内置 `pip install --force-reinstall --no-deps mineru==<同版本>` 自动恢复 | patch3→5 迭代 |
| 7 | 图片名页号不可信 | 跨块页号语义漂移 | 只信"引用与文件同步改名"不变量，物理页看 middle_json | backend.md §2 |
| 8 | Dockerfile 注释过时 | 公式模型写成 UniMERNet | 4.x torch 档实为 PP-FormulaNet_plus-M，以官方仓文件树为准 | §3.2 更正 |

## 附录 B：相关文件清单

| 文件 | 内容 |
|---|---|
| `deploy/mineru-gateway/Dockerfile.pascal` | 镜像定义（本手册 §2 的完整原文） |
| `deploy/mineru-gateway/patch3_mineru_image.py` / `patch4_…` / `patch5_…` | 补丁三代（patch5 为最终版） |
| `deploy/mineru-gateway/test_patch5.py` | patch5 七变体本地验证 |
| `docs/backend.md` | 网关契约与版本锁定（权威文档） |
| `tests/fixtures/blocks/…/block_87-114.zip` | 真实网关返回样例（金样本） |
| `../../gzsx-md/工艺流程.md` | 五册转换工艺（含启动与 CUDA 验证留痕，历史原件区） |

---

*本手册由工作区部署留痕复盘而成；v1.1 经网关远程实测核实（版本/sha256/端点面），v1.2–v1.3 经网关机实测核实（GPU/启动参数/wrapper 来源/模型落地路径）。**§8 待确认清单已全部销账**；后续如升级 MinerU 或重建镜像，请同步更新 §7.1 锁定表。*
