#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""技能壳脚本：环境预检（SKILL.md §0）。

检查项：tbp 可用性 / Node.js / KaTeX 资产随包 / 工作区可写；端点可达性可选。
只做检查与汇报，不做任何转换动作。输出 JSON 信封（与核心包同纪律）。

用法：
    python precheck.py [--workspace <路径>] [--check-endpoint]

退出码：0 全部通过 · 20 必要项缺失 · 30 端点不可达（仅 --check-endpoint 时）。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

EXIT_OK = 0
EXIT_CONFIG = 20
EXIT_BACKEND = 30


def _emit(payload, exit_code, t0):
    payload.update({"cmd": "precheck", "ok": exit_code == 0, "exit_code": exit_code,
                    "elapsed_sec": round(time.time() - t0, 2)})
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return exit_code


def _sh(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                           encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or r.stderr or "").strip().splitlines()
    except (OSError, subprocess.TimeoutExpired) as ex:
        return None, [str(ex)]


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace")
    ap.add_argument("--check-endpoint", action="store_true")
    args = ap.parse_args()

    checks = []

    def add(name, ok, detail, hint=None, fatal=True):
        checks.append({"name": name, "ok": bool(ok), "detail": detail,
                       **({"hint": hint} if hint else {}), "fatal": fatal})

    # ① tbp 命令可用（import 路径与入口双重验证）
    rc, out = _sh([sys.executable, "-c",
                   "import textbook_pipe, sys; print(textbook_pipe.__file__)"])
    add("tbp_import", rc == 0, out[0] if out else "",
        hint="pip install textbook-pipe（见 docs/install.md）" if rc != 0 else None)
    tbp_exe = shutil.which("tbp") or shutil.which("tbp.exe")
    # 入口缺失不致命：import 成功时 python -m textbook_pipe.cli 等价可用
    add("tbp_entry", tbp_exe is not None, tbp_exe or "未找到（可用 python -m textbook_pipe.cli 等价调用）",
        hint="pip install textbook-pipe 后 tbp/tbpipe 入口进 PATH" if not tbp_exe else None, fatal=False)

    # ② Node.js ≥ 22（KaTeX 预渲染依赖）
    rc, out = _sh(["node", "--version"])
    ver = out[0] if rc == 0 and out else ""
    try:
        ok = rc == 0 and tuple(int(x) for x in ver.lstrip("v").split(".")) >= (22,)
    except ValueError:
        ok = False
    add("node", ok, ver or "未找到",
        hint="安装 Node.js ≥22（版本锁定见 docs/install.md）" if not ok else None)

    # ③ KaTeX 资产随包（css + 字体 + 渲染脚本）
    rc, out = _sh([sys.executable, "-c",
                   "import os, textbook_pipe.engine.render as r;"
                   "print(os.path.exists(os.path.join(r.KATEX_DIR, 'katex.min.css')));"
                   "print(len(os.listdir(os.path.join(r.KATEX_DIR, 'fonts'))));"
                   "print(os.path.exists(r.RENDER_JS))"])
    if rc == 0 and len(out) >= 3:
        add("katex_assets", out[0] == "True" and int(out[1]) >= 20 and out[2] == "True",
            "css=%s fonts=%s js=%s" % (out[0], out[1], out[2]),
            hint="重装包（package-data 应随 wheel 分发）" if out[0] != "True" else None)
    else:
        add("katex_assets", False, "探测失败", hint="检查 textbook_pipe.engine.render 可导入")

    # ④ 工作区解析与可写
    ws = args.workspace or os.environ.get("TBP_WORKSPACE") or os.getcwd()
    try:
        probe = os.path.join(ws, ".tbp_probe")
        os.makedirs(ws, exist_ok=True)
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        add("workspace_writable", True, ws)
    except OSError as ex:
        add("workspace_writable", False, "%s: %s" % (ws, ex),
            hint="tbp config set workspace <可写路径>")

    # ⑤ 端点可达（可选，失败仅警告不致命）
    endpoint_rc = None
    if args.check_endpoint:
        rc, out = _sh([sys.executable, "-c",
                       "from textbook_pipe.commands._endpoints import resolve_api;"
                       "import os;"
                       "print(resolve_api(os.getcwd()) or '')"])
        endpoint = out[0] if rc == 0 and out else ""
        if not endpoint:
            add("endpoint", False, "未配置",
                hint="设 TBP_BACKEND_API 或 tbp config set backend_endpoint",
                fatal=False)
        else:
            crc, cout = _sh(["curl", "-sf", "-m", "10", endpoint.rstrip("/") + "/version"])
            endpoint_rc = crc
            add("endpoint", crc == 0, "%s -> %s" % (endpoint, cout[0] if cout else "不可达"),
                hint="网关不可达：离线命令（run/scan/report）仍可用，抽取/基准重抽不可用",
                fatal=False)

    fatal_bad = [c for c in checks if not c["ok"] and c["fatal"]]
    exit_code = EXIT_OK if not fatal_bad else EXIT_CONFIG
    if args.check_endpoint and exit_code == EXIT_OK and endpoint_rc not in (0, None):
        exit_code = EXIT_BACKEND
    return _emit({"checks": checks, "workspace": ws}, exit_code, t0)


if __name__ == "__main__":
    sys.exit(main())
