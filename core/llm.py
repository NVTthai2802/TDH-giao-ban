"""Gọi mô hình ngôn ngữ chạy cục bộ. Hai cách, tự chọn:
  1. llama.cpp đóng gói sẵn trong thư mục ai/ (llama-server, http://127.0.0.1:8081) — ưu tiên
  2. Ollama nếu máy đã cài (http://127.0.0.1:11434)
Không có kết nối nào ra Internet."""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import transform

from .paths import ROOT
AI_DIR = ROOT / "ai"
LLAMA_HOST = "http://127.0.0.1:8081"
_proc = None

DEFAULT_SYSTEM = (
    "Bạn là cán bộ văn phòng Công an cấp xã, soạn văn bản hành chính tiếng Việt, văn phong trang trọng, ngắn gọn.\n"
    "Nhiệm vụ: chuyển một mục trong kế hoạch của Công an thành phố thành nội dung kế hoạch của Công an xã.\n"
    "QUY TẮC BẮT BUỘC:\n"
    "1. Chỉ dùng thông tin có trong ĐOẠN GỐC và THÔNG TIN XÃ. Không thêm số liệu, ngày tháng, tên người, số hiệu văn bản mới.\n"
    "2. Giữ nguyên mọi con số, tỷ lệ, thời hạn, số hiệu văn bản và các cụm trong ngoặc như (Thực hiện thường xuyên), (Hoàn thành trước ngày ...).\n"
    "3. Nhiệm vụ giao cho 'các đơn vị, địa phương' hoặc 'Công an cấp xã' -> viết thành nhiệm vụ Công an xã tự thực hiện.\n"
    "4. Nhiệm vụ chỉ của cơ quan cấp trên (các Phòng PC, PX, PV, Cơ quan CSĐT thành phố) -> viết thành việc Công an xã phối hợp, "
    "báo cáo, chấp hành; KHÔNG giao việc cho các Phòng đó.\n"
    "5. Nếu cả mục hoàn toàn không liên quan tới Công an xã, chỉ trả lời đúng một dòng: [BỎ]\n"
    "6. Mỗi ý một dòng, bắt đầu bằng '- ' nếu bản gốc là gạch đầu dòng. Không viết lại tiêu đề, không giải thích thêm.\n"
    "7. Có thể dùng TÀI LIỆU THAM KHẢO (nếu có) để bổ sung nhiệm vụ, căn cứ phù hợp với cấp xã. Khi dẫn văn bản, "
    "ghi đúng số hiệu như trong tài liệu; không tự đặt số hiệu, không dẫn văn bản không có trong tài liệu.\n"
    "8. Viết như cán bộ viết tay: nói thẳng việc gì, ai làm, khi nào. KHÔNG dùng: 'đóng vai trò', 'nhấn mạnh', "
    "'là minh chứng', 'mạnh mẽ', 'không chỉ... mà còn', 'Ngoài ra/Hơn nữa' đầu câu, đuôi câu ', góp phần...', ', cho thấy...'. "
    "Không câu tóm tắt, không câu mở đầu hay kết thúc kiểu trợ lý. Không gạch ngang dài, không chữ đậm, không ký hiệu Markdown."
)


# ---------------------------------------------------------------- llama.cpp đóng gói kèm
def bundled_server():
    for name in ("llama-server.exe", "llama-server"):
        hits = sorted((AI_DIR / "llama").rglob(name)) if (AI_DIR / "llama").exists() else []
        if hits:
            return hits[0]
    return None


def bundled_model():
    hits = sorted((AI_DIR / "models").glob("*.gguf")) if (AI_DIR / "models").exists() else []
    return hits[0] if hits else None


def _kill_with_parent(proc):
    """Windows: gắn tiến trình AI vào Job Object để nó tự tắt khi phần mềm bị đóng (kể cả bấm X)."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IOC(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class EXT(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IOC), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.OpenProcess.restype = wintypes.HANDLE
    job = k32.CreateJobObjectW(None, None)
    info = EXT()
    info.Basic.LimitFlags = 0x2000                     # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info))
    h = k32.OpenProcess(0x0001 | 0x0100, False, proc.pid)   # PROCESS_TERMINATE | PROCESS_SET_QUOTA
    k32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(h))
    globals()["_job"] = job                            # giữ handle sống tới khi phần mềm thoát


def start_bundled(log_path: Path):
    """Bật llama-server nếu có sẵn trong thư mục ai/. Gọi một lần khi mở phần mềm."""
    global _proc
    exe, model = bundled_server(), bundled_model()
    if not exe or not model or _proc:
        return False
    try:                       # còn sót một bản đang chạy từ lần trước -> dùng luôn
        _get(LLAMA_HOST + "/health")
        return False
    except Exception:
        pass
    threads = max(1, (os.cpu_count() or 4) - 1)
    cmd = [str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", LLAMA_HOST.rsplit(":", 1)[1],
           "-c", "8192", "-t", str(threads)]
    flags = 0x08000000 if sys.platform == "win32" else 0      # CREATE_NO_WINDOW
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _proc = subprocess.Popen(cmd, cwd=str(exe.parent), stdout=open(log_path, "ab"),
                             stderr=subprocess.STDOUT, creationflags=flags)
    try:
        _kill_with_parent(_proc)
    except Exception:
        pass
    return True


def stop_bundled():
    if _proc and _proc.poll() is None:
        _proc.terminate()


def _get(url, timeout=1.5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def status(profile: dict) -> dict:
    """{'backend': 'llama'|'ollama'|None, 'ready': bool, 'label': str, 'models': [...]}"""
    if bundled_server() and bundled_model():
        name = bundled_model().name
        try:
            _get(LLAMA_HOST + "/health")
            return {"backend": "llama", "ready": True, "label": f"sẵn sàng ({name})", "models": [name]}
        except urllib.error.HTTPError as e:
            if e.code == 503:
                return {"backend": "llama", "ready": False, "label": "đang nạp mô hình, chờ 1–2 phút rồi bấm F5",
                        "models": []}
        except Exception:
            pass
        if _proc and _proc.poll() is not None:
            return {"backend": None, "ready": False,
                    "label": "lỗi khởi động, xem work/llama.log", "models": []}
        return {"backend": "llama", "ready": False, "label": "đang khởi động, bấm F5 sau ít giây", "models": []}
    host = profile.get("ollama_host", "http://127.0.0.1:11434")
    try:
        ms = [m["name"] for m in _get(host.rstrip("/") + "/api/tags").get("models", [])]
    except Exception:
        ms = []
    if ms:
        return {"backend": "ollama", "ready": True, "label": f"sẵn sàng (Ollama: {profile.get('model')})", "models": ms}
    return {"backend": None, "ready": False,
            "label": "chưa có — chạy chuan_bi_ai.bat để đóng gói AI", "models": []}


# ---------------------------------------------------------------- gọi mô hình
def _post(url, payload, timeout=1800):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def chat(profile: dict, system: str, user: str) -> str:
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    st = status(profile)
    if st["backend"] == "llama":
        if not st["ready"]:
            raise RuntimeError("AI " + st["label"])
        r = _post(LLAMA_HOST + "/v1/chat/completions",
                  {"messages": msgs, "temperature": 0.2, "max_tokens": 1500})
        return r["choices"][0]["message"]["content"].strip()
    if st["backend"] == "ollama":
        r = _post(profile.get("ollama_host", "http://127.0.0.1:11434").rstrip("/") + "/api/chat",
                  {"model": profile.get("model") or "qwen2.5:3b", "stream": False, "messages": msgs,
                   "options": {"temperature": 0.2, "num_ctx": 8192}, "think": False})
        return r["message"]["content"].strip()
    raise RuntimeError("Chưa có AI cục bộ. Chạy chuan_bi_ai.bat để đóng gói AI vào phần mềm.")


def system_prompt(profile: dict) -> str:
    return (profile.get("prompt_he_thong") or "").strip() or DEFAULT_SYSTEM


def build_user(profile: dict, sec: dict, refs=(), extra: str = "") -> str:
    parts = [f"THÔNG TIN XÃ: Công an xã {profile.get('ten_xa', '')}, trực thuộc {profile.get('cap_tren_ten', '')}."]
    if refs:
        parts.append("TÀI LIỆU THAM KHẢO (các đoạn liên quan trong kho tài liệu):\n" +
                     "\n\n".join(f"[{r['name']}]\n{r['text']}" for r in refs))
    parts.append(f"ĐOẠN GỐC (mục {sec['num']} {sec['title']}):\n" + "\n".join(sec["body"]))
    if extra.strip():
        parts.append("YÊU CẦU RIÊNG CHO MỤC NÀY: " + extra.strip())
    parts.append("Hãy viết lại nội dung mục này cho kế hoạch của Công an xã.")
    return "\n\n".join(parts)


def rewrite(profile: dict, sec: dict, refs=(), extra: str = "") -> str:
    if profile.get("model") == "fake":               # chế độ thử, không cần AI
        return transform.apply_subs("\n".join(sec["body"]), profile)
    return chat(profile, system_prompt(profile), build_user(profile, sec, refs, extra))
