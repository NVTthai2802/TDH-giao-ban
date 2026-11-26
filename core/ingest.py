"""Đọc tài liệu (txt / docx / pdf / ảnh chụp) thành văn bản, rồi tách thành các mục."""
from .paths import ROOT
import os
import re
from pathlib import Path

COMMON = ("của", "và", "các", "trong", "được", "để", "công", "tác", "thực", "hiện")
BULLET = re.compile(r"^\s*[-–•]\s+")
HEAD = re.compile(r"^\s*(?P<num>[IVX]{1,4}|\d{1,2}(?:\.\d{1,2}){0,2})\.\s+(?P<title>\S.*)$")
# Tiêu đề cấp I viết hoa; OCR hay đọc nhầm I -> L, H, l, 1, |  (vd "IL.", "HI.")
ROMAN_OCR = re.compile(r"^\s*(?P<num>[IVXLHl1|]{1,4})[.,]\s+(?P<title>.{4,})$")
PAGENO = re.compile(r"^\s*\d{1,2}\s*$")
TAIL = re.compile(r"^\s*Nơi nhận", re.I)
MAX_HEAD = 320   # khối dài hơn thế coi là đoạn văn có đánh số, không phải tiêu đề
ROMANS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


# ---------------------------------------------------------------- đọc file
def read_any(path: str) -> str:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".txt", ".md"):
        return p.read_text(encoding="utf-8", errors="ignore")
    if ext == ".docx":
        import docx
        d = docx.Document(str(p))
        return "\n\n".join(par.text for par in d.paragraphs if par.text.strip())
    if ext == ".pdf":
        from pypdf import PdfReader
        text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
        if len(text.strip()) < 200:
            raise ValueError("PDF này là bản quét, không có lớp chữ. Hãy xuất từng trang thành ảnh JPG/PNG rồi tải lên.")
        return text
    if ext in IMAGE_EXT:
        return ocr_image(str(p))
    raise ValueError(f"Chưa hỗ trợ định dạng {ext}")


def _tesseract():
    import shutil
    import pytesseract
    la = os.environ.get("LOCALAPPDATA", "")
    bundled = ROOT / "tesseract" / "tesseract.exe"
    if bundled.exists():   # bản Tesseract đóng gói kèm phần mềm
        os.environ["TESSDATA_PREFIX"] = str(bundled.parent / "tessdata")
    cands = [str(bundled) if bundled.exists() else None,
             os.environ.get("TESSERACT_CMD"),
             r"C:\Program Files\Tesseract-OCR\tesseract.exe",
             r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
             os.path.join(la, "Programs", "Tesseract-OCR", "tesseract.exe") if la else None,
             os.path.join(la, "Tesseract-OCR", "tesseract.exe") if la else None,
             shutil.which("tesseract")]
    for c in cands:
        if c and os.path.exists(c):
            pytesseract.pytesseract.tesseract_cmd = c
            break
    else:
        raise RuntimeError(
            "Chưa cài Tesseract OCR (cần để đọc ảnh chụp). Cài bản Windows của UB Mannheim, "
            "ở bước 'Additional language data' chọn Vietnamese, rồi mở lại chay.bat. "
            "Nếu đã cài ở thư mục khác, đặt biến môi trường TESSERACT_CMD trỏ tới tesseract.exe.")
    try:
        langs = pytesseract.get_languages(config="")
    except Exception:
        langs = []
    if langs and "vie" not in langs:
        raise RuntimeError(
            "Tesseract đã cài nhưng thiếu gói tiếng Việt. Chạy lại bộ cài Tesseract, "
            "ở bước 'Additional language data' tích chọn Vietnamese.")
    return pytesseract


def _score(text: str) -> int:
    low = f" {text.lower()} "
    return sum(low.count(f" {w} ") for w in COMMON)


def ocr_image(path: str, lang: str = "vie") -> str:
    """OCR ảnh chụp văn bản; tự xoay ảnh bị nghiêng 90/180/270 độ."""
    from PIL import Image, ImageOps
    tess = _tesseract()
    img = ImageOps.exif_transpose(Image.open(path)).convert("L")
    small = img.copy()
    small.thumbnail((1400, 1400))
    best = max((0, 90, 180, 270),
               key=lambda a: _score(tess.image_to_string(small.rotate(a, expand=True), lang=lang)))
    return tess.image_to_string(img.rotate(best, expand=True), lang=lang)


def clean_ocr(text: str) -> str:
    """Sửa vài lỗi OCR hay gặp trong văn bản Công an."""
    text = text.replace("\u2044", "/").replace("\u2215", "/")
    # mã đơn vị: PC0I -> PC01, PXO5 -> PX05
    text = re.sub(r"\b(P[CXAVH])([0-9OIl]{2})\b",
                  lambda m: m.group(1) + m.group(2).replace("O", "0").replace("I", "1").replace("l", "1"), text)
    return text


def _head_line(t: str):
    """(num, title, level) nếu chuỗi t có dạng tiêu đề mục."""
    m = ROMAN_OCR.match(t)
    if m and m["title"] == m["title"].upper() and any(c.isalpha() for c in m["title"]):
        return m["num"], m["title"].strip(), 1
    m = HEAD.match(t)
    if m and m["title"][:1].isupper() or (m and m["title"][:1] in "“\"'"):
        num = m["num"]
        return num, m["title"].strip(), 1 if re.fullmatch(r"[IVX]+", num) else num.count(".") + 2
    return None


def _is_title(t: str) -> bool:
    return not t.rstrip().endswith((".", ";", ":", ","))


def split_head(lines: list[str]):
    """Nhận một khối dòng; trả về ((num, title, level), phần thân còn lại) nếu khối mở đầu bằng tiêu đề."""
    whole = " ".join(x.strip() for x in lines)
    if not _head_line(whole) and not _head_line(lines[0].strip()):
        return None
    if len(whole) <= MAX_HEAD and _is_title(whole) and _head_line(whole):
        return _head_line(whole), ""
    # tiêu đề (1-2 dòng) dính liền với đoạn thân phía sau
    for k in range(min(2, len(lines) - 1)):
        title = " ".join(x.strip() for x in lines[:k + 1])
        nxt = lines[k + 1].strip()
        rest = " ".join(x.strip() for x in lines[k + 1:])
        h = _head_line(title)
        if h and _is_title(title) and (nxt[:1].isupper() or BULLET.match(nxt)) and len(rest) >= 40:
            return h, rest
    return None


# ---------------------------------------------------------------- tách mục
def blocks(text: str) -> list[list[str]]:
    """Gom dòng thành khối (đoạn). Khối bắt đầu bằng chữ thường là phần OCR tách nhầm -> nối vào khối trước."""
    out, cur = [], []
    for ln in text.replace("\r", "").split("\n"):
        if not ln.strip():
            if cur:
                out.append(cur)
                cur = []
            continue
        if PAGENO.match(ln):
            continue
        if cur and (BULLET.match(ln) or HEAD.match(ln) or ROMAN_OCR.match(ln) or TAIL.match(ln)):
            out.append(cur)
            cur = []
        cur.append(ln.strip())
    if cur:
        out.append(cur)
    merged = []
    for b in out:
        if merged and b[0][:1].islower():
            merged[-1].extend(b)
        else:
            merged.append(b)
    return merged


def paragraphs(text: str) -> list[str]:
    return [" ".join(b) for b in blocks(text)]


def parse(text: str) -> dict:
    secs, intro, tail, cur, in_tail, n1 = [], [], [], None, False, 0
    for b in blocks(clean_ocr(text)):
        p = " ".join(b)
        if TAIL.match(p):
            in_tail = True
        if in_tail:
            tail.append(p)
            continue
        sh = split_head(b)
        if sh:
            (num, title, level), rest = sh
            if level == 1:
                n1 += 1
                num = ROMANS[n1 - 1] if n1 <= len(ROMANS) else num
            cur = {"id": f"s{len(secs) + 1}", "num": num + ".", "title": title, "level": level, "body": []}
            secs.append(cur)
            if rest:
                cur["body"].append(rest)
        elif cur is None:
            intro.append(p)
        else:
            cur["body"].append(p)
    return {"intro": intro, "sections": secs, "tail": tail}


def body_text(sec: dict) -> str:
    return "\n".join(sec["body"])
