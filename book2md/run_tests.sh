#!/usr/bin/env bash
# run_tests.sh — textbook-pipe 全量回归一键复现（P1 验收与日常回归入口）
#
# 用法：
#   bash run_tests.sh                      # 冒烟 + 契约测试（不依赖历史产物）
#   TBP_PARITY_SOURCE=<gzsx-md> bash run_tests.sh   # 追加四套行为保持对账（约 11 分钟）
#
# 环境要求：Python ≥3.13（解释器见 docs/install.md）、Node.js ≥22、PIL（Pillow）。
# 任一测试失败立即非零退出（set -e）。
set -euo pipefail

cd "$(dirname "$0")"

PY=${TBP_PYTHON:-python}
export TBP_PARITY_SOURCE="${TBP_PARITY_SOURCE:-}"

echo "== 环境自检 =="
"$PY" -c "import sys; assert sys.version_info >= (3, 13), '需要 Python ≥3.13'; print('Python', sys.version.split()[0])"
node --version
"$PY" -c "import PIL; print('Pillow', PIL.__version__)"
echo

run() {
    echo "== $1 =="
    "$PY" "tests/$1.py" 2>&1 | grep -E "^Ran|^OK|^FAILED"
}

# 第一梯队：不依赖历史产物的测试（CI 友好）
run test_extraction_contract
run test_extract_onboard_smoke
run test_run_smoke
run test_s16_and_inline_tags
run test_baseline_smoke
run test_fingerprint_and_sampling
run test_skill_scripts

# 第二梯队：行为保持对账（需 TBP_PARITY_SOURCE 指向五册历史产物目录，缺省跳过）
# 注意：test_render_parity 为 10 个 HTML 逐字节对账，约 10 分钟，放最后。
if [ -n "$TBP_PARITY_SOURCE" ]; then
    run test_merge_parity
    run test_inspectors_parity
    run test_behavior_parity
    run test_render_parity
else
    echo "== 对账测试跳过（未设 TBP_PARITY_SOURCE，P1 验收时必须设置）=="
fi

echo
echo "全部通过。"
