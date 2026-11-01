#!/usr/bin/env bash
# book2qa 一键回归（体例对齐 book2md/run_tests.sh）
set -euo pipefail
cd "$(dirname "$0")"

PY=${B2Q_PYTHON:-python}
echo "== book2qa 单元测试 =="
"$PY" -m unittest discover -s tests -v 2>&1 | tail -5

echo ""
echo "== 冒烟：b2q --version =="
"$PY" -m book2qa.cli --version

echo ""
echo "全部通过"
