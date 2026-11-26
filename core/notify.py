"""Gửi thông báo trước giờ giao ban qua email (SMTP) và/hoặc Telegram bot.

Đây là phần DUY NHẤT của phần mềm gửi dữ liệu ra khỏi máy, và chỉ chạy khi người dùng bật.
"""
import json
import mimetypes
import smtplib
import ssl
import urllib.parse
import urllib.request
import uuid
from email.message import EmailMessage
from pathlib import Path

TIMEOUT = 30


def _contexts():
    yield ssl.create_default_context()
    ctx = ssl.create_default_context()           # Python 3.13 kiểm tra chặt hơn; một số
    ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)   # phần mềm diệt virus làm hỏng
    yield ctx


# ---------------------------------------------------------------- email
def send_email(cfg: dict, subject: str, body: str, attachment: Path | None = None):
    to = [a.strip() for a in cfg.get("nguoi_nhan", "").replace(";", ",").split(",") if a.strip()]
    if not (cfg.get("tai_khoan") and cfg.get("mat_khau") and to):
        raise ValueError("Email: thiếu tài khoản, mật khẩu ứng dụng hoặc người nhận.")
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, cfg["tai_khoan"], ", ".join(to)
    msg.set_content(body)
    if attachment:
        ctype = mimetypes.guess_type(attachment.name)[0] or "application/octet-stream"
        main, sub = ctype.split("/", 1)
        msg.add_attachment(attachment.read_bytes(), maintype=main, subtype=sub, filename=attachment.name)
    host, port = cfg.get("smtp", "smtp.gmail.com"), int(cfg.get("cong", 465) or 465)
    err = None
    for ctx in _contexts():
        try:
            if port == 465:
                with smtplib.SMTP_SSL(host, port, context=ctx, timeout=TIMEOUT) as s:
                    s.login(cfg["tai_khoan"], cfg["mat_khau"])
                    s.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=TIMEOUT) as s:
                    s.starttls(context=ctx)
                    s.login(cfg["tai_khoan"], cfg["mat_khau"])
                    s.send_message(msg)
            return len(to)
        except ssl.SSLError as e:
            err = e
        except smtplib.SMTPAuthenticationError:
            raise ValueError("Email: sai tài khoản hoặc mật khẩu ứng dụng. Với Gmail phải dùng "
                             "'Mật khẩu ứng dụng' 16 ký tự, không dùng mật khẩu đăng nhập.") from None
    raise err


# ---------------------------------------------------------------- telegram
def _tg(token: str, method: str, data: bytes | None = None, ctype: str | None = None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    err = None
    for ctx in _contexts():
        try:
            req = urllib.request.Request(url, data=data, headers={"Content-Type": ctype} if ctype else {})
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
                res = json.loads(r.read().decode("utf-8"))
            if not res.get("ok"):
                raise ValueError("Telegram: " + res.get("description", "lỗi không rõ"))
            return res["result"]
        except ssl.SSLError as e:
            err = e
        except urllib.error.HTTPError as e:
            try:
                desc = json.loads(e.read().decode("utf-8")).get("description", "")
            except Exception:
                desc = str(e)
            if e.code == 401:
                desc = "token bot sai"
            elif "chat not found" in desc or e.code == 403:
                desc += " (người nhận phải mở bot và bấm Start trước)"
            raise ValueError("Telegram: " + desc) from None
    raise err


def tg_me(token):
    return _tg(token, "getMe")


def tg_chats(token):
    """Những người/nhóm đã nhắn cho bot gần đây: [{id, ten}]. Người nhận phải bấm Start trước."""
    seen = {}
    for u in _tg(token, "getUpdates"):
        for k in ("message", "my_chat_member", "edited_message", "channel_post"):
            chat = (u.get(k) or {}).get("chat")
            if chat:
                ten = chat.get("title") or " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x)
                if chat.get("username"):
                    ten += f" (@{chat['username']})"
                seen[chat["id"]] = {"id": chat["id"], "ten": ten.strip() or str(chat["id"]), "loai": chat.get("type")}
    return list(seen.values())


def tg_send(token: str, chat_id, text: str, attachment: Path | None = None):
    if not attachment:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        return _tg(token, "sendMessage", data, "application/x-www-form-urlencoded")
    b = uuid.uuid4().hex
    parts = []
    for k, v in (("chat_id", str(chat_id)), ("caption", text[:1000])):
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append((f'--{b}\r\nContent-Disposition: form-data; name="document"; filename="{attachment.name}"\r\n'
                  "Content-Type: application/octet-stream\r\n\r\n").encode() + attachment.read_bytes() + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    return _tg(token, "sendDocument", b"".join(parts), f"multipart/form-data; boundary={b}")


def send_all(cfg: dict, subject: str, text: str, attachment: Path | None):
    """Gửi theo mọi kênh đang bật. Trả về danh sách kết quả từng kênh (không dừng khi một kênh lỗi)."""
    out = []
    em = cfg.get("email", {})
    if em.get("bat"):
        try:
            n = send_email(em, subject, text, attachment)
            out.append(f"Email: đã gửi tới {n} địa chỉ")
        except Exception as e:  # noqa: BLE001
            out.append(f"Email LỖI: {e}")
    tg = cfg.get("telegram", {})
    if tg.get("bat"):
        ids = [i.strip() for i in str(tg.get("chat_ids", "")).replace(";", ",").split(",") if i.strip()]
        if not (tg.get("token") and ids):
            out.append("Telegram LỖI: thiếu token hoặc người nhận (chat_id)")
        for cid in ids:
            try:
                tg_send(tg["token"], cid, f"{subject}\n\n{text}", attachment)
                out.append(f"Telegram: đã gửi tới {cid}")
            except Exception as e:  # noqa: BLE001
                out.append(f"Telegram {cid} LỖI: {e}")
    if not out:
        out.append("Chưa bật kênh gửi nào (email hoặc Telegram).")
    return out
