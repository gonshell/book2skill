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
