# -*- coding: utf-8 -*-
"""RemoteMinerUAdapter 内核（自 gzsx-md/run_blocks.py 行为保持迁入 + 编排新增）。

网络半（convert_block）：curl 分块提交 / 403 退避（0/30/90s）/ 块间隔，逐字保持。
合并半：调用 extractors/merge.py（与 process_block 的内联合并同逻辑，去重）。
编排（extract_pdf / 契约与指纹落盘）为新增代码，规格见 docs/spec-cli.md §6.5。

⚠️ 端点/参数禁止硬编码：api 由调用方（CLI/配置）传入（docs/backend.md 契约）。
⚠️ 版本指纹纪律：网关未上报的字段一律 None（docs/backend.md §3）。
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile

from textbook_pipe.extractors import merge

# 默认数据（人教A版数学 5 册：书名 → PDF 文件名；科目配置化后由配置注入）
DEFAULT_PDF_MAP = {
    "选择性必修第三册": "普通高中教科书·数学（A版）选择性必修第三册.pdf",
    "选择性必修第二册": "普通高中教科书·数学（A版）选择性必修第二册.pdf",
    "选择性必修第一册": "普通高中教科书·数学（A版）选择性必修第一册.pdf",
    "必修第二册": "普通高中教科书·数学（A版）必修第二册.pdf",
    "必修第一册": "普通高中教科书·数学（A版）必修第一册.pdf",
}
DEFAULT_START_PAGE = 7   # 前 6 页为封面/扉页/版权页/导引/目录，统一跳过
DEFAULT_BLOCK_SIZE = 40


def make_blocks(start, end, block_size=DEFAULT_BLOCK_SIZE):
    """按块大小切分物理页区间（自 run_blocks.make_blocks 逐字保持）。"""
    blocks, s = [], start
    while s <= end:
        e = min(s + block_size - 1, end)
        blocks.append((s, e))
        s = e + 1
    return blocks


def pdf_page_count(pdf_path):
    """读 PDF 总页数（pymupdf 惰性导入——仅 extract 可选增强需要）。"""
    try:
        import pymupdf
    except ImportError:
        raise RuntimeError(
            "本地未安装 pymupdf（pip install textbook-pipe[extract]），"
            "且未显式传入 page_count，无法确定分块范围") from None
    return pymupdf.open(pdf_path).page_count


def load_ledger(ledger_path):
    if os.path.exists(ledger_path):
        return json.load(open(ledger_path, encoding="utf-8"))
    return {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "books": {}}


def save_ledger(ledger_path, led):
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
    json.dump(led, open(ledger_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def convert_block(pdf_path, s, e, blocks_dir, api, tier="basic"):
    """提交一个块并下载 zip（自 run_blocks.convert_block 行为保持，仅参数化）。

    返回 (status, message)：status ∈ done / failed。
    """
    os.makedirs(blocks_dir, exist_ok=True)
    zpath = os.path.join(blocks_dir, f"block_{s}-{e}.zip")

    url = f"{api}/v1/file_parse?tier={tier}&response_format=zip&wait_timeout=900&page_range={s}-{e}"
    cmd = ["curl", "-sS", "-X", "POST", url,
           "-F", f"files=@{pdf_path}",
           "-o", zpath, "-w", "%{http_code}"]
    # 403 = 服务端间歇限流，退避等待（0/30/90s）
    backoff = [0, 30, 90]
    code, err = "", ""
    for attempt in (0, 1, 2):
        if attempt > 0:
            time.sleep(backoff[attempt])
            print(f"  [重试 {attempt}] {s}-{e}（上次 HTTP {code}）", flush=True, file=sys.stderr)
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=960)
        code = r.stdout.strip()
        if code == "200" and os.path.exists(zpath) and zipfile.is_zipfile(zpath):
            dt = round(time.time() - t0, 1)
            time.sleep(3)  # 块间隔，降低触发限流概率
            return ("done", f"{dt}s")
        err = ""
        try:
            err = open(zpath, encoding="utf-8").read()[:200]
        except Exception:
            pass
        print(f"  [失败 attempt={attempt}] HTTP {code} | {err[:200]}", flush=True, file=sys.stderr)
    return ("failed", f"HTTP {code} {err[:100]}")


def process_block(name, s, e, pdf_path, blocks_dir, out_dir, api, tier="basic"):
    """提交 + 解包 + 合并（自 run_blocks.process_block 行为保持；合并半复用 merge.merge_one）。

    返回 (status, message)。
    """
    status, msg = convert_block(pdf_path, s, e, blocks_dir, api, tier)
    if status != "done":
        return status, msg
    try:
        # merge_one 约定 blocks_root（其内部拼 <book>/）；blocks_dir 是册目录，回退一级
        n_imgs, pages = merge.merge_one(name, s, e,
                                        os.path.dirname(blocks_dir.rstrip("/\\")), out_dir)
    except FileNotFoundError as ex:
        return "failed", str(ex)
    return "done", f"pages {s}-{e}, images {n_imgs}, 教材页 {pages}"


def collect_fingerprint():
    """网关版本指纹（docs/backend.md §3）。

    网关未上报的字段一律 None——缺口显式可见，禁止占位假值；
    补实途径见 backend.md「核实尝试记录」。
    """
    return {
        "gateway_version": None,
        "mineru_version": None,
        "model_hashes": {},
        "patched_files": [{"path": "mineru/model/ocr/image.py",
                           "patch_id": "img-crop-min1", "present": None}],
        "note": "待网关核实（docs/backend.md §3，2026-10-24 探测：网关不可达）",
    }


def extract_pdf(pdf_path, book, workspace, api, tier="basic", start_page=DEFAULT_START_PAGE,
                end_page=None, block_size=DEFAULT_BLOCK_SIZE, force=False):
    """抽取编排（新增代码，规格 docs/spec-cli.md §6.5）。

    流程：账本初始化（单册）→ 逐 pending 块 convert+merge（每块落账）→
    merge_all 页序归一化（rematch 语义）→ 写 contract.json（Canonical Extraction v1）。
    归一化产物按 spec §4 布局写 <workspace>/extract/<book>/{markdown.md, images/}；
    blocks/<book>/ 的 ex_* 解包缓存即适配器原始输出，追溯复用同一份，不重复落盘。
    返回统计 dict；网络失败抛 RuntimeError（CLI 映射退出码 30）。
    """
    pdf_path = os.path.abspath(pdf_path)
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(pdf_path)
    if end_page is None:
        end_page = pdf_page_count(pdf_path)

    blocks_dir = os.path.join(workspace, "blocks", book)
    blocks_root = os.path.join(workspace, "blocks")
    extract_root = os.path.join(workspace, "extract")
    contract_dir = os.path.join(extract_root, book)
    ledger_path = os.path.join(workspace, "ledger.json")

    led = load_ledger(ledger_path)
    info = led["books"].setdefault(book, {
        "pdf": os.path.basename(pdf_path), "total_pdf_pages": end_page,
        "start": start_page, "end": end_page, "blocks": {},
    })
    for s, e in make_blocks(start_page, end_page, block_size):
        key = f"{s}-{e}"
        if key not in info["blocks"] or force:
            info["blocks"][key] = "pending"
    save_ledger(ledger_path, led)

    pending = [(int(k.split("-")[0]), int(k.split("-")[1]))
               for k, v in sorted(info["blocks"].items(),
                                  key=lambda kv: int(kv[0].split("-")[0])) if v == "pending"]
    failed = []
    for s, e in pending:
        print(f"[{book}] {s}-{e} ...", flush=True, file=sys.stderr)
        st, msg = process_block(book, s, e, pdf_path, blocks_dir, extract_root, api, tier)
        print(f"  -> {st} | {msg}", flush=True, file=sys.stderr)
        info["blocks"][f"{s}-{e}"] = st
        save_ledger(ledger_path, led)
        if st != "done":
            failed.append((s, e, msg))
    if failed:
        raise RuntimeError("抽取失败块: %s" % failed)

    # 页序归一化（rematch 语义：清空 extract/<book> 后按页序重合并）
    merge.merge_all(blocks_root=blocks_root, out_root=extract_root,
                    ledger_path=ledger_path, books=[book])

    # Canonical Extraction v1 契约落盘（方案 §4.4.2）
    os.makedirs(contract_dir, exist_ok=True)
    images_dir = os.path.join(extract_root, book, "images")
    manifest = sorted(os.listdir(images_dir)) if os.path.isdir(images_dir) else []
    sha = hashlib.sha256(open(pdf_path, "rb").read()).hexdigest()
    contract = {
        "schema": "tbpipe.extraction/v1",
        "source_pdf": {"name": os.path.basename(pdf_path), "sha256": sha},
        "meta": {"tool": "mineru-remote", "tier": tier,
                 "extracted_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                 "backend": collect_fingerprint()},
        "pages": [{"physical_page": s, "extraction_index": i,
                   "block": f"{s}-{e}"}
                  for i, (s, e) in enumerate(make_blocks(start_page, end_page, block_size))],
        "images": [{"asset": "images/" + f, "physical_page": None,
                    "alt_source": "auto"} for f in manifest],
        "markdown": os.path.join(extract_root, book, "markdown.md"),
        "blocks": None,
    }
    cpath = os.path.join(contract_dir, "contract.json")
    json.dump(contract, open(cpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return {"book": book, "blocks": len(info["blocks"]), "images": len(manifest),
            "contract": cpath, "markdown": contract["markdown"]}
