#!/bin/sh
# Tạo gói KeHoachXa (Python nhúng cho Windows + KeHoachXa.exe) từ máy Linux. Cần: curl, pip, x86_64-w64-mingw32-gcc.
set -e
S=$(cd "$(dirname "$0")/.." && pwd); OUT=${1:-/tmp/exepkg}; P=$OUT/KeHoachXa; PYV=3.13.0
rm -rf "$OUT"; mkdir -p "$P/python/Lib/site-packages" "$OUT/whl"
curl -sL -o "$OUT/emb.zip" "https://www.python.org/ftp/python/$PYV/python-$PYV-embed-amd64.zip"
(cd "$P/python" && unzip -q "$OUT/emb.zip")
printf 'python313.zip\r\n.\r\nLib\\site-packages\r\n..\r\nimport site\r\n' > "$P/python/python313._pth"
pip download -q -r "$S/requirements.txt" --platform win_amd64 --python-version 3.13 --implementation cp --only-binary=:all: -d "$OUT/whl"
for w in "$OUT"/whl/*.whl; do python3 -c "import zipfile,sys;zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$w" "$P/python/Lib/site-packages"; done
x86_64-w64-mingw32-gcc -O2 -s -municode -static -o "$P/KeHoachXa.exe" "$S/tools/launcher/kehoachxa.c"
cp -r "$S/app.py" "$S/ui.html" "$S/giaoban.html" "$S/core" "$S/data" "$S/tesseract" "$S/chuan_bi_ai.bat" "$P/"
mkdir -p "$P/tools" && cp "$S/tools/chuan_bi_ai.py" "$P/tools/"
find "$P" -name __pycache__ -prune -exec rm -rf {} +
(cd "$OUT" && zip -qr9 KeHoachXa.zip KeHoachXa)
echo "Xong: $OUT/KeHoachXa.zip"
