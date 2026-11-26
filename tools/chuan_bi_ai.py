"""Chuẩn bị gói cài offline (chạy MỘT LẦN trên máy có Internet).

Sau khi chạy xong, thư mục phần mềm có thêm:
  wheels/     thư viện Python (khoảng 12 MB), để máy khách cài không cần mạng
  ai/llama/   llama.cpp bản Windows chạy bằng CPU (llama-server.exe ...)
  ai/models/  mô hình .gguf
Chép nguyên thư mục phần mềm sang máy khách (đã cài cùng phiên bản Python) là dùng được, không cần mạng.
"""
import json
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AI = ROOT / "ai"
MODELS = {
    # tên gọn: (repo HuggingFace, file) — mặc định qwen2.5-3b, hợp máy 8GB RAM
    "qwen2.5-3b": ("Qwen/Qwen2.5-3B-Instruct-GGUF", "qwen2.5-3b-instruct-q4_k_m.gguf"),
    "qwen2.5-1.5b": ("Qwen/Qwen2.5-1.5B-Instruct-GGUF", "qwen2.5-1.5b-instruct-q4_k_m.gguf"),
}
UA = {"User-Agent": "kehoach-xa-setup"}


# ---------------------------------------------------------------- tải file
def _contexts():
    """Python 3.13 bật kiểm tra chứng chỉ chặt (VERIFY_X509_STRICT), làm hỏng kết nối qua
    một số phần mềm diệt virus / tường lửa quét HTTPS. Lần thử thứ hai bỏ riêng cờ này,
    vẫn kiểm tra chứng chỉ và tên máy chủ như bình thường."""
    yield None
    c = ssl.create_default_context()
    c.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    yield c


def _open(url, timeout=60):
    last = None
    for c in _contexts():
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout, context=c)
        except urllib.error.HTTPError:
            raise
        except (ssl.SSLError, urllib.error.URLError, OSError) as e:
            last = e
    raise last


def _curl(url, dest=None):
    exe = shutil.which("curl.exe") or shutil.which("curl")
    if not exe:
        raise RuntimeError("Máy không có curl.exe")
    if dest:
        subprocess.run([exe, "-L", "-#", "--fail", "--retry", "3", "-A", UA["User-Agent"], "-o", str(dest), url], check=True)
        return None
    return subprocess.run([exe, "-L", "-sS", "--fail", "--retry", "3", "-A", UA["User-Agent"], url],
                          check=True, capture_output=True).stdout


def fetch_json(url):
    try:
        with _open(url) as r:
            return json.load(r)
    except Exception as e:  # noqa: BLE001
        print(f"  Python không kết nối được ({type(e).__name__}). Thử lại bằng curl...")
        return json.loads(_curl(url))


def download(url, dest: Path):
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with _open(url) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done / 1e6:7.0f} / {total / 1e6:.0f} MB ({done * 100 // total}%)", end="", flush=True)
        print()
    except Exception as e:  # noqa: BLE001
        print(f"\n  Python không tải được ({type(e).__name__}). Thử lại bằng curl...")
        tmp.unlink(missing_ok=True)
        _curl(url, tmp)
    tmp.replace(dest)


# ---------------------------------------------------------------- thư viện Python
def get_wheels():
    whl = ROOT / "wheels"
    print("Tải thư viện Python về thư mục wheels (để máy khách cài không cần mạng)...")
    subprocess.run([sys.executable, "-m", "pip", "download", "-q", "-r", str(ROOT / "requirements.txt"),
                    "-d", str(whl), "--only-binary=:all:"], check=True)
    print(f"  Xong: {len(list(whl.glob('*.whl')))} gói. Máy khách phải cài Python {sys.version_info.major}.{sys.version_info.minor}.")


# ---------------------------------------------------------------- llama.cpp
SKIP = ("cuda", "cudart", "vulkan", "hip", "sycl", "opencl", "arm64", "aarch64", "kompute", "rpc", "musa", "openvino")


def pick_asset(names):
    """Chọn file zip bản Windows x64 chạy bằng CPU, chịu được việc llama.cpp đổi cách đặt tên."""
    win = [n for n in names if n.lower().endswith(".zip") and "win" in n.lower()
           and not any(k in n.lower() for k in SKIP)]
    for key in ("cpu-x64", "cpu", "avx2", "x64"):
        hit = [n for n in win if key in n.lower()]
        if hit:
            return sorted(hit, key=len)[0]
    return None


def get_llama():
    if list((AI / "llama").rglob("llama-server.exe")):
        print("llama.cpp đã có, bỏ qua.")
        return
    print("Tìm bản llama.cpp cho Windows (CPU)...")
    releases = fetch_json("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=20")
    name = url = tag = None
    for rel in releases:
        assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
        n = pick_asset(assets)
        if n:
            name, url, tag = n, assets[n], rel.get("tag_name", "")
            break
    if not name:
        names = [a["name"] for a in (releases[0].get("assets", []) if releases else [])]
        raise RuntimeError("Không tìm thấy bản Windows CPU. Các file trong bản phát hành mới nhất: " + ", ".join(names))
    z = AI / name
    AI.mkdir(exist_ok=True)
    print(f"Tải {name} (bản phát hành {tag})")
    download(url, z)
    shutil.rmtree(AI / "llama", ignore_errors=True)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(AI / "llama")
    z.unlink()
    if not list((AI / "llama").rglob("llama-server.exe")):
        raise RuntimeError("File tải về không có llama-server.exe")
    print("Đã giải nén llama.cpp", tag, "(giấy phép MIT)")


# ---------------------------------------------------------------- mô hình
def get_model(key):
    repo, fname = MODELS[key]
    (AI / "models").mkdir(parents=True, exist_ok=True)
    for old in (AI / "models").glob("*.gguf"):
        if old.name != fname:
            print("Xoá mô hình cũ", old.name)
            old.unlink()
    dest = AI / "models" / fname
    if dest.exists() and dest.stat().st_size > 100e6:
        print("Mô hình đã có, bỏ qua.")
        return
    print("Tải mô hình", fname, "(khoảng 1–2 GB, có thể mất 10–30 phút)")
    download(f"https://huggingface.co/{repo}/resolve/main/{fname}", dest)


# ---------------------------------------------------------------- chạy
def manual_help(failed, key):
    repo, fname = MODELS[key]
    print("\nCách làm tay cho phần chưa tải được (dùng trình duyệt, hoặc đổi sang mạng khác như wifi điện thoại):")
    if "llama.cpp" in failed:
        print("  - llama.cpp: mở https://github.com/ggml-org/llama.cpp/releases, tải file .zip Windows CPU x64")
        print("    (tên có 'win' và 'cpu' hoặc 'avx2'; KHÔNG chọn cuda, vulkan, hip, arm64).")
        print("    Giải nén vào thư mục ai\\llama sao cho có file llama-server.exe.")
    if "Mô hình AI" in failed:
        print(f"  - Mô hình: tải https://huggingface.co/{repo}/resolve/main/{fname}")
        print("    Lưu vào thư mục ai\\models (giữ nguyên tên file).")
    if "Thư viện Python" in failed:
        print("  - Thư viện Python: kết nối tới pypi.org bị chặn. Thử mạng khác rồi chạy lại file này.")
    print("Sau đó chạy lại chuan_bi_ai.bat. Phần nào đã có sẽ được bỏ qua.")


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5-3b"
    if key not in MODELS:
        sys.exit("Mô hình hợp lệ: " + ", ".join(MODELS))
    failed = []
    embedded = (ROOT / "python" / "python.exe").exists()   # bản KeHoachXa.exe đã có sẵn thư viện
    steps = [("llama.cpp", get_llama), ("Mô hình AI", lambda: get_model(key))]
    if not embedded:
        steps.insert(0, ("Thư viện Python", get_wheels))
    for label, fn in steps:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            print(f"\nLỖI ở bước {label}: {type(e).__name__}: {e}\n")
            failed.append(label)
    if failed:
        print("CHƯA XONG. Bước bị lỗi:", ", ".join(failed))
        manual_help(failed, key)
        sys.exit(1)
    if embedded:
        print("\nXONG. Chép nguyên thư mục phần mềm (có thư mục ai) sang máy khách rồi nhấn đúp KeHoachXa.exe.")
    else:
        print("\nXONG. Chép nguyên thư mục phần mềm (có wheels và ai) sang máy khách. "
              f"Máy khách cài Python {sys.version_info.major}.{sys.version_info.minor} rồi nhấn đúp chay.bat.")
