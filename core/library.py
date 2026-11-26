"""Kho tài liệu tham khảo (nghị quyết, quy định, hướng dẫn, tài liệu nội bộ).

Tìm kiếm bằng từ khoá (BM25) trên từng đoạn — không cần mô hình thêm, chạy nhanh trên máy yếu.
Tiếng Việt: dùng cả âm tiết đơn và cặp âm tiết liền nhau ("tạm đình", "đình chỉ") để bắt được từ ghép.
"""
import json
import math
import re
import time
import uuid
from collections import Counter
from pathlib import Path

CHUNK = 700          # số ký tự mỗi đoạn


def tokens(text: str) -> list[str]:
    w = re.findall(r"\w+", text.lower())
    return w + [a + "_" + b for a, b in zip(w, w[1:])]


def chunks(text: str) -> list[str]:
    from .ingest import paragraphs
    out, cur = [], ""
    for p in paragraphs(text):
        if cur and len(cur) + len(p) > CHUNK:
            out.append(cur)
            cur = ""
        cur = (cur + "\n" + p).strip()
        while len(cur) > CHUNK * 2:          # đoạn quá dài: cắt theo câu
            cut = cur.rfind(". ", 0, CHUNK) + 1 or CHUNK
            out.append(cur[:cut].strip())
            cur = cur[cut:].strip()
    if cur:
        out.append(cur)
    return out


class Library:
    def __init__(self, path: Path):
        self.path = path
        self.data = {"docs": [], "chunks": []}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def docs(self):
        return self.data["docs"]

    def add(self, name: str, text: str) -> dict:
        did = uuid.uuid4().hex[:8]
        cs = chunks(text)
        doc = {"id": did, "name": name, "chars": len(text), "chunks": len(cs),
               "added": time.strftime("%d/%m/%Y")}
        self.data["docs"].append(doc)
        self.data["chunks"] += [{"doc": did, "text": c} for c in cs]
        self.save()
        return doc

    def delete(self, did: str):
        self.data["docs"] = [d for d in self.data["docs"] if d["id"] != did]
        self.data["chunks"] = [c for c in self.data["chunks"] if c["doc"] != did]
        self.save()

    def search(self, query: str, k: int = 3, max_chars: int = 1800) -> list[dict]:
        """Trả về các đoạn liên quan nhất: [{'name', 'text', 'score'}]."""
        cs = self.data["chunks"]
        if not cs:
            return []
        names = {d["id"]: d["name"] for d in self.data["docs"]}
        docs_tok = [Counter(tokens(c["text"])) for c in cs]
        n = len(cs)
        avg = sum(sum(t.values()) for t in docs_tok) / n
        df = Counter()
        for t in docs_tok:
            df.update(t.keys())
        q = set(tokens(query))
        k1, b = 1.5, 0.75
        scored = []
        for c, tf in zip(cs, docs_tok):
            dl = sum(tf.values())
            s = 0.0
            for w in q:
                f = tf.get(w)
                if f:
                    idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                    s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / avg))
            if s > 0:
                scored.append((s, c))
        scored.sort(key=lambda x: -x[0])
        out, used = [], 0
        for s, c in scored[:k]:
            if used + len(c["text"]) > max_chars and out:
                break
            out.append({"name": names.get(c["doc"], "?"), "text": c["text"], "score": round(s, 1)})
            used += len(c["text"])
        return out
