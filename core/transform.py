"""Luật chuyển đổi không cần AI: thay thế cụm từ, phát hiện nhiệm vụ cấp trên,
kiểm tra mốc thời hạn, chống 'bịa số liệu', đánh số lại các mục."""
import calendar
import datetime as dt
import re

# Thuật ngữ thường chỉ nhiệm vụ của cấp trên -> tô vàng để cán bộ xem lại
CITY_RE = re.compile(
    r"\b(?:PC|PX|PA|PV|PH)0?\d+\b|Giám đốc Công an|Giám đốc CATP|Công an thành phố|Công an TP|"
    r"Phòng(?= [A-ZĐ])|Viện [Kk]iểm sát|Tòa án|Toà án|Cơ quan CSĐT|Cơ quan Cảnh sát điều tra|"
    r"Đảng ủy Công an|Công an cấp huyện"
)
PAREN = re.compile(r"\(([^()]*[Hh]oàn thành[^()]*)\)")
NUM = re.compile(r"\d+(?:[./]\d+)*")


def flag_terms(text: str) -> list[str]:
    seen = []
    for m in CITY_RE.finditer(text):
        if m.group(0) not in seen:
            seen.append(m.group(0))
    return seen


def count_flags(sec: dict) -> int:
    return len(CITY_RE.findall(sec["title"] + "\n" + "\n".join(sec["body"])))


def _eom(y: int, m: int) -> dt.date:
    return dt.date(y, m, calendar.monthrange(y, m)[1])


def deadlines(text: str) -> list[tuple[str, dt.date]]:
    """Tìm mốc trong cụm '(Hoàn thành ...)': ngày cụ thể, tháng m/yyyy, quý I-IV năm yyyy."""
    out = []
    for pm in PAREN.finditer(text):
        s = pm.group(1)
        for m in re.finditer(r"(\d{1,2})/(\d{1,2})/(\d{4})", s):
            try:
                out.append((m.group(0), dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))))
            except ValueError:
                pass
        for m in re.finditer(r"[Tt]háng\s*(\d{1,2})/(\d{4})", s):
            mo, y = int(m.group(1)), int(m.group(2))
            if 1 <= mo <= 12:
                out.append((m.group(0), _eom(y, mo)))
        for m in re.finditer(r"[Qq]uý\s*([IVLHl|1-4]{1,3})\s*(?:năm\s*)?(\d{4})", s):
            raw = m.group(1)
            if raw.isdigit():
                q = int(raw)
            else:   # OCR: "HI", "lII" -> "III"
                q = {"I": 1, "II": 2, "III": 3, "IV": 4}.get(re.sub(r"[LHl|1]", "I", raw))
            if not q or not 1 <= q <= 4:
                continue
            out.append((m.group(0), _eom(int(m.group(2)), q * 3)))
    return out


def ref_date(profile: dict) -> dt.date:
    s = (profile.get("ngay_ban_hanh") or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return dt.date.today()


def apply_subs(text: str, profile: dict) -> str:
    for pair in profile.get("thay_the", []):
        if len(pair) == 2 and pair[0]:
            text = text.replace(pair[0], pair[1].format(**profile))
    return text


def new_numbers(src: str, out: str, extra: str = "") -> list[str]:
    """Các con số có trong bản viết lại nhưng KHÔNG có trong bản gốc / thông tin xã."""
    known = set(NUM.findall(src)) | set(NUM.findall(extra))
    return sorted(set(NUM.findall(out)) - known)


def _roman(n: int) -> str:
    vals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    r = ""
    for v, s in vals:
        while n >= v:
            r += s
            n -= v
    return r


def assemble(parsed: dict, decisions: dict, profile: dict, renumber: bool = True) -> list[tuple[str, str]]:
    """Ghép bản kế hoạch xã: list (loại, nội dung), loại = intro | h1 | h2 | h3 | p."""
    items = [("intro", p) for p in profile.get("doan_mo_dau", "").split("\n") if p.strip()]
    c = [0, 0, 0]
    for s in parsed["sections"]:
        d = decisions.get(s["id"], {})
        if d.get("action") == "drop":
            continue
        lv = s["level"]
        num = s["num"]
        if renumber:
            c[lv - 1] += 1
            for k in range(lv, 3):
                c[k] = 0
            num = _roman(c[0]) + "." if lv == 1 else (f"{c[1]}." if lv == 2 else f"{c[1]}.{c[2]}.")
        items.append((f"h{lv}", f"{num} {apply_subs(d.get('title') or s['title'], profile)}"))
        body = d.get("text")
        if body is None:
            body = "\n".join(s["body"])
        for p in apply_subs(body, profile).split("\n"):
            if p.strip():
                items.append(("p", p.strip()))
    return items
