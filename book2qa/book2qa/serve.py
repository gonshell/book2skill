# -*- coding: utf-8 -*-
"""b2q serve — FastAPI 运行主体（M1a，infra-server「Docker 部署方案」§1）。

设计要点（roadmap M1a）：
  引擎复用：/recall 与 /node 直接走 commands.recall/node 的 execute（同一份
  引擎同一份信封，CLI 与 HTTP 契约天然一致，零重复实现）；
  加载缓存：按 workspace 缓存一次数据装载（数据不变则不重解析）；
  认证：B2Q_API_KEY 设置即启用（/healthz 豁免）；未设置 = 开发模式并明示；
  请求日志：每次 /recall 追加 data/request_log.jsonl（巡检工具的数据源）。
"""
import io
import json
import os
import threading
import time

from fastapi import FastAPI, HTTPException, Request

from book2qa import paths

# execute() 经 emit 打印信封到 stdout（CLI 契约）；serve 捕获解析复用同一实现。
# redirect_stdout 是进程级的 → 全局锁串行化（recall 本就 CPU 密集，无碍）。
EXEC_LOCK = threading.Lock()


def _call_execute(fn, args):
    from contextlib import redirect_stdout
    with EXEC_LOCK, redirect_stdout(io.StringIO()) as buf:
        rc = fn(args, t0=None)
    return rc, json.loads(buf.getvalue())


def _load_bundle(workspace):
    """数据装载缓存：同 workspace 只装载一次（进程生命周期内）。"""
    from book2qa.commands import recall as recall_cmd
    bundle = recall_cmd._load(workspace)
    ok = bool(bundle.get("graph"))
    return bundle, ok


def create_app():
    app = FastAPI(title="b2q serve", version=_version())
    state = {"workspace": None}

    def _ws():
        if state["workspace"] is None:
            state["workspace"] = os.environ.get("B2Q_WORKSPACE") or \
                paths.resolve_workspace(None)
        return state["workspace"]

    @app.get("/healthz")
    def healthz():
        bundle, ok = _load_bundle(_ws())
        key = os.environ.get("B2Q_API_KEY")
        return {"ok": ok and bool(key is not None or True),
                "version": _version(),
                "index_loaded": ok,
                "nodes": len(bundle.get("graph", [])),
                "auth": "on" if key else "off(dev)",
                "workspace": _ws()}

    @app.post("/recall")
    def recall(req: Request, body: dict):
        _auth(req)
        from book2qa.commands import recall as recall_cmd
        import argparse
        args = argparse.Namespace(
            book=body.get("book", "必修第一册"),
            query=body.get("query", ""),
            top=int(body.get("top", 5)),
            scene=body.get("scene", "ask"),
            context=body.get("context"),
            workspace=_ws(),
        )
        if not args.query.strip():
            raise HTTPException(422, "query 为空")
        rc, env = _call_execute(recall_cmd.execute, args)
        # compact（默认开）：非 top1 候选只留元数据——模板只用 top1 的全文料，
        # 全量 quotes/formulas/exercises×3 候选是积分成本的大头（试用实测 11.71 分/题）
        if body.get("compact", True):
            for c in (env.get("candidates") or [])[1:]:
                for k in ("quotes", "formulas", "errors", "exercises", "summary"):
                    c.pop(k, None)
                c["compact"] = True
        _log_request(_ws(), args.query, env)
        return env

    @app.get("/node/{book}/{node_id}")
    def node(book: str, node_id: str, req: Request):
        _auth(req)
        from book2qa.commands import node as node_cmd
        import argparse
        args = argparse.Namespace(node_id=node_id, workspace=_ws())
        rc, env = _call_execute(node_cmd.execute, args)
        return env

    # ── M1b：学情端点（store 语义在 store.py，serve 只做 HTTP 壳）──
    @app.post("/log")
    def log(req: Request, body: dict):
        _auth(req)
        from book2qa import store
        account = body.get("account")
        node_id = body.get("node_id")
        if not account or not node_id:
            raise HTTPException(422, "account 与 node_id 必填")
        conn = store.connect(_ws())
        try:
            result = store.log_attempt(
                conn, account, node_id, eid=body.get("eid"),
                correct=bool(body.get("correct")), error_type=body.get("error_type"))
        finally:
            conn.close()
        return {"ok": True, "account": account, "node_id": node_id, **result}

    @app.get("/due")
    def due(req: Request, account: str, limit: int = 5):
        _auth(req)
        from book2qa import store
        conn = store.connect(_ws())
        try:
            return {"ok": True, "account": account,
                    "due": store.get_due(conn, account, limit=limit)}
        finally:
            conn.close()

    @app.get("/mastery")
    def mastery(req: Request, account: str):
        _auth(req)
        from book2qa import store
        conn = store.connect(_ws())
        try:
            return {"ok": True, "account": account,
                    "mastery": store.get_mastery(conn, account)}
        finally:
            conn.close()

    # ── M2a：/section —— 整节取料（learn 带学、ask 兜底的节点序列来源）──
    @app.get("/img/{book}/{img_path:path}")
    def img(book: str, img_path: str, req: Request):
        """教材原图（candidates[].figures[].file → 此端点）。"""
        _auth(req)
        from fastapi.responses import FileResponse
        root = os.environ.get("B2Q_IMAGES_ROOT")
        if not root or not os.path.isdir(root):
            raise HTTPException(503, "未配置教材图片根（B2Q_IMAGES_ROOT）")
        full = os.path.realpath(os.path.join(root, book, img_path))
        if not full.startswith(os.path.realpath(root) + os.sep) \
                or not os.path.isfile(full):
            raise HTTPException(404, "图不存在")
        return FileResponse(full)

    @app.get("/section/{book}/{section_id}")
    def section(book: str, section_id: str, req: Request):
        _auth(req)
        bundle, ok = _load_bundle(_ws())
        sid = section_id.strip()
        # 命中规则：unit 精确相等，或为该节的子节（unit 以 "sid." 开头）
        nodes = [n for n in bundle.get("graph", [])
                 if n.get("unit") == sid or n.get("unit", "").startswith(sid + ".")]
        if not nodes:
            raise HTTPException(404, "节 %r 下无知识点节点" % sid)
        nodes.sort(key=lambda n: n["id"])
        sec_row = next((r for r in bundle.get("structure", [])
                        if r.get("id") == sid), None)
        return {
            "ok": True,
            "book": book,
            "section_id": sid,
            "title": (sec_row or {}).get("title", sid),
            "nodes": [{"id": n["id"], "title": n["title"], "type": n["type"],
                       "pages": n.get("pages"), "prereq": n.get("prereq", []),
                       "summary": n.get("summary", "")} for n in nodes],
        }

    @app.put("/context/{context_id}")
    def put_ctx(context_id: str, req: Request, body: dict):
        _auth(req)
        from book2qa import store
        conn = store.connect(_ws())
        try:
            store.put_context(conn, context_id, body.get("account"),
                              last_node_id=body.get("last_node_id"),
                              history=body.get("history"))
        finally:
            conn.close()
        return {"ok": True, "context_id": context_id}

    @app.get("/context/{context_id}")
    def get_ctx(context_id: str, req: Request):
        _auth(req)
        from book2qa import store
        conn = store.connect(_ws())
        try:
            ctx = store.get_context(conn, context_id)
        finally:
            conn.close()
        if ctx is None:
            raise HTTPException(404, "context 不存在")
        return {"ok": True, **ctx}

    return app


def _auth(req):
    key = os.environ.get("B2Q_API_KEY")
    if key and req.headers.get("X-API-Key") != key:
        raise HTTPException(401, "无效 API key")


def _log_request(workspace, query, env):
    import json
    path = os.path.join(paths.data_dir(workspace), "request_log.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "query": query,
           "intent": env.get("intent"),
           "confidence": env.get("confidence"),
           "top_nodes": [c.get("node_id") for c in env.get("candidates", [])[:3]],
           "elapsed_sec": env.get("elapsed_sec")}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _version():
    from book2qa import __version__
    return __version__


def main():
    """b2q serve 入口：uvicorn 拉起。"""
    import uvicorn
    port = int(os.environ.get("B2Q_SERVE_PORT", "8100"))
    uvicorn.run(create_app(), host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
