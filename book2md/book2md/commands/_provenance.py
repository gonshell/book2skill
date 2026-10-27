# -*- coding: utf-8 -*-
"""provenance.json 构建（docs/spec-cli.md §6.3）。

版本指纹纪律：网关未上报的字段一律 None——缺口显式可见，禁止占位假值。
"""
import hashlib
import json
import os


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(pdf_path, adapter, api, tier, extracted_at):
    """组装 provenance dict（不含落盘）。"""
    from book2md.extractors.mineru import collect_fingerprint
    return {
        "schema": "b2m.provenance/v1",
        "source_pdf": {"name": os.path.basename(pdf_path), "sha256": sha256_file(pdf_path)},
        "adapter": adapter,
        "gateway": {"endpoint": api, "tier": tier},
        "backend": collect_fingerprint(),
        "contract": "b2m.extraction/v1",
        "extracted_at": extracted_at,
    }


def write(pdf_path, adapter, api, tier, extracted_at, out_path):
    doc = build(pdf_path, adapter, api, tier, extracted_at)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(doc, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out_path
