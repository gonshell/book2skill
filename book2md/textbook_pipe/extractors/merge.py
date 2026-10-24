# -*- coding: utf-8 -*-
"""按页码序重合并抽取块（自 gzsx-md/rematch_merge.py 行为保持迁入）。

背景：分块提交按"完成顺序"落盘会导致页序错乱（实测 87-126 曾排在 47-86 前）。
本模块按 ledger 的块起始页升序，从 zip/ex_* 重放合并逻辑，产出页序正确的
<out_root>/<book>/markdown.md 与 images/。
"""
import json
import os
import re
import shutil
import sys
import zipfile

# 默认册序（人教A版数学 5 册，数据；科目配置化后由配置注入）
DEFAULT_BOOKS = ["选择性必修第三册", "选择性必修第二册", "选择性必修第一册", "必修第二册", "必修第一册"]


def merge_one(name, s, e, blocks_root, out_root):
    """重放单块合并（自 rematch_merge.merge_one 行为保持，仅路径参数化）。

    blocks_root: 分块缓存目录（含 <book>/block_{s}-{e}.zip 与 ex_{s}-{e}/）
    out_root:    输出根（写 <out_root>/<book>/markdown.md 与 images/）
    返回 (图片数, "教材页码区间")。
    """
    zpath = os.path.join(blocks_root, name, f"block_{s}-{e}.zip")
    exdir = os.path.join(blocks_root, name, f"ex_{s}-{e}")
    if not os.path.isdir(exdir):
        if not zipfile.is_zipfile(zpath):
            raise FileNotFoundError(f"{zpath} 不存在且无法从 zip 重建")
        os.makedirs(exdir)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(exdir)
    src = None
    if os.path.exists(os.path.join(exdir, "markdown.md")):
        src = exdir
    else:
        for d in sorted(os.listdir(exdir)):
            if os.path.isdir(os.path.join(exdir, d)) and os.path.exists(os.path.join(exdir, d, "markdown.md")):
                src = os.path.join(exdir, d)
                break
    if src is None:
        raise FileNotFoundError(f"{exdir} 内无 markdown.md")

    mj = json.load(open(os.path.join(src, "middle_json.json"), encoding="utf-8"))
    page_to_book = {}
    for p in mj.get("pages", []):
        idx = p.get("page_idx")
        pn = next((b.get("content", [{}])[0].get("content")
                   for b in p.get("blocks", []) if b.get("type") == "page_number"), None)
        if idx is not None:
            page_to_book[idx - s + 2] = pn
    book_first, book_last = page_to_book.get(1), page_to_book.get(e - s + 1)

    bdir = os.path.join(out_root, name)
    os.makedirs(os.path.join(bdir, "images"), exist_ok=True)
    md = open(os.path.join(src, "markdown.md"), encoding="utf-8").read()
    md = re.sub(r"\(images/page_(\d+)_",
                lambda m: f"(images/page_{s + int(m.group(1)) - 1}_", md)

    n_imgs = 0
    srcdir = os.path.join(src, "images")
    if os.path.isdir(srcdir):
        for f in os.listdir(srcdir):
            m = re.match(r"page_(\d+)_(.+)", f)
            if m:
                shutil.copy2(os.path.join(srcdir, f),
                             os.path.join(bdir, "images", f"page_{s + int(m.group(1)) - 1}_{m.group(2)}"))
                n_imgs += 1

    header = f"\n\n<!-- ===== 原书物理页 {s}-{e}"
    if book_first or book_last:
        header += f" · 教材页码 {book_first}-{book_last}"
    header += " ===== -->\n\n"
    with open(os.path.join(bdir, "markdown.md"), "a", encoding="utf-8") as fh:
        fh.write(header + md.rstrip() + "\n")
    return n_imgs, f"{book_first}-{book_last}"


def merge_all(blocks_root, out_root, ledger_path=None, books=None):
    """按 ledger 的 done 块页码序重合并（自 rematch_merge 模块级主流程行为保持迁入）。

    blocks_root: 分块缓存根（含 <book>/ 与 ledger.json）
    out_root:    输出根（<book>/markdown.md 与 images/ 先清空后重建）
    ledger_path: 账本路径，缺省 <blocks_root>/../ledger.json
    books:       册名列表，缺省 DEFAULT_BOOKS
    返回 {book: {"blocks": n, "images": 总图片数, "last_pages": 区间}}；进度走 stderr。
    """
    ledger_path = ledger_path or os.path.join(os.path.dirname(blocks_root.rstrip("/\\")), "ledger.json")
    led = json.load(open(ledger_path, encoding="utf-8"))
    books = books or DEFAULT_BOOKS
    stats = {}
    for name in books:
        blocks = sorted((int(k.split("-")[0]), int(k.split("-")[1]))
                        for k, v in led["books"][name]["blocks"].items() if v == "done")
        bdir = os.path.join(out_root, name)
        imgdir = os.path.join(bdir, "images")
        if os.path.exists(os.path.join(bdir, "markdown.md")):
            os.remove(os.path.join(bdir, "markdown.md"))
        if os.path.isdir(imgdir):
            shutil.rmtree(imgdir, ignore_errors=True)
        print(f"[{name}] {len(blocks)} 块按页码序重合并: {[f'{a}-{b}' for a, b in blocks]}", flush=True, file=sys.stderr)
        total_imgs = 0
        last_pg = "-"
        for s, e in blocks:
            n, pg = merge_one(name, s, e, blocks_root, out_root)
            total_imgs += n
            last_pg = pg
        print(f"  -> images {total_imgs} 张，教材页码区间末块 {last_pg}", flush=True, file=sys.stderr)
        stats[name] = {"blocks": len(blocks), "images": total_imgs, "last_pages": last_pg}
    print("REMATCH-DONE", flush=True, file=sys.stderr)
    return stats


if __name__ == "__main__":
    import argparse
    _p = argparse.ArgumentParser(description="按页码序重合并抽取块（tbp extract 的归一化内核）")
    _p.add_argument("--blocks", required=True, help="分块缓存根目录")
    _p.add_argument("--out", required=True, help="输出根目录")
    _p.add_argument("--ledger", help="账本路径（缺省 <blocks>/../ledger.json）")
    _p.add_argument("books", nargs="*", help="册名列表，缺省默认五册")
    _a = _p.parse_args()
    merge_all(blocks_root=_a.blocks, out_root=_a.out, ledger_path=_a.ledger,
              books=_a.books or None)
