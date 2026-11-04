# ops-runbook.md — 部署运维手册

> 目标读者：把 book2qa 部署到一台**全新服务器**并跑起来的人（含未来的自己）。
> 命令均实测于 172.20.4.209（Ubuntu，xiesg 用户，docker 组，无 sudo）。
> 版本基线：v0.7.0（双册上线）。

## 0. 部署要求（前置核对清单）

| 项 | 要求 | 核对命令 |
|---|---|---|
| OS | Linux（Ubuntu 实测） | — |
| 用户 | 部署用户在 `docker` 组；**无需 sudo** | `id -nG \| grep docker` |
| 磁盘 | ≥5 GB（镜像 300M + 模型 200M + 双册产物 ~100M + 备份余量） | `df -h ~` |
| 网络 | 可达 docker hub（拉基础镜像）与 hf-mirror.com（拉模型）；**不要求**能连 GitHub（代码走 bundle） | `docker pull hello-world`、`curl -sI https://hf-mirror.com` |
| 端口 | 8100 空闲（可改，见 compose） | `ss -tlnp \| grep 8100` |
| 本地机 | git、ssh 免密到服务器（`~/.ssh/config` 配别名）、本地 Python ≥3.12（跑测试） | — |
| 密钥 | `B2Q_API_KEY`（首次部署自动生成于 `deploy/deploy.env`，权限 600） | — |

## 1. 全新服务器 Bootstrap（一次性，约 20 分钟）

```bash
# 本地机变量
SERVER=<ssh别名>            # ~/.ssh/config 里配好免密
SHOME=book2qa               # 服务器家目录下的部署根

# ① 服务器目录骨架
ssh $SERVER "mkdir -p ~/$SHOME/{models,data,src,backup,repo}"

# ② bge 模型（二选一：hub CLI 或直接下载 ONNX）
ssh $SERVER "~/miniconda3/bin/conda create -n b2q python=3.12 -y -q"
ssh $SERVER "~/miniconda3/envs/b2q/bin/pip install -q 'huggingface_hub[cli]' onnxruntime"
ssh $SERVER "HF_ENDPOINT=https://hf-mirror.com ~/miniconda3/envs/b2q/bin/hf download \
  Xenova/bge-small-zh-v1.5 --include 'onnx/*' --local-dir ~/$SHOME/models/bge-onnx"
# 校验：输出维度必须 512
ssh $SERVER "~/miniconda3/envs/b2q/bin/python -c \"import onnxruntime as ort; \
  s=ort.InferenceSession('$HOME/$SHOME/models/bge-onnx/onnx/model.onnx'); \
  print([(i.name,i.shape) for i in s.get_inputs()])\""
# 另需 vocab.txt（Encoder 加载词表用）：从仓库外下载或从既有部署拷
scp vocab.txt $SERVER:$SHOME/models/bge-onnx/vocab.txt

# ③ 运行副本（服务器连不上 GitHub → bundle 方式）
cd <本地book2skill仓库> && git bundle create /tmp/book2skill.bundle --all
scp -q /tmp/book2skill.bundle $SERVER:$SHOME/
ssh $SERVER "cd ~/$SHOME/repo && git clone -q --depth 1 -b main ~/$SHOME/book2skill.bundle ."
```

## 2. 首次部署（一条命令）

```bash
# 本地机（先确认测试全绿——deploy.sh 有前置断言，不绿即止）
cd <book2skill仓库>
B2Q_PYTHON=<python≥3.12> bash book2qa/deploy/deploy.sh
```

脚本自动完成：bundle→scp→按册同步 data 与 book2md 原文→服务器 build 镜像
（tag=git 短 hash）→compose up→healthz 30 秒轮询→失败自动回滚上一 tag。
成功后 `B2Q_API_KEY` 已生成在服务器 `book2qa/repo/book2qa/deploy/deploy.env`。

**验证**：
```bash
curl -s http://$SERVER_IP:8100/healthz          # 节点数>0、auth:on
curl -s http://$SERVER_IP:8100/img/必修第一册/images/page_128_image_4.jpg \
     -H "X-API-Key: $KEY" -o /dev/null -w '%{http_code}'   # 200 且 content-type image/jpeg
```

## 3. 日常更新（改代码/改图谱后）

> **deploy.sh 的可配环境变量**（换机器/换册时用，见脚本头注释）：
> `B2Q_DEPLOY_SERVER`（ssh 别名）、`B2Q_SERVER_HOME`（默认 book2qa）、
> `B2Q_DEPLOY_BOOK`、`B2Q_GZSX_FINAL`（本地 gzsx-md/final 绝对路径）、`B2Q_PYTHON`。

```bash
# 本地：测试全绿 → 提交 → 直接重跑 deploy.sh（幂等）
B2Q_PYTHON=<python> bash book2qa/deploy/deploy.sh
```
图谱更新链（改了候选/裁定后）：`b2q review-import --apply`（如走 Excel）→
`b2q build --stage graph` → `b2q index --book X` → deploy.sh（数据按册自动同步）。

## 4. 回滚（一条命令）

```bash
ssh $SERVER "cd ~/$SHOME/repo/book2qa/deploy && \
  PREV=\$(docker images --format '{{.Tag}}' b2q-serve | grep -v <当前tag> | head -1) && \
  B2Q_UID=\$(id -u) B2Q_GID=\$(id -g) BOOK2QA_HOME=\$HOME/$SHOME TAG=\$PREV docker compose up -d"
curl -s http://127.0.0.1:8100/healthz   # 回滚态验证
```
（deploy.sh 健康检查失败时已自动做同样的事。）

## 5. 备份（每周 + 每次发版后）

```bash
bash ops/backup.sh          # 小件：git bundle + store + memory + data 冻结产物（秒级）
bash ops/backup.sh --full   # 追加 gzsx-md 原件全量（首次 ~526MB，之后仍全量但 LAN 一分钟）
```
落点：服务器 `~/book2qa/backup/{git,store,memory,data,gzsx-md}`。
**恢复演练**（建议每季度一次）：从 backup/data/data-*.tar 解包 graph.jsonl →
healthz 节点数与 tar 内行数一致即通过。

## 6. 巡检（每周）

```bash
scp $SERVER:~/book2qa/data/request_log.jsonl book2qa/data/inspect/
cd book2qa && python scripts/inspect_report.py    # 出 Markdown 周报
```
看三个数：`none`>10% = 检索系统性缺口；`low` 重复聚类 = 真缺口；处置 =
补 aliases（review Excel）或加 eval_gold（重跑评测不降标）。

## 7. 故障速查

| 症状 | 首查 | 本项目已踩过的实例 |
|---|---|---|
| 容器起不来 | `docker logs b2q-serve` | compose 空插值覆盖 env_file → API key 失效 |
| 写库报 readonly | 容器 user 与卷属主 | heredoc `$(id -u)` 本地展开成 Windows 假 uid → 改 `\$()` |
| recall 50 缺 book2md 产物 | src 下有无该册 markdown/page_map | 按册原文同步（deploy.sh ⓪b 步） |
| R4 降级 warnings | models/bge-onnx 布局（vocab.txt + onnx/model.onnx） | scp 层级错位 |
| healthz 节点 0 | data/<册>/graph.jsonl 是否同步 | 按册 scp |
| healthz 节点重复膨胀 | request 侧多次 PUT？否——检查 data 下是否残留旧根级 jsonl | M3-4 修复 |

## 8. 已知边界

- 服务器不连 GitHub：一切代码更新走 bundle+scp（deploy.sh 内建）
- 单机 FastAPI + 内存索引 + sqlite：数百学生内够用；并发上去后唯一迁移点 = sqlite→postgres（store.py 已隔离）
- R4 推理进程内 CPU（5–20ms/条），GPU 不需要
