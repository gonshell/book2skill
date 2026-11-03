# -*- coding: utf-8 -*-
"""核心层：学生学情库 store（M1b，roadmap；serve 不直接摸 SQL）。

五张表（v1 语义定稿）：
  account  邀请码账号（v1 只存 id；激活校验在阶段 C）
  attempt  每次答题（eid/对错/错因）——只增
  mastery  每节点当前掌握度 = correct/attempts（简单比值，可迭代）
  schedule SM-2 排程（easiness/interval/reps/next_due）
  context  会话承接（跨设备）

SM-2 简化规则（v1 定稿）：
  答对 reps+1，interval 1→6→×easiness；easiness+0.1（上限 3.0）
  答错 reps=0，interval=1；easiness−0.2（下限 1.3）
  next_due = 当天 + interval 天
mastery 规则：correct/attempts（冷启动 0，随题量趋稳；迭代留待试用反馈）。

并发：sqlite WAL 模式，单写者足够（写少读多）；换 postgres 时只动本模块。
"""
import json
import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS account (
  account_id TEXT PRIMARY KEY, invite_code TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS attempt (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id TEXT NOT NULL, node_id TEXT NOT NULL, eid TEXT,
  correct INTEGER NOT NULL, error_type TEXT, ts TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_attempt_acc ON attempt(account_id, ts);
CREATE TABLE IF NOT EXISTS mastery (
  account_id TEXT NOT NULL, node_id TEXT NOT NULL,
  mastery REAL NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0, correct INTEGER NOT NULL DEFAULT 0,
  last_seen TEXT,
  PRIMARY KEY (account_id, node_id));
CREATE TABLE IF NOT EXISTS schedule (
  account_id TEXT NOT NULL, node_id TEXT NOT NULL,
  easiness REAL NOT NULL DEFAULT 2.5,
  interval_days INTEGER NOT NULL DEFAULT 0,
  reps INTEGER NOT NULL DEFAULT 0, next_due TEXT NOT NULL,
  PRIMARY KEY (account_id, node_id));
CREATE TABLE IF NOT EXISTS context (
  context_id TEXT PRIMARY KEY, account_id TEXT, last_node_id TEXT,
  history_json TEXT NOT NULL DEFAULT '[]', updated_at TEXT);
"""


def connect(workspace):
    path = os.path.join(_data_dir(workspace), "store.sqlite")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _data_dir(workspace):
    from book2qa import paths
    return paths.data_dir(workspace)


def _today(ts=None):
    return (ts or time.time()) and time.strftime("%Y-%m-%d", time.localtime())


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ── SM-2 简化（v1 定稿，见模块注释）──
def _sm2(row, correct, today):
    ef, iv, reps = 2.5, 0, 0
    if row:
        ef, iv, reps = row["easiness"], row["interval_days"], row["reps"]
    if correct:
        reps += 1
        iv = 1 if reps == 1 else (6 if reps == 2 else max(1, round(iv * ef)))
        ef = min(3.0, ef + 0.1)
    else:
        reps, iv = 0, 1
        ef = max(1.3, ef - 0.2)
    # due 基于「会话日 today」（可注入以便测试与补卡），非 wall clock
    base = time.mktime(time.strptime(today, "%Y-%m-%d"))
    due = time.strftime("%Y-%m-%d", time.localtime(base + iv * 86400))
    return ef, iv, reps, due


def log_attempt(conn, account_id, node_id, eid=None, correct=False,
                error_type=None, today=None):
    """落一次答题：attempt 只增 + mastery 重算 + schedule SM-2。

    返回更新后的 {"mastery","attempts","next_due","interval_days"}。
    """
    ts = _now()
    day = today or _today()
    with conn:
        conn.execute(
            "INSERT INTO attempt(account_id,node_id,eid,correct,error_type,ts)"
            " VALUES(?,?,?,?,?,?)",
            (account_id, node_id, eid, int(bool(correct)), error_type, ts))
        row = conn.execute(
            "SELECT attempts, correct FROM mastery"
            " WHERE account_id=? AND node_id=?", (account_id, node_id)).fetchone()
        attempts = (row["attempts"] if row else 0) + 1
        corr = (row["correct"] if row else 0) + (1 if correct else 0)
        mastery = round(corr / attempts, 4)
        conn.execute(
            "INSERT INTO mastery(account_id,node_id,mastery,attempts,correct,last_seen)"
            " VALUES(?,?,?,?,?,?) ON CONFLICT(account_id,node_id) DO UPDATE SET"
            " mastery=excluded.mastery, attempts=excluded.attempts,"
            " correct=excluded.correct, last_seen=excluded.last_seen",
            (account_id, node_id, mastery, attempts, corr, ts))
        srow = conn.execute(
            "SELECT easiness, interval_days, reps FROM schedule"
            " WHERE account_id=? AND node_id=?", (account_id, node_id)).fetchone()
        ef, iv, reps, due = _sm2(srow, correct, day)
        conn.execute(
            "INSERT INTO schedule(account_id,node_id,easiness,interval_days,reps,next_due)"
            " VALUES(?,?,?,?,?,?) ON CONFLICT(account_id,node_id) DO UPDATE SET"
            " easiness=excluded.easiness, interval_days=excluded.interval_days,"
            " reps=excluded.reps, next_due=excluded.next_due",
            (account_id, node_id, ef, iv, reps, due))
    return {"mastery": mastery, "attempts": attempts,
            "next_due": due, "interval_days": iv}


def get_due(conn, account_id, limit=5, today=None):
    day = today or _today()
    rows = conn.execute(
        "SELECT node_id, next_due, interval_days, reps FROM schedule"
        " WHERE account_id=? AND next_due<=? ORDER BY next_due LIMIT ?",
        (account_id, day, limit)).fetchall()
    return [dict(r) for r in rows]


def get_mastery(conn, account_id):
    rows = conn.execute(
        "SELECT node_id, mastery, attempts, correct, last_seen FROM mastery"
        " WHERE account_id=? ORDER BY mastery ASC", (account_id,)).fetchall()
    return [dict(r) for r in rows]


def put_context(conn, context_id, account_id, last_node_id=None, history=None):
    with conn:
        conn.execute(
            "INSERT INTO context(context_id,account_id,last_node_id,history_json,updated_at)"
            " VALUES(?,?,?,?,?) ON CONFLICT(context_id) DO UPDATE SET"
            " last_node_id=excluded.last_node_id, history_json=excluded.history_json,"
            " updated_at=excluded.updated_at",
            (context_id, account_id, last_node_id,
             json.dumps(history or [], ensure_ascii=False), _now()))


def get_context(conn, context_id):
    row = conn.execute("SELECT * FROM context WHERE context_id=?",
                       (context_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["history"] = json.loads(d.pop("history_json"))
    return d
