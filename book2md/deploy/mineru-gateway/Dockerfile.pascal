# ============================================================
# MinerU 4.x — NVIDIA Pascal (TITAN X / GTX 10系, CC 6.1) 定制镜像
#
# 三个关键决策：
# 1) 基础镜像用 CUDA 12.6（自带 cuda-compat-12-6，
#    前向兼容驱动 535/R525+；旧镜像 cu129/13.0 无 Pascal 内核，804 无解）
# 2) torch 锁 cu126 构建 —— 最后一个仍带 sm_61 内核的 CUDA 版本
#    （cu128/cu129 已移除 Pascal；MinerU 要求 torch>=2.7 → 选 2.8.0+cu126）
# 3) 不安装 vLLM（Pascal 不支持），跑 basic 档：纯小模型 GPU 管线，
#    layout + OCR + 公式(PP-FormulaNet_plus-M，4.x torch 档实装，ModelScope 仓
#    OpenDataLab/MinerU-4_models_torch 文件树为准；旧注释 UniMERNet 系 2.x
#    pipeline 时代配置) + 表格 全部在 GPU 上执行
# ============================================================
FROM docker.m.daocloud.io/nvidia/cuda:12.6.2-runtime-ubuntu22.04

# ---- 系统依赖：apt 换阿里云源 + 安装 python3.12（deadsnakes）----
# DEBIAN_FRONTEND=noninteractive + debconf 预选时区：
# python3.12 依赖链会带入 tzdata，默认安装时弹交互式时区选择，
# 构建环境无终端会卡死——必须关掉交互并预设 Asia/Shanghai
RUN sed -i 's|http://security.ubuntu.com|https://mirrors.aliyun.com|g; s|http://archive.ubuntu.com|https://mirrors.aliyun.com|g' /etc/apt/sources.list && \
    echo 'tzdata tzdata/Areas select Asia' | debconf-set-selections && \
    echo 'tzdata tzdata/Zones/Asia select Shanghai' | debconf-set-selections && \
    DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 ca-certificates curl software-properties-common tzdata && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3.12-dev && \
    ln -sf /usr/bin/python3.12 /usr/local/bin/python3 && \
    ln -sf /usr/bin/python3.12 /usr/local/bin/python && \
    python3.12 -m ensurepip --upgrade && \
    python3.12 -m pip install --upgrade pip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 确保优先使用镜像自带的 cuda-compat-12-6（驱动 535 前向兼容的关键）
ENV LD_LIBRARY_PATH=/usr/local/cuda/compat:${LD_LIBRARY_PATH}

# ---- Python 依赖：MinerU[torch] + 锁死 cu126 版 torch/torchvision ----
# （--extra-index-url 让 nvidia-* 12.6 运行库从 PyTorch 源解析；
#   torch/torchvision 必须同时锁定，否则 pip 会拉最新 cu128 构建 = Pascal 不可用）
RUN python3 -m pip install -U --no-cache-dir \
        'mineru[torch]>=4.0,<5' \
        torch==2.8.0+cu126 torchvision==0.23.0+cu126 \
        -i https://mirrors.aliyun.com/pypi/simple \
        --extra-index-url https://download.pytorch.org/whl/cu126

# ---- 运行时配置：小模型走 torch(GPU)；basic 档不需要 VLM ----
ENV MINERU_MODEL_SOURCE=modelscope \
    MINERU_MODEL_SMALL_BACKEND=torch \
    MINERU_MODEL_VLM_ENGINE=llama-cpp

# ---- 预下载 basic 档模型（torch 小模型包，ModelScope 源，约 1-2 GB）----
RUN mineru-kit models download --tier basic --small-backend torch -s modelscope

# 与官方镜像一致：启动时切换到本地权重，不联网
ENTRYPOINT ["/bin/bash", "-c", "export MINERU_MODEL_SOURCE=local && exec \"$@\"", "--"]
