#!/usr/bin/env bash
# book2skill 备份链（M3-3b；本地机执行 → 服务器 ~/book2qa/backup/）
#   用法：bash ops/backup.sh [--full]
#     默认：git bundle + store 快照 + memory + memory 快照（小件，秒级）
#     --full：追加 gzsx-md 原件全量（首次 ~526MB，LAN 数分钟）
# 服务器侧目录：~/book2qa/backup/{gzsx-md,git,store,memory}
set -euo pipefail

SERVER="${B2Q_DEPLOY_SERVER:-localgpu}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"        # book2skill 仓库根
WS="$(cd "$ROOT/.." && pwd)"                     # 工作区（gzsx-md/memory 所在）
DEST="book2qa/backup"
DATE="$(date +%Y%m%d-%H%M)"
FULL=0
[ "${1:-}" = "--full" ] && FULL=1

echo "== 备份开始 $DATE（--full=$FULL）=="
ssh "$SERVER" "mkdir -p $DEST/{git,store,memory,data,gzsx-md}"

# ① git bundle（代码全历史）
git -C "$ROOT" bundle create /tmp/b2k-git.bundle --all
scp -q /tmp/b2k-git.bundle "$SERVER:$DEST/git/book2skill-$DATE.bundle"
rm -f /tmp/b2k-git.bundle
echo "① git bundle ✓"

# ② store 学生数据（服务器上自拷，保留 60 份）
ssh "$SERVER" "cp ~/book2qa/data/store.sqlite $DEST/store/store-$DATE.sqlite 2>/dev/null || true; ls -t $DEST/store/store-*.sqlite | tail -n +61 | xargs -r rm -f"
echo "② store ✓"

# ②b book2qa/data 冻结产物（按册目录 + gold；入库外双保险）
tar -C "$ROOT/book2qa/data" -cf /tmp/b2k-data.tar \
    $(cd "$ROOT/book2qa/data" && ls -d */ 2>/dev/null | tr -d '/') eval_gold.jsonl \
    2>/dev/null || true
if [ -s /tmp/b2k-data.tar ]; then
  scp -q /tmp/b2k-data.tar "$SERVER:$DEST/data/data-$DATE.tar"
  rm -f /tmp/b2k-data.tar
  echo "②b data 冻结产物 ✓"
fi

# ③ memory（私有，仅内网服务器）
tar -C "$WS" -cf /tmp/b2k-mem.tar .workbuddy/memory 2>/dev/null || tar -C "$WS" -cf /tmp/b2k-mem.tar workbuddy-2026-10-18-10-47-49/.workbuddy/memory
scp -q /tmp/b2k-mem.tar "$SERVER:$DEST/memory/memory-$DATE.tar"
rm -f /tmp/b2k-mem.tar
echo "③ memory ✓"

# ④ gzsx-md 原件（孤本；--full 才跑）
if [ "$FULL" = "1" ]; then
  ssh "$SERVER" "mkdir -p $DEST/gzsx-md"
  tar -C "$WS" -cf - gzsx-md | ssh "$SERVER" "tar -C $DEST -xf -"
  ssh "$SERVER" "touch $DEST/gzsx-md/.full-$DATE"
  echo "④ gzsx-md 全量 ✓（du：）"
  ssh "$SERVER" "du -sh $DEST/gzsx-md"
else
  echo "④ gzsx-md 跳过（加 --full 执行；已有全量则无需重跑）"
fi

echo "== 备份完成：$SERVER:$DEST =="
