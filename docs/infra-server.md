# infra-server.md — 172.20.4.209 服务器资源规划（book2qa 开发期）

> 服务器现状：MinerU 网关已运行（docker，端口 8000，GPU 2×TITAN X 12GB，
> 驱动 535.309.01，模型在 `/root/.mineru/models/`）——证明该机 docker 与
> HuggingFace/ModelScope 下载链路可用。新增服务沿用同一模式：docker 容器、
> 只监听内网、/opt 分区落盘。
>
> **总原则：服务器是「文件仓库 + 备份仓 + 可选计算」，不是必需运行时。**
> book2qa 的客户端保持纯本地（检索/推理在学生机上跑），服务器只承担
> 一次性下载源、异地备份、（可选）重计算三类角色。

---

## 1. 目录布局

```
~/book2qa/
├── models/                 # 模型文件仓库（一次性下载源）
│   └── bge-small-zh-v1.5-onnx/     # ~150MB，R4 用
├── backup/                 # 异地备份（原待办：gzsx-md 是孤本）
│   ├── gzsx-md/            #   526MB → 压缩 ~300MB（对账裁判，丢了全废）
│   ├── book2skill-repo/    #   git 裸仓库镜像（push 备份）
│   └── workbuddy-memory/   #   .workbuddy/memory/ 私有内容，不进 GitHub
├── git/                    # （阶段2 可选）Gitea 容器数据卷
└── docker/                 # compose 文件与配置
```

## 2. 服务清单（按阶段）

### 阶段 1：模型下载源（R4 前置，本周）

| 项 | 说明 |
|---|---|
| 下载 bge ONNX | 服务器上 `huggingface-cli` / `modelscope` / 直接 wget 均可（该机已验证能下 MinerU 模型） |
| 静态文件服务 | **caddy**（单二进制 + 自动目录页）或 `docker run nginx`，共享 `~/book2qa/`，监听 8080（避开网关 8000） |
| 用途 | 本地机 `curl http://172.20.4.209:8080/models/...` 拉模型 → 落 `~/.book2qa/models/` |

**架构决策（R4 计算位置）**：模型文件放服务器做下载源，**推理仍在学生机**
（onnxruntime CPU，单条 query 5–20ms）——保持纯本地哲学与低延迟。
服务器 GPU 只在两种情况下启用：① 本地机性能实测不够（备选：服务器起
embedding API 容器，与 MinerU 网关同模式）；② 全五册索引重建想提速。
v1 都不做，只留接口（recall 的 R4 走 HTTP 还是本地 onnxruntime，签名不变）。

### 阶段 2：异地备份（S1 关账前完成，防孤本）

| 项 | 工具 | 频率 |
|---|---|---|
| gzsx-md 526MB | rsync over ssh | 一次性 + 每月 |
| book2skill git 裸仓库 | `git push --mirror` | 每次 milestone |
| .workbuddy/memory/ | rsync | 每周（私有，不进 GitHub） |

### 阶段 3（可选）：内网 Git 第二远端

Gitea 容器（~200MB 镜像）做 `git remote add lan ssh://git@172.20.4.209/...`——
GitHub 之外的备份远端。v1 非必需，GitHub 已够用。

## 3. 客户端/开发工具清单

| 侧 | 工具 | 状态 |
|---|---|---|
| 本地机（开发机） | Python 3.13 + pytest + git + ssh client | ✅ 已有 |
| 本地机 | onnxruntime（`pip install book2qa[embed]`，R4 时装） | 待装 |
| 服务器 | docker（✅ 已有）、caddy/nginx、rsync、huggingface-cli/modelscope | 待装（一次性） |
| 两侧 | ssh 免密（本地机 → 服务器，备份与文件拉取用） | 待配置 |

## 4. 明确不做的

- ❌ 向量数据库 / Milvus / Qdrant——单册 8MB 向量，numpy 暴力内积（serving §1）
- ❌ 服务器常驻推理服务（v1）——学生机 CPU 足够
- ❌ 公网暴露——所有新端口只绑 172.20.x 内网
- ❌ 在服务器上装 Node/渲染栈——渲染在本地（book2md 已跑通）

## 5. 服务器接入（✅ 2026-11-03 已解决）

- SSH：`ssh localgpu`（~/.ssh/config 别名，xiesg@dev-server-1，免密可用）
- sudo 需密码 → **部署用 `~/book2qa/`，不用 /opt**（无需 sudo）
- python3.12.3 + docker（xiesg 在 docker 组，mineru-api 容器已在跑）
- 下载源：hf-mirror.com ✓ / modelscope.cn ✓（均可达）
- 磁盘：233G 总 / 127G 空闲


---

## 附：基建落地记录（2026-11-03 执行完毕）

- 目录：`~/book2qa/{models,data,backup,repo}` 已建
- 运行副本：`repo/` = bundle+scp 方式 clone（**服务器 GitHub DNS 不通**，部署流水线采用
  本地 bundle → scp → 服务器 clone/pull，已验证 1.3MB/次）
- 模型：`models/bge-small-zh-v1.5`（官方权重 184M）+ `models/bge-onnx`（社区 ONNX 导出）；
  onnxruntime CPU 加载验证通过，输出维度 **512** 实测确认
- conda：独立环境 `b2q`（python3.12 + huggingface_hub + onnxruntime），不污染用户 base
- 端口决策：serve 用 **8100**（盘点：22/53/80/443/3000/3022/5003/6010/6011/6443/8000 已占）
- 待办衔接：M1a serve 代码就绪后即第 4 步部署

- **serve 部署形态定案（2026-11-03）**：docker 镜像化——Dockerfile 入仓、镜像 tag=git 短 hash、模型与数据走挂载卷不进镜像、服务器本地 build（不上 DockerHub）、回滚=起上一 tag。conda env b2q 保留用于 index 编码与验证


---

## serve Docker 镜像部署方案（定稿 2026-11-03）

### 前置验证（已通过）

- `docker pull python:3.12-slim` 成功（2026-11-03 实测）——docker hub 可达
- 服务器另有公司私有 registry `hub.htres.cn`（guangxin-* 栈来源）——**不使用**（非我方命名空间）
- 端口 8100 空闲已盘点

### 1. 镜像设计

| 项 | 决策 |
|---|---|
| 基础镜像 | `python:3.12-slim`（已缓存到服务器） |
| 依赖层 | fastapi + uvicorn + onnxruntime + book2qa 包（pyproject `[serve]` extra） |
| 运行用户 | 容器内非 root（`app`） |
| 入口 | `uvicorn book2qa.serve:app --host 0.0.0.0 --port 8100` |
| HEALTHCHECK | python urllib 探 `/healthz`（slim 无 curl） |
| 体积预估 | slim 130M + 依赖 ~100M + 代码 ~2M ≈ **250–300M** |
| 模型/数据 | **不进镜像**——挂载卷（见下） |

### 2. 卷与环境变量

| 挂载 | 宿主机（~/book2qa/） | 容器内 | 权限 |
|---|---|---|---|
| 教材产物 + store | `data/` | `/app/data` | rw |
| bge ONNX | `models/bge-onnx/` | `/app/models` | ro |
| 备份输出 | `backup/` | `/app/backup` | rw |

环境变量（十二要素，不写死路径）：`B2Q_API_KEY`、`B2Q_DATA_DIR=/app/data`、
`B2Q_MODELS_DIR=/app/models`、`B2Q_SERVE_PORT=8100`。

### 3. compose（deploy/compose.yaml）

```yaml
services:
  serve:
    build: { context: .., dockerfile: book2qa/deploy/Dockerfile }
    image: b2q-serve:<git短hash>
    ports: ["8100:8100"]
    volumes: ["../data:/app/data", "../models:/app/models:ro", "../backup:/app/backup"]
    environment: [B2Q_API_KEY, B2Q_DATA_DIR=/app/data, B2Q_MODELS_DIR=/app/models]
    restart: unless-stopped
```

### 4. 部署流水线（deploy.sh，本地执行）

```
前置：本地 109 例测试全绿（脚本前置断言，不绿即止）
① git bundle → scp 到服务器 ~/book2qa/
② 服务器：解包 pull → docker build -t b2q-serve:<hash>
③ compose up -d（新 tag）→ 轮询 /healthz（30s 超时）
④ 成功：prune 旧镜像（保留最近 3 个 tag）
   失败：自动起上一个 tag（回滚）+ 非零退出
```

幂等可重跑；回滚 = `docker compose up -d` 指向上一 tag，一条命令。

### 5. 验证方式说明

- **本地机**：uvicorn 直跑 + 109 例回归 + HTTP 契约测试（不依赖本地 docker）
- **服务器**：镜像 build + compose 冒烟（/healthz）+ 回滚演练（M1d 验收含此）

### 6. 实施文件清单（M1a/M1d 执行时产出）

| 文件 | 内容 |
|---|---|
| `book2qa/deploy/Dockerfile` | 按本方案 |
| `book2qa/deploy/compose.yaml` | 按本方案 |
| `book2qa/deploy/deploy.sh` | 本地侧流水线（bundle/scp/build/up/healthz/回滚） |
| `book2qa/pyproject.toml` | 加 `[serve]` extra（fastapi/uvicorn） |
| `book2qa/commands/serve.py` | FastAPI 应用（M1a） |
