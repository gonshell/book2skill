#!/usr/bin/env bash
# 部署流水线（infra-server.md「serve Docker 部署方案」§4；本地执行）
#   前置：本地测试全绿（不绿即止）→ bundle+scp → 服务器 build → up → healthz
#   失败：自动回滚上一个 tag；幂等可重跑
# 可配环境变量：B2Q_DEPLOY_SERVER(默认 localgpu) B2Q_SERVER_HOME(默认 ~/book2qa)
#               B2Q_DEPLOY_BOOK(默认 必修第一册) B2Q_GZSX_FINAL(gzsx-md/final 路径)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SERVER="${B2Q_DEPLOY_SERVER:-localgpu}"
SHOME="${B2Q_SERVER_HOME:-book2qa}"          # 服务器上的相对 home 路径（~/book2qa）
BOOK="${B2Q_DEPLOY_BOOK:-必修第一册}"
GZSX_FINAL="${B2Q_GZSX_FINAL:-C:/Users/xiesh/WorkBuddy/2026-10-18-10-47-49/gzsx-md/final}"
TAG="$(git -C "$ROOT" rev-parse --short HEAD)"
PY="${B2Q_PYTHON:-python}"

echo "== 前置：本地测试全绿 =="
(cd "$ROOT/book2qa" && "$PY" -m unittest discover -s tests -q)

echo "== ① bundle + 数据传输 =="
BUNDLE="$ROOT/dist/book2skill.bundle"
mkdir -p "$ROOT/dist"
git -C "$ROOT" bundle create "$BUNDLE" --all
scp -q "$BUNDLE" "$SERVER:$SHOME/book2skill.bundle"
ssh "$SERVER" "mkdir -p $SHOME/data $SHOME/src/$BOOK $SHOME/backup"
scp -q "$ROOT"/book2qa/data/*.jsonl "$SERVER:$SHOME/data/"
scp -q "$ROOT"/book2qa/data/vectors.npz "$ROOT"/book2qa/data/vectors_meta.jsonl \
    "$SERVER:$SHOME/data/" 2>/dev/null || echo "  (无向量索引，跳过——R4 将降级三路)"
scp -q "$GZSX_FINAL/$BOOK/markdown.md" "$GZSX_FINAL/$BOOK/page_map.md" \
    "$SERVER:$SHOME/src/$BOOK/"

echo "== ② 服务器：代码更新 + 镜像构建 =="
ssh "$SERVER" bash -s <<REMOTE
set -euo pipefail
HDIR="\$HOME/$SHOME"
cd "\$HDIR/repo"
if [ -d .git ]; then
  git pull -q "\$HDIR/book2skill.bundle" main
else
  git clone -q --depth 1 -b main "\$HDIR/book2skill.bundle" .
fi
docker build -q -t b2q-serve:$TAG -f book2qa/deploy/Dockerfile .
cd book2qa/deploy
[ -f deploy.env ] || { echo "B2Q_API_KEY=\$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')" > deploy.env; chmod 600 deploy.env; }
BOOK2QA_HOME="\$HDIR" TAG=$TAG docker compose up -d
REMOTE

echo "== ③ 健康检查（30s 超时 → 回滚）=="
OK=0
for i in $(seq 1 15); do
  if ssh "$SERVER" "curl -sf http://127.0.0.1:8100/healthz" >/dev/null 2>&1; then OK=1; break; fi
  sleep 2
done
if [ "$OK" != "1" ]; then
  echo "!! 健康检查失败 → 回滚上一个 tag"
  ssh "$SERVER" "cd $SHOME/repo/book2qa/deploy && PREV=\$(docker images --format '{{.Tag}}' b2q-serve | grep -v $TAG | head -1) && BOOK2QA_HOME=\"\$HOME/$SHOME\" TAG=\$PREV docker compose up -d"
  exit 1
fi

echo "== ④ 成功：tag=$TAG，清理旧镜像（保留 3 个）=="
ssh "$SERVER" "docker images --format '{{.Tag}}' b2q-serve | tail -n +4 | xargs -r docker rmi b2q-serve 2>/dev/null || true"
echo "部署完成：http://172.20.4.209:8100  (tag=$TAG)"
