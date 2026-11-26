#!/usr/bin/env python3
"""Ứng dụng lập kế hoạch Công an xã từ kế hoạch cấp trên — chạy hoàn toàn trên máy.

  python app.py                         -> mở giao diện tại http://127.0.0.1:8765
  python app.py --cli <file...> --out kq.docx [--ai]   -> chạy không giao diện
"""
import argparse
import json
import re
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from core import exportdocx, giaoban, ingest, library, llm, notify, style, transform
from core.paths import ROOT

WORK = ROOT / "work"
UPLOADS = WORK / "uploads"
STATE_F = WORK / "state.json"
DEFAULT_PROFILE = json.loads((ROOT / "data" / "profile.json").read_text(encoding="utf-8"))
LIB = library.Library(WORK / "library.json")
GB = giaoban.GiaoBan(WORK / "giaoban.json")
LOCK = threading.Lock()
JOBS: dict = {}


def new_state():
    return {"raw": "", "files": [], "decisions": {}, "profile": dict(DEFAULT_PROFILE)}


def load_state():
    if STATE_F.exists():
        try:
            st = json.loads(STATE_F.read_text(encoding="utf-8"))
            st["profile"] = {**DEFAULT_PROFILE, **st.get("profile", {})}
            return st
        except Exception:
            pass
    return new_state()


STATE = new_state()


def save():
    WORK.mkdir(exist_ok=True)
    STATE_F.write_text(json.dumps(STATE, ensure_ascii=False, indent=1), encoding="utf-8")


def ensure_decisions():
    p = ingest.parse(STATE["raw"])
    for s in p["sections"]:
        if s["id"] not in STATE["decisions"]:
            STATE["decisions"][s["id"]] = {
                "action": "rewrite" if transform.count_flags(s) else "keep",
                "text": ingest.body_text(s), "title": s["title"], "ai": False}
    return p


def view():
    p = ensure_decisions()
    prof = STATE["profile"]
    ref = transform.ref_date(prof)
    prof_txt = json.dumps(prof, ensure_ascii=False)
    secs = []
    for s in p["sections"]:
        d = STATE["decisions"][s["id"]]
        src = s["title"] + "\n" + ingest.body_text(s)
        secs.append({
            "id": s["id"], "num": s["num"], "title": d.get("title") or s["title"], "level": s["level"],
            "orig": ingest.body_text(s), "flags": transform.flag_terms(src),
            "deadlines": [{"text": t, "date": dd.strftime("%d/%m/%Y"), "overdue": dd < ref}
                          for t, dd in transform.deadlines(src)],
            "action": d["action"], "text": d["text"], "ai": d.get("ai", False),
            "new_numbers": transform.new_numbers(src, d["text"], prof_txt + d.get("ref_text", "")),
            "refs": d.get("refs", []), "yeu_cau": d.get("yeu_cau", ""),
            "van_phong": style.check(d["text"], src) if d["action"] == "rewrite" else [],
        })
    return {"files": STATE["files"], "profile": prof, "ref_date": ref.strftime("%d/%m/%Y"),
            "intro": p["intro"], "tail": p["tail"], "sections": secs,
            "ai": llm.status(prof), "library": LIB.docs(), "default_prompt": llm.DEFAULT_SYSTEM}


def overdue_strings():
    ref = transform.ref_date(STATE["profile"])
    out = []
    for s in ingest.parse(STATE["raw"])["sections"]:
        out += [t for t, dd in transform.deadlines(s["title"] + "\n" + ingest.body_text(s)) if dd < ref]
    return out


def build_docx(path):
    p = ensure_decisions()
    items = transform.assemble(p, STATE["decisions"], STATE["profile"])
    return exportdocx.export(items, STATE["profile"], str(path), overdue_strings())


def rewrite_job(jid, ids):
    job = JOBS[jid]
    with LOCK:
        ensure_decisions()
    by_id = {s["id"]: s for s in ingest.parse(STATE["raw"])["sections"]}
    for sid in ids:
        job["current"] = sid
        try:
            t0 = time.time()
            sec = by_id[sid]
            with LOCK:
                extra = STATE["decisions"][sid].get("yeu_cau", "")
                refs = LIB.search(sec["title"] + "\n" + ingest.body_text(sec) + "\n" + extra)
            out = llm.rewrite(STATE["profile"], sec, refs, extra)
            with LOCK:
                d = STATE["decisions"][sid]
                if out.strip().upper().startswith("[BỎ]"):
                    d["action"] = "drop"
                else:
                    d.update(text=style.autofix(out), action="rewrite", ai=True,
                             refs=sorted({r["name"] for r in refs}),
                             ref_text="\n".join(r["text"] for r in refs))
                save()
            job["log"].append(f"{sid}: xong sau {time.time() - t0:.0f} giây")
        except Exception as e:  # noqa: BLE001
            job["log"].append(f"{sid}: LỖI {e}")
        job["done"] += 1
    job["finished"] = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body: bytes, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self):
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    # ---------- giao ban
    def _gb_view(self):
        return {**GB.public(), "goi_y_ngay": GB.suggest_date(), "du_kien": GB.preview_rotation(10)}

    def _gb_get(self, op, q):
        with LOCK:
            if op == "state":
                return self._json(self._gb_view())
            if op == "docx":
                bb = GB.draft(q["ngay"][0])
                name = f"Bien_ban_giao_ban_{giaoban.parse_date(bb['ngay']):%d.%m.%Y}.docx"
                out = WORK / "giaoban" / name
                out.parent.mkdir(parents=True, exist_ok=True)
                GB.export_docx(bb, out)
                data = out.read_bytes()
            elif op == "zip":
                import io
                import zipfile
                buf = io.BytesIO()
                name = f"Bien_ban_giao_ban_{q['tu'][0]}_{q['den'][0]}.zip"
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                    for d in giaoban.ngay_hop(q["tu"][0], q["den"][0]):
                        if d.isoformat() in GB.data["lich_su"]:
                            f = WORK / "giaoban" / f"Bien_ban_giao_ban_{d:%d.%m.%Y}.docx"
                            f.parent.mkdir(parents=True, exist_ok=True)
                            GB.export_docx(GB.data["lich_su"][d.isoformat()], f)
                            z.write(f, f.name)
                data = buf.getvalue()
            else:
                return self._json({"error": "không tìm thấy"}, 404)
        ctype = ("application/zip" if op == "zip" else
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        return self._send(200, data, ctype, {"Content-Disposition": f'attachment; filename="{name}"'})

    def _gb_post(self, op, data):
        res = {"ok": True}
        if op == "config":
            GB.set_config(data)
        elif op == "members":
            GB.set_members(data["thanh_vien"])
        elif op == "reset_rotation":
            GB.reset_rotation()
        elif op == "draft":
            return {"draft": GB.draft(data["ngay"], data.get("vang"))}
        elif op == "commit":
            res["ban"] = GB.commit(data)
        elif op == "undo":
            res["xoa"] = GB.undo_latest()
        elif op == "batch":
            res["ngay"] = GB.batch(data["tu"], data["den"])
        elif op == "notify_cfg":
            GB.set_notify(data)
        elif op == "notify_test":
            GB.set_notify(data)
            res["ket_qua"] = send_notice(GB.suggest_date() if not data.get("ngay") else data["ngay"], test=True)
        elif op == "tg_chats":
            GB.set_notify(data)
            tok = GB.data["thong_bao"]["telegram"]["token"]
            if not tok:
                raise ValueError("Nhập token bot trước.")
            res["bot"] = notify.tg_me(tok).get("username")
            res["chats"] = notify.tg_chats(tok)
        else:
            raise ValueError("không tìm thấy")
        GB.save()
        res["state"] = self._gb_view()
        return res

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/":
            return self._send(200, (ROOT / "ui.html").read_bytes(), "text/html; charset=utf-8")
        if u.path == "/giaoban":
            return self._send(200, (ROOT / "giaoban.html").read_bytes(), "text/html; charset=utf-8")
        if u.path.startswith("/api/gb/"):
            try:
                return self._gb_get(u.path[8:], q)
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e)}, 400)
        if u.path == "/api/state":
            with LOCK:
                return self._json(view())
        if u.path == "/api/job":
            return self._json(JOBS.get(q.get("id", [""])[0], {}))
        if u.path == "/api/export":
            with LOCK:
                out = build_docx(WORK / "ke_hoach_xa.docx")
            return self._send(200, Path(out).read_bytes(),
                              "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                              {"Content-Disposition": 'attachment; filename="ke_hoach_xa.docx"'})
        self._json({"error": "không tìm thấy"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/api/lib/upload":
                name = re.sub(r"[^\w.\-]", "_", Path(unquote(q.get("name", ["file"])[0])).name)
                LIBDIR = WORK / "library"
                LIBDIR.mkdir(parents=True, exist_ok=True)
                f = LIBDIR / f"{int(time.time() * 1000)}_{name}"
                f.write_bytes(self._body())
                text = ingest.read_any(str(f))
                with LOCK:
                    doc = LIB.add(unquote(q.get("name", [name])[0]), text)
                return self._json({"ok": True, "doc": doc})
            if u.path == "/api/upload":
                name = re.sub(r"[^\w.\-]", "_", Path(unquote(q.get("name", ["file"])[0])).name)
                UPLOADS.mkdir(parents=True, exist_ok=True)
                f = UPLOADS / f"{int(time.time() * 1000)}_{name}"
                f.write_bytes(self._body())
                text = ingest.read_any(str(f))
                with LOCK:
                    STATE["raw"] += "\n\n" + text
                    STATE["files"].append(name)
                    STATE["decisions"] = {}
                    save()
                return self._json({"ok": True, "chars": len(text)})
            data = json.loads(self._body() or b"{}")
            if u.path.startswith("/api/gb/"):
                with LOCK:
                    return self._json(self._gb_post(u.path[8:], data))
            with LOCK:
                if u.path == "/api/paste":
                    STATE["raw"] += "\n\n" + data.get("text", "")
                    STATE["files"].append("(văn bản dán)")
                    STATE["decisions"] = {}
                elif u.path == "/api/reset":
                    keep = STATE["profile"]
                    STATE.clear()
                    STATE.update(new_state(), profile=keep)
                elif u.path == "/api/lib/paste":
                    LIB.add(data.get("name") or "Văn bản dán", data.get("text", ""))
                elif u.path == "/api/lib/delete":
                    LIB.delete(data["id"])
                elif u.path == "/api/profile":
                    STATE["profile"].update(data)
                elif u.path == "/api/decide":
                    ensure_decisions()
                    d = STATE["decisions"][data["id"]]
                    for k in ("action", "text", "title", "yeu_cau"):
                        if k in data:
                            d[k] = data[k]
                elif u.path == "/api/rewrite":
                    jid = uuid.uuid4().hex[:8]
                    JOBS[jid] = {"total": len(data["ids"]), "done": 0, "current": None,
                                 "log": [], "finished": False}
                    threading.Thread(target=rewrite_job, args=(jid, data["ids"]), daemon=True).start()
                    return self._json({"job": jid})
                else:
                    return self._json({"error": "không tìm thấy"}, 404)
                save()
            return self._json({"ok": True})
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 400)


def send_notice(ngay, test=False):
    """Lập (và chốt nếu chưa chốt) biên bản ngày `ngay`, gửi báo trước qua các kênh đang bật.
    Gọi khi đang giữ LOCK."""
    tb = GB.data["thong_bao"]
    bb = GB.draft(ngay)
    if not bb.get("da_chot") and not test:
        bb = GB.commit(bb)
    subject, text = GB.notice(bb)
    att = None
    if tb.get("dinh_kem"):
        att = WORK / "giaoban" / f"Bien_ban_giao_ban_{giaoban.parse_date(bb['ngay']):%d.%m.%Y}.docx"
        att.parent.mkdir(parents=True, exist_ok=True)
        GB.export_docx(bb, att)
    if test:
        subject = "[GỬI THỬ] " + subject
    out = notify.send_all(tb, subject, text, att)
    GB.log(time.strftime("%d/%m %H:%M ") + ("(thử) " if test else "") + "; ".join(out))
    GB.save()
    return out


def notice_loop():
    """Mỗi phút kiểm tra: ngày T2–T6, đã tới giờ gửi, hôm nay chưa gửi, chưa quá 12h trưa -> gửi."""
    import datetime as dt
    while True:
        time.sleep(60)
        try:
            with LOCK:
                tb = GB.data["thong_bao"]
                now = dt.datetime.now()
                today = now.date().isoformat()
                if not tb.get("bat") or now.weekday() >= 5 or tb.get("da_gui") == today or now.hour >= 12:
                    continue
                hh, mm = (int(x) for x in (tb.get("gio_gui") or "07:00").split(":")[:2])
                if (now.hour, now.minute) < (hh, mm):
                    continue
                last = GB.latest_date()
                if last and last > today:      # đã chốt trước cả ngày sau: không gửi lại
                    tb["da_gui"] = today
                    GB.save()
                    continue
                tb["da_gui"] = today            # đánh dấu trước để lỗi mạng không gửi lặp mỗi phút
                send_notice(today)
        except Exception as e:  # noqa: BLE001
            with LOCK:
                GB.log(time.strftime("%d/%m %H:%M ") + f"LỖI: {e}")
                GB.save()


def main():
    global STATE
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", nargs="*", help="các file kế hoạch cấp trên (theo thứ tự trang)")
    ap.add_argument("--out", default="ke_hoach_xa.docx")
    ap.add_argument("--ai", action="store_true", help="dùng AI viết lại các mục được gợi ý")
    ap.add_argument("--model", help="tên mô hình Ollama (hoặc 'fake' để thử)")
    ap.add_argument("--dump", help="ghi văn bản đã đọc/OCR ra file .txt")
    ap.add_argument("--lib", nargs="*", default=[], help="tài liệu tham khảo đưa vào kho trước khi chạy")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()

    if a.cli is not None:
        STATE = new_state()
        if a.model:
            STATE["profile"]["model"] = a.model
        for f in a.lib:
            print("Thêm vào kho:", f, file=sys.stderr)
            LIB.add(Path(f).name, ingest.read_any(f))
        for f in a.cli:
            print("Đọc:", f, file=sys.stderr)
            STATE["raw"] += "\n\n" + ingest.read_any(f)
        if a.dump:
            Path(a.dump).write_text(STATE["raw"], encoding="utf-8")
        p = ensure_decisions()
        for s in p["sections"]:
            d = STATE["decisions"][s["id"]]
            print(f"  [{d['action']:7}] {s['num']} {s['title'][:70]}", file=sys.stderr)
        if a.ai:
            ids = [s["id"] for s in p["sections"] if STATE["decisions"][s["id"]]["action"] == "rewrite"]
            JOBS["cli"] = {"total": len(ids), "done": 0, "current": None, "log": [], "finished": False}
            rewrite_job("cli", ids)
            print("\n".join(JOBS["cli"]["log"]), file=sys.stderr)
        print("Mốc thời hạn đã qua:", overdue_strings(), file=sys.stderr)
        print("Đã xuất:", build_docx(a.out))
        return

    url = f"http://127.0.0.1:{a.port}"
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)   # chỉ nghe trên máy này
    except OSError:
        print("Phần mềm đang mở sẵn, chỉ mở lại trình duyệt.")
        webbrowser.open(url)
        return
    STATE = load_state()
    import atexit
    if llm.start_bundled(WORK / "llama.log"):
        print("Đang bật AI cục bộ (llama.cpp) - lần đầu nạp mô hình mất 1-2 phút.")
    atexit.register(llm.stop_bundled)
    import signal
    for sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGBREAK", None)):
        if sig:
            signal.signal(sig, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
    threading.Thread(target=notice_loop, daemon=True).start()
    print("Đang chạy tại", url, "- đóng cửa sổ này để tắt.")
    threading.Timer(1, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        llm.stop_bundled()


if __name__ == "__main__":
    main()
