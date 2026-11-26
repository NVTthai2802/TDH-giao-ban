"""Module giao ban hằng ngày: danh sách tổ, kho ý kiến riêng từng người, luân phiên người phát biểu,
xuất biên bản giao ban ra Word theo mẫu của tổ.

Lịch họp: thứ 2 đến thứ 6, kể cả ngày lễ.
Luân phiên: hàng đợi theo thứ tự danh sách; mỗi buổi lấy N người đầu hàng đợi đang có mặt,
họ chuyển xuống cuối. Người vắng giữ nguyên vị trí nên được phát biểu ở buổi kế tiếp.
"""
import copy
import datetime as dt
import json
import uuid
from pathlib import Path

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, Twips

from .exportdocx import FONT, _p, _run

THU = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]

DEFAULT = {
    "cau_hinh": {
        "co_quan": "CÔNG AN XÃ AN LÃO",
        "to": "TỔ PCTP",
        "dia_danh": "An Lão",
        "dia_diem": "phòng làm việc Tổ Phòng chống tội phạm Công an xã An Lão, thành phố Hải Phòng",
        "ten_to": "Tổ Phòng chống tội phạm - Công an xã An Lão",
        "gio_bat_dau": "07h30'",
        "gio_ket_thuc": "08h30'",
        "chu_toa": "",           # id thành viên
        "thu_ky": "",            # id thành viên
        "so_nguoi_y_kien": 2,
        "noi_dung_mac_dinh": (
            "Đ/c chủ tọa đánh giá nhận xét công tác đã làm được của CBCS trong tổ. Đ/c chủ tọa yêu cầu các "
            "đồng chí ca trực báo cáo tình hình ca trực, tuần tra kiểm soát theo kế hoạch của Công an xã "
            "An Lão có phát sinh vụ việc nào không."),
        "ket_luan_mac_dinh": (
            "Đ/c chủ tọa nhất trí với các ý kiến tham gia. Yêu cầu CBCS thực hiện nghiêm các văn bản đã "
            "quán triệt và thực hiện theo đúng quy định của pháp luật."),
    },
    "thong_bao": {      # gửi trước giờ giao ban (tắt mặc định: đây là phần duy nhất đưa dữ liệu ra ngoài)
        "bat": False, "gio_gui": "07:00", "dinh_kem": True,
        "email": {"bat": False, "smtp": "smtp.gmail.com", "cong": 465, "tai_khoan": "", "mat_khau": "",
                  "nguoi_nhan": ""},
        "telegram": {"bat": False, "token": "", "chat_ids": ""},
        "da_gui": "", "nhat_ky": [],
    },
    "thanh_vien": [],   # {id, ten, chuc_vu, luan_phien, vang_dai_ngay, y_kien: [str]}
    "hang_doi": [],     # thứ tự lượt phát biểu
    "lich_su": {},      # "yyyy-mm-dd" -> biên bản đã chốt
}


def new_id():
    return uuid.uuid4().hex[:8]


def fmt_date(d: dt.date):
    return f"{d.day:02d} tháng {d.month} năm {d.year}"


def parse_date(s) -> dt.date:
    if isinstance(s, dt.date):
        return s
    s = s.strip()
    if "/" in s:
        d, m, y = (int(x) for x in s.split("/"))
        return dt.date(y, m, d)
    return dt.date.fromisoformat(s)


def ngay_hop(tu, den):
    """Các ngày họp (T2–T6, kể cả ngày lễ) trong khoảng [tu, den]."""
    d, den = parse_date(tu), parse_date(den)
    out = []
    while d <= den:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def ngay_hop_tiep(d: dt.date):
    d += dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


class GiaoBan:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = copy.deepcopy(DEFAULT)
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                self.data.update(saved)
                self.data["cau_hinh"] = {**DEFAULT["cau_hinh"], **saved.get("cau_hinh", {})}
                tb = saved.get("thong_bao", {})
                self.data["thong_bao"] = {**copy.deepcopy(DEFAULT["thong_bao"]), **tb,
                                          "email": {**DEFAULT["thong_bao"]["email"], **tb.get("email", {})},
                                          "telegram": {**DEFAULT["thong_bao"]["telegram"], **tb.get("telegram", {})}}
            except Exception:
                pass

    # ---------- lưu trữ
    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def member(self, mid):
        return next((m for m in self.data["thanh_vien"] if m["id"] == mid), None)

    def _sync_queue(self):
        ids = [m["id"] for m in self.data["thanh_vien"]]
        q = [i for i in self.data["hang_doi"] if i in ids]
        q += [i for i in ids if i not in q]
        self.data["hang_doi"] = q

    def set_config(self, cfg: dict):
        self.data["cau_hinh"].update({k: v for k, v in cfg.items() if k in DEFAULT["cau_hinh"]})
        self.data["cau_hinh"]["so_nguoi_y_kien"] = max(1, int(self.data["cau_hinh"]["so_nguoi_y_kien"] or 2))

    def set_members(self, members: list):
        """Thay cả danh sách (giữ id cũ, cấp id mới cho người mới). Thứ tự danh sách = thứ tự lượt
        cho người mới thêm; người cũ giữ vị trí trong hàng đợi."""
        out = []
        for m in members:
            ten = (m.get("ten") or "").strip()
            if not ten:
                continue
            yk = m.get("y_kien") or []
            if isinstance(yk, str):
                yk = [b.strip() for b in yk.replace("\r", "").split("\n\n")]
            out.append({
                "id": m.get("id") or new_id(),
                "ten": ten,
                "chuc_vu": (m.get("chuc_vu") or "").strip(),
                "luan_phien": bool(m.get("luan_phien", True)),
                "vang_dai_ngay": (m.get("vang_dai_ngay") or "").strip(),
                "y_kien": [y for y in yk if y.strip()],
            })
        self.data["thanh_vien"] = out
        self._sync_queue()

    def reset_rotation(self):
        """Xếp lại lượt theo đúng thứ tự danh sách hiện tại."""
        self.data["hang_doi"] = [m["id"] for m in self.data["thanh_vien"]]

    # ---------- chọn người và ý kiến
    def _last_used(self, mid):
        """{chỉ số ý kiến: ngày dùng gần nhất} của một người."""
        used = {}
        for ngay, bb in self.data["lich_su"].items():
            for p in bb.get("phat_bieu", []):
                if p["id"] == mid and p.get("y_kien_idx") is not None:
                    used[p["y_kien_idx"]] = max(used.get(p["y_kien_idx"], ""), ngay)
        return used

    def pick_opinion(self, mid):
        m = self.member(mid)
        if not m or not m["y_kien"]:
            return None, ""
        used = self._last_used(mid)
        # câu chưa dùng lần nào trước (theo thứ tự kho), rồi đến câu dùng lâu nhất
        idx = min(range(len(m["y_kien"])), key=lambda i: (used.get(i, ""), i))
        return idx, m["y_kien"][idx]

    def speakers(self, vang_ids):
        cfg = self.data["cau_hinh"]
        n = int(cfg["so_nguoi_y_kien"])
        skip = set(vang_ids) | {cfg["chu_toa"]}
        out = []
        for mid in self.data["hang_doi"]:
            m = self.member(mid)
            if m and m["luan_phien"] and mid not in skip:
                out.append(mid)
            if len(out) == n:
                break
        return out

    # ---------- biên bản
    def latest_date(self):
        return max(self.data["lich_su"]) if self.data["lich_su"] else None

    def suggest_date(self, today=None):
        last = self.latest_date()
        today = today or dt.date.today()
        if last:
            return ngay_hop_tiep(dt.date.fromisoformat(last)).isoformat()
        d = today
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        return d.isoformat()

    def draft(self, ngay, vang=None):
        """Bản nháp biên bản cho một ngày. Ngày đã chốt thì trả lại đúng bản đã lưu."""
        d = parse_date(ngay)
        key = d.isoformat()
        if key in self.data["lich_su"]:
            bb = copy.deepcopy(self.data["lich_su"][key])
            bb["da_chot"] = True
            return bb
        if d.weekday() >= 5:
            raise ValueError(f"{d:%d/%m/%Y} là {THU[d.weekday()]}, không có lịch giao ban.")
        last = self.latest_date()
        if last and key < last:
            raise ValueError(f"Ngày {d:%d/%m/%Y} trước buổi đã chốt gần nhất ({dt.date.fromisoformat(last):%d/%m/%Y}). "
                             "Luân phiên chỉ đi tiếp từ buổi gần nhất.")
        cfg = self.data["cau_hinh"]
        if vang is None:   # mặc định: người đang vắng dài ngày
            vang = [{"id": m["id"], "ly_do": m["vang_dai_ngay"]}
                    for m in self.data["thanh_vien"] if m["vang_dai_ngay"]]
        vang_ids = [v["id"] for v in vang]
        phat_bieu = []
        for mid in self.speakers(vang_ids):
            idx, text = self.pick_opinion(mid)
            phat_bieu.append({"id": mid, "y_kien_idx": idx, "text": text})
        return {
            "ngay": key, "da_chot": False,
            "vang": vang,
            "noi_dung": cfg["noi_dung_mac_dinh"],
            "phat_bieu": phat_bieu,
            "ket_luan": cfg["ket_luan_mac_dinh"],
            "them": "",
            "gio_bat_dau": cfg["gio_bat_dau"], "gio_ket_thuc": cfg["gio_ket_thuc"],
            "chu_toa": cfg["chu_toa"], "thu_ky": cfg["thu_ky"],
        }

    def commit(self, bb):
        key = parse_date(bb["ngay"]).isoformat()
        if key in self.data["lich_su"]:
            # sửa lại nội dung chữ của buổi đã chốt, không đổi lượt
            old = self.data["lich_su"][key]
            for k in ("noi_dung", "ket_luan", "them", "gio_bat_dau", "gio_ket_thuc"):
                if k in bb:
                    old[k] = bb[k]
            for p_new, p_old in zip(bb.get("phat_bieu", []), old["phat_bieu"]):
                p_old["text"] = p_new.get("text", p_old["text"])
            return old
        last = self.latest_date()
        if last and key < last:
            raise ValueError("Không chốt được ngày trước buổi gần nhất.")
        rec = {k: bb.get(k) for k in ("ngay", "vang", "noi_dung", "phat_bieu", "ket_luan", "them",
                                       "gio_bat_dau", "gio_ket_thuc", "chu_toa", "thu_ky")}
        rec["ngay"] = key
        rec["hang_doi_truoc"] = list(self.data["hang_doi"])
        rec["ten_snapshot"] = {m["id"]: {"ten": m["ten"], "chuc_vu": m["chuc_vu"]} for m in self.data["thanh_vien"]}
        rec["tong_so"] = len(self.data["thanh_vien"])
        spoke = [p["id"] for p in rec["phat_bieu"]]
        self.data["hang_doi"] = [i for i in self.data["hang_doi"] if i not in spoke] + spoke
        self.data["lich_su"][key] = rec
        return rec

    def undo_latest(self):
        last = self.latest_date()
        if not last:
            return None
        rec = self.data["lich_su"].pop(last)
        self.data["hang_doi"] = rec.get("hang_doi_truoc", self.data["hang_doi"])
        self._sync_queue()
        return last

    def batch(self, tu, den):
        """Chốt liền nhiều ngày (không ai vắng ngoài người vắng dài ngày). Bỏ qua ngày đã chốt."""
        done = []
        for d in ngay_hop(tu, den):
            if d.isoformat() in self.data["lich_su"]:
                done.append(d.isoformat())
                continue
            done.append(self.commit(self.draft(d))["ngay"])
        return done

    # ---------- thông báo trước giờ họp
    MASK = "••••••"

    def public(self):
        """Dữ liệu gửi lên giao diện: che mật khẩu email và token bot."""
        d = copy.deepcopy(self.data)
        tb = d["thong_bao"]
        for sec, k in (("email", "mat_khau"), ("telegram", "token")):
            if tb[sec].get(k):
                tb[sec][k] = self.MASK
        return d

    def set_notify(self, cfg: dict):
        tb = self.data["thong_bao"]
        for k in ("bat", "gio_gui", "dinh_kem"):
            if k in cfg:
                tb[k] = cfg[k]
        for sec, secret in (("email", "mat_khau"), ("telegram", "token")):
            new = dict(cfg.get(sec, {}))
            if new.get(secret) == self.MASK:
                new.pop(secret)
            tb[sec].update(new)

    def notice(self, bb):
        """Tiêu đề và nội dung tin nhắn báo trước cho một buổi."""
        d = parse_date(bb["ngay"])
        subject = f"Giao ban {THU[d.weekday()]}, {d:%d/%m/%Y} lúc {bb.get('gio_bat_dau', '')}"
        lines = ["Phát biểu: " + (", ".join("đ/c " + self._name(bb, p["id"]) for p in bb["phat_bieu"]) or "chưa có")]
        if bb.get("vang"):
            lines.append("Vắng: " + ", ".join(self._name(bb, v["id"]) + (f" ({v['ly_do']})" if v.get("ly_do") else "")
                                             for v in bb["vang"]))
        if bb.get("chu_toa"):
            lines.append("Chủ tọa: đ/c " + self._name(bb, bb["chu_toa"]))
        lines.append("")
        lines.append("Ý kiến dự kiến:")
        for p in bb["phat_bieu"]:
            lines.append(f"- Đ/c {self._name(bb, p['id'])}: {p.get('text') or '(chưa có trong kho ý kiến)'}")
        lines.append("")
        lines.append("Biên bản dự thảo do phần mềm lập sẵn. Có thay đổi thì sửa trong phần mềm, mục Giao ban.")
        return subject, "\n".join(lines)

    def log(self, text):
        nk = self.data["thong_bao"].setdefault("nhat_ky", [])
        nk.insert(0, text)
        del nk[30:]

    # ---------- xem trước lượt
    def preview_rotation(self, k=10):
        """Dự kiến người phát biểu k buổi tới (giả định không ai vắng thêm)."""
        q = list(self.data["hang_doi"])
        saved = self.data["hang_doi"]
        d = dt.date.fromisoformat(self.suggest_date())
        out = []
        try:
            self.data["hang_doi"] = q
            vang = [m["id"] for m in self.data["thanh_vien"] if m["vang_dai_ngay"]]
            for _ in range(k):
                sp = self.speakers(vang)
                out.append({"ngay": d.isoformat(), "nguoi": [self.member(i)["ten"] for i in sp]})
                self.data["hang_doi"] = [i for i in self.data["hang_doi"] if i not in sp] + sp
                d = ngay_hop_tiep(d)
        finally:
            self.data["hang_doi"] = saved
        return out

    # ---------- Word
    def _name(self, bb, mid):
        m = self.member(mid) or (bb.get("ten_snapshot") or {}).get(mid)
        return m["ten"] if m else "(không rõ)"

    def _role(self, bb, mid):
        m = self.member(mid) or (bb.get("ten_snapshot") or {}).get(mid)
        return m["chuc_vu"] if m else ""

    def export_docx(self, bb, path):
        cfg = self.data["cau_hinh"]
        d = parse_date(bb["ngay"])
        doc = docx.Document()
        st = doc.styles["Normal"]
        st.font.name, st.font.size = FONT, Pt(14)
        st.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
        sec = doc.sections[0]
        sec.page_width, sec.page_height = Cm(21), Cm(29.7)
        sec.top_margin, sec.bottom_margin = Twips(964), Twips(964)
        sec.left_margin, sec.right_margin = Twips(1247), Twips(1021)

        # phần đầu
        t = doc.add_table(rows=1, cols=2)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        widths = (Twips(3403), Twips(6378))
        for i, w in enumerate(widths):
            t.columns[i].width = w
            t.rows[0].cells[i].width = w
        left, right = t.rows[0].cells
        p = left.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(p, cfg["co_quan"], 13)
        _run(_p(left), cfg["to"], 13, bold=True, underline=True)
        p = right.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(p, "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", 13, bold=True)
        _run(_p(right), "Độc lập – Tự do – Hạnh phúc", 14, bold=True, underline=True)
        _run(_p(right, before=6), f"{cfg['dia_danh']}, ngày {fmt_date(d)}", 14, italic=True)

        J = WD_ALIGN_PARAGRAPH.JUSTIFY
        ind = Twips(680)

        def para(text, bold=False, italic=False, before=0, after=0, indent=ind):
            par = _p(doc, J, before=before, after=after, indent=indent)
            par.paragraph_format.line_spacing = 1.0
            _run(par, text, 14, bold=bold, italic=italic)
            return par

        _run(_p(doc, before=12, after=6), "BIÊN BẢN GIAO BAN", 14, bold=True)
        para(f"Vào hồi {bb['gio_bat_dau']} ngày {fmt_date(d)} tại {cfg['dia_diem']}. "
             f"{cfg['ten_to']} tiến hành giao ban hàng ngày.")
        para("Thành phần tham gia:")
        tong = bb.get("tong_so") or len(self.data["thanh_vien"])
        vang = bb.get("vang") or []
        co_mat = tong - len(vang)
        para(f"- Tổng số: {tong:02d} đ/c")
        para(f"- Có mặt: {co_mat:02d} đ/c")
        if vang:
            ly = ", ".join(f"đ/c {self._name(bb, v['id'])}" + (f" {v['ly_do']}" if v.get("ly_do") else "")
                           for v in vang)
            para(f"- Vắng mặt: {len(vang):02d} đ/c ({ly})")
        else:
            para("- Vắng mặt: 0 đ/c")
        if bb.get("chu_toa"):
            para(f"- Đ/c {self._name(bb, bb['chu_toa'])} - {self._role(bb, bb['chu_toa'])} - Chủ tọa.")
        if bb.get("thu_ky"):
            para(f"- Đ/c {self._name(bb, bb['thu_ky'])} - {self._role(bb, bb['thu_ky'])} - Thư ký.")

        _run(_p(doc, before=3, after=3), "NỘI DUNG", 14, bold=True)
        for block in (bb.get("noi_dung") or "").replace("\r", "").split("\n"):
            if block.strip():
                para(block.strip() if block.strip().startswith("-") else "- " + block.strip())
        for block in (bb.get("them") or "").replace("\r", "").split("\n"):
            if block.strip():
                para(block.strip() if block.strip().startswith("-") else "- " + block.strip())
        para("- Ý kiến tham gia:")
        for pb in bb.get("phat_bieu", []):
            text = (pb.get("text") or "").strip() or "Nhất trí với đánh giá, nhận xét của đ/c chủ tọa."
            par = _p(doc, J, indent=ind)
            par.paragraph_format.line_spacing = 1.0
            _run(par, f"+ Đ/c {self._name(bb, pb['id'])}: ", 14)
            _run(par, text, 14)
        if (bb.get("ket_luan") or "").strip():
            para("+ " + bb["ket_luan"].strip())
        para(f"Không còn ý kiến tham gia, tiến hành biểu quyết: {co_mat}/{co_mat} = 100% nhất trí. "
             f"Cuộc họp kết thúc vào hồi {bb['gio_ket_thuc']} cùng ngày.")

        # chữ ký
        t = doc.add_table(rows=1, cols=2)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        for i, w in enumerate((Twips(4962), Twips(4054))):
            t.columns[i].width = w
            t.rows[0].cells[i].width = w
        for cell, chuc, mid in ((t.rows[0].cells[0], "THƯ KÝ", bb.get("thu_ky")),
                                (t.rows[0].cells[1], "CHỦ TỌA", bb.get("chu_toa"))):
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(12)
            _run(p, chuc, 14, bold=True)
            for _ in range(4):
                _p(cell)
            _run(_p(cell), self._name(bb, mid) if mid else "", 14, bold=True)
        doc.save(path)
        return path
