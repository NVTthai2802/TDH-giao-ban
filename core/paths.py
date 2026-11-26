"""Thư mục gốc của phần mềm. Khi chạy bản .exe (PyInstaller), lấy thư mục chứa file .exe,
vì ui.html, data/, tesseract/, ai/, work/ được đặt cạnh file .exe."""
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent
