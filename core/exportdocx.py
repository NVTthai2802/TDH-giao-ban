"""Xuất bản kế hoạch ra Word theo thể thức văn bản hành chính (tham khảo NĐ 30/2020/NĐ-CP).
Cụm từ cần kiểm tra được tô vàng."""
import re

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from .transform import CITY_RE

FONT = "Times New Roman"


def _run(par, text, size=14, bold=False, italic=False, underline=False, hl=False):
    r = par.add_run(text)
    r.font.name = FONT
    r._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
    r.font.size = Pt(size)
    r.bold, r.italic, r.underline = bold, italic, underline
    if hl:
        r.font.highlight_color = WD_COLOR_INDEX.YELLOW
    return r


def _runs(par, text, size=14, bold=False, italic=False, hl_re=None):
    pos = 0
    for m in (hl_re.finditer(text) if hl_re else []):
        if m.start() > pos:
            _run(par, text[pos:m.start()], size, bold, italic)
        _run(par, m.group(0), size, bold, italic, hl=True)
        pos = m.end()
    if pos < len(text):
        _run(par, text[pos:], size, bold, italic)


def _p(container, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0, indent=None, keep=False):
    par = container.add_paragraph()
    f = par.paragraph_format
    f.alignment, f.space_before, f.space_after = align, Pt(before), Pt(after)
    f.line_spacing = 1.15
    if indent is not None:
        f.first_line_indent = indent
    f.keep_with_next = keep
    return par


def _page_field(par):
    r = _run(par, "", 13)
    for tag, val in (("begin", None), ("instr", "PAGE"), ("end", None)):
        if tag == "instr":
            e = OxmlElement("w:instrText")
            e.set(qn("xml:space"), "preserve")
            e.text = val
        else:
            e = OxmlElement("w:fldChar")
            e.set(qn("w:fldCharType"), tag)
        r._element.append(e)


def export(items, profile: dict, path: str, extra_highlight=()):
    pats = [CITY_RE.pattern] + [re.escape(s) for s in extra_highlight if s]
    hl_re = re.compile("|".join(pats))

    d = docx.Document()
    st = d.styles["Normal"]
    st.font.name, st.font.size = FONT, Pt(14)
    st.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
    sec = d.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.top_margin, sec.bottom_margin = Cm(2), Cm(2)
    sec.left_margin, sec.right_margin = Cm(3), Cm(2)
    sec.different_first_page_header_footer = True
    _page_field(sec.header.paragraphs[0])
    sec.header.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ---- Phần đầu: cơ quan ban hành | Quốc hiệu, tiêu ngữ
    t = d.add_table(rows=1, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    left, right = t.rows[0].cells
    left.width, right.width = Cm(6), Cm(10)
    t.columns[0].width, t.columns[1].width = Cm(6), Cm(10)
    p = left.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p, profile.get("co_quan_cap_tren", ""), 13)
    _run(_p(left), profile.get("ten_don_vi", ""), 13, bold=True, underline=True)
    _run(_p(left, before=6), f"Số:      /{profile.get('ky_hieu', '')}", 13)
    p = right.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p, "CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM", 12, bold=True)
    _run(_p(right), "Độc lập - Tự do - Hạnh phúc", 14, bold=True, underline=True)
    _run(_p(right, before=6),
         f"{profile.get('ten_xa', '')}, ngày      tháng      năm {profile.get('nam', '')}", 14, italic=True)

    # ---- Tên loại, trích yếu
    _run(_p(d, before=18), "KẾ HOẠCH", 14, bold=True)
    _run(_p(d, after=12), profile.get("tieu_de", ""), 14, bold=True)

    # ---- Nội dung
    J = WD_ALIGN_PARAGRAPH.JUSTIFY
    for kind, text in items:
        if kind == "intro":          # đoạn căn cứ do người dùng tự nhập: không tô
            _runs(_p(d, J, after=6, indent=Cm(1.27)), text, 14)
        elif kind == "p":
            _runs(_p(d, J, after=6, indent=Cm(1.27)), text, 14, hl_re=hl_re)
        else:
            lv = int(kind[1])
            _runs(_p(d, J, before=6, after=6, indent=Cm(1.27), keep=True), text, 14,
                  bold=True, italic=(lv == 3), hl_re=hl_re)

    # ---- Nơi nhận | Chức danh người ký
    t = d.add_table(rows=1, cols=2)
    t.autofit = False
    left, right = t.rows[0].cells
    left.width, right.width = Cm(8), Cm(8)
    t.columns[0].width, t.columns[1].width = Cm(8), Cm(8)
    p = left.paragraphs[0]
    p.paragraph_format.space_before = Pt(12)
    _run(p, "Nơi nhận:", 12, bold=True, italic=True)
    for ln in profile.get("noi_nhan", "").split("\n"):
        if ln.strip():
            _runs(_p(left, WD_ALIGN_PARAGRAPH.LEFT), ln.strip(), 11, hl_re=None)
    p = right.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(12)
    _run(p, profile.get("chuc_danh_ky", ""), 14, bold=True)
    d.save(path)
    return path
