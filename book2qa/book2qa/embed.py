# -*- coding: utf-8 -*-
"""核心层：R4 向量路——编码器与索引（M1c，serving.md §1.2）。

实现约定：
  分词 = BERT WordPiece（vocab.txt，lowercase），max_length 512
  池化 = CLS（BGE 官方 1_Pooling 配置）→ L2 归一化（内积即余弦）
  查询侧加官方指令前缀（BGE v1.5 模型卡要求，短查询→段落检索必需；
  索引侧不加）——漏掉这条 R4 召回会显著劣化
  依赖缺失（onnxruntime/tokenizers/模型文件任一不在）→ R4 不可用 =
  三路正常形态（serving §1.2），调用方降级，不报错
"""
import json
import os

import numpy as np

QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


class Encoder:
    def __init__(self, model_dir):
        from tokenizers import BertWordPieceTokenizer
        import onnxruntime as ort
        vocab = os.path.join(model_dir, "vocab.txt")
        onnx = os.path.join(model_dir, "onnx", "model.onnx")
        if not (os.path.isfile(vocab) and os.path.isfile(onnx)):
            raise FileNotFoundError("模型文件不全：%s" % model_dir)
        self.tok = BertWordPieceTokenizer(vocab, lowercase=True)
        self.tok.enable_truncation(max_length=512)
        self.sess = ort.InferenceSession(onnx,
                                         providers=["CPUExecutionProvider"])
        self.pad_id = self.tok.token_to_id("[PAD]") or 0

    def encode(self, texts, is_query=False):
        """texts → np.ndarray [N, 512]，已 L2 归一化。"""
        if is_query:
            texts = [QUERY_PREFIX + t for t in texts]
        encs = [self.tok.encode(t) for t in texts]
        maxlen = min(512, max(len(e.ids) for e in encs))
        ids_b, mask_b = [], []
        for e in encs:
            ids = e.ids[:maxlen]
            pad = maxlen - len(ids)
            ids_b.append(ids + [self.pad_id] * pad)
            mask_b.append([1] * len(ids) + [0] * pad)
        out = self.sess.run(None, {
            "input_ids": ids_b, "attention_mask": mask_b,
            "token_type_ids": [[0] * maxlen] * len(ids_b)})[0]
        vecs = out[:, 0, :].astype(np.float32)          # CLS 池化
        norm = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.clip(norm, 1e-9, None)


def load_index(data_dir):
    """读 vectors.npz + meta.jsonl → (vectors, meta)；缺失返回 None。"""
    npz = os.path.join(data_dir, "vectors.npz")
    meta = os.path.join(data_dir, "vectors_meta.jsonl")
    if not (os.path.isfile(npz) and os.path.isfile(meta)):
        return None
    arr = np.load(npz)
    rows = [json.loads(l) for l in open(meta, encoding="utf-8") if l.strip()]
    return arr["vectors"], rows


def search(encoder, query, index, top=8):
    """query → [(meta_row, score)]，内积（已归一化即余弦）。"""
    vectors, rows = index
    if not rows:
        return []
    qv = encoder.encode([query], is_query=True)[0]
    sims = vectors @ qv
    order = np.argsort(-sims)[:top]
    return [(rows[i], float(sims[i])) for i in order]
