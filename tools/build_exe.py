"""Đóng gói phần mềm thành thư mục chạy bằng file .exe (PyInstaller, kiểu thư mục).

Chạy trên máy Windows có Python 3.13 (qua dong_goi_exe.bat). Kết quả: dist/KeHoachXa/
gồm KeHoachXa.exe, _internal/ (Python + thư viện), và các thư mục ui, data, tesseract, ai.
Chép nguyên thư mục dist/KeHoachXa sang máy khách là chạy được, không cần cài Python.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "KeHoachXa"
DIST = ROOT / "dist" / NAME


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("Chưa có PyInstaller. Chạy: python -m pip install pyinstaller")
    icon = ROOT / "data" / "icon.ico"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console",
           "--name", NAME, "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"),
           "--specpath", str(ROOT / "build"),
           "--collect-data", "docx",          # mẫu Word mặc định của python-docx
           "--hidden-import", "pytesseract", "--hidden-import", "pypdf",
           str(ROOT / "app.py")]
    if icon.exists():
        cmd[3:3] = ["--icon", str(icon)]
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    # Tài nguyên đặt cạnh file .exe (core/paths.py lấy thư mục chứa .exe làm gốc)
    for f in ("ui.html", "giaoban.html", "README.md"):
        shutil.copy2(ROOT / f, DIST / f)
    for d in ("data", "tesseract", "ai"):
        src = ROOT / d
        if src.exists():
            print("Chép", d, "...")
            shutil.copytree(src, DIST / d, dirs_exist_ok=True)
        elif d == "ai":
            print("Chưa có thư mục ai/ - bản exe sẽ chạy không có AI. Chạy chuan_bi_ai.bat trước nếu cần AI.")
    (DIST / "work").mkdir(exist_ok=True)
    print("\nXONG. Thư mục để chép sang máy khách:", DIST)
    print("Mở phần mềm: nhấn đúp", DIST / (NAME + ".exe"))


if __name__ == "__main__":
    main()
