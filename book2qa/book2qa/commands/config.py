# -*- coding: utf-8 -*-
"""b2q config — ~/.book2qa/config.json 读写。"""
import json
import os
import sys
import time

from book2qa.envelope import emit
from book2qa.exit_codes import EXIT_OK, EXIT_USAGE

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".book2qa", "config.json")
_ALLOWED_KEYS = ("workspace", "source_root")


def _read():
    if os.path.exists(CONFIG_PATH):
        try:
            return json.load(open(CONFIG_PATH, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def execute(args, t0):
    if args.action == "path":
        return emit("config", EXIT_OK, t0=t0, extra={"path": CONFIG_PATH})
    if args.action == "get":
        if not args.key:
            return emit("config", EXIT_OK, t0=t0, extra={"values": _read()})
        return emit("config", EXIT_OK, t0=t0,
                    extra={"key": args.key, "value": _read().get(args.key)})
    # set
    if not args.key or args.value is None:
        return emit("config", EXIT_USAGE, error="set 需要 key 和 value", t0=t0)
    if args.key not in _ALLOWED_KEYS:
        return emit("config", EXIT_USAGE,
                    error="key 必须是 %s" % (_ALLOWED_KEYS,), t0=t0)
    cfg = _read()
    cfg[args.key] = args.value
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return emit("config", EXIT_OK, t0=t0,
                extra={"key": args.key, "value": args.value})


if __name__ == "__main__":
    sys.exit(0)
