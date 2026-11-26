"""Kiểm tra và tự sửa dấu hiệu văn AI trong bản AI viết lại (không cần AI).
Quy tắc nằm ở data/quy_tac_van_phong.json, sửa được."""
import json
import re
from pathlib import Path

from .paths import ROOT
RULES_F = ROOT / "data" / "quy_tac_van_phong.json"
_cache = {"mtime": None, "data": None}


def rules() -> dict:
    m = RULES_F.stat().st_mtime if RULES_F.exists() else None
    if m != _cache["mtime"]:
        _cache["data"] = json.loads(RULES_F.read_text(encoding="utf-8")) if m else {"tu_cam": [], "tu_sua": {}}
        _cache["mtime"] = m
    return _cache["data"]


def autofix(text: str) -> str:
    fx = rules().get("tu_sua", {})
    t = text.strip()
    for pat in fx.get("bo_cau_tro_ly", []):
        t = re.sub(pat, "", t, flags=re.I | re.M).strip()
    if fx.get("markdown"):
        t = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), t)
        t = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", t)              # tiêu đề markdown
        t = re.sub(r"(?m)^\s*[*•]\s+", "- ", t)                   # gạch đầu dòng kiểu khác -> "- "
        t = re.sub(r"(?m)^\s*-{3,}\s*$", "", t)                   # đường kẻ ---
        t = t.replace("`", "")
    if fx.get("gach_ngang_dai"):
        t = re.sub(r"\s*—\s*", ", ", t)                           # gạch dài chèn ý
        t = re.sub(r"(?<=\S) – (?=\S)", ", ", t)                  # gạch có dấu cách
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()


def check(text: str, src: str = "") -> list[str]:
    """Các lỗi văn phong có trong bản viết lại mà bản gốc không có."""
    out = []
    low_src = src.lower()
    for r in rules().get("tu_cam", []):
        try:
            ms = [m.group(0) for m in re.finditer(r["mau"], text, flags=re.I | re.M)]
        except re.error:
            continue
        ms = [m for m in ms if m.strip().lower() not in low_src]
        if ms and r["loi"] not in out:
            out.append(r["loi"])
    if "—" in text:
        out.append("còn gạch ngang dài (—)")
    return out
