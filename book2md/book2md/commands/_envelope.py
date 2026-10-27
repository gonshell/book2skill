# -*- coding: utf-8 -*-
"""JSON 结果信封（docs/spec-cli.md §5）：stdout 恒为单个合法 JSON 对象。"""
import json
import sys
import time


def emit(cmd, exit_code, *, workspace=None, book=None, out_dir=None,
         artifacts=None, warnings=None, error=None, t0=None, extra=None):
    """组装并打印信封到 stdout；返回 exit_code 供 sys.exit 使用。

    extra: 命令特有字段（顶层合并，spec §8 允许的新增可选字段；禁覆盖核心键）。
    """
    envelope = {
        "cmd": cmd,
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "workspace": workspace,
        "book": book,
        "out_dir": out_dir,
        "artifacts": artifacts or {},
        "warnings": warnings or [],
        "elapsed_sec": round(time.time() - t0, 2) if t0 else None,
        "error": error,
    }
    if extra:
        clash = set(extra) & set(envelope)
        if clash:
            raise ValueError("extra 与信封核心键冲突：%s" % sorted(clash))
        envelope.update(extra)
    sys.stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    return exit_code
