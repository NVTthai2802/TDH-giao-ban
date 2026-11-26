# TDH giao ban: lập kế hoạch và giao ban cho Công an xã

Ứng dụng chạy **hoàn toàn trên máy tính**, dùng để chuyển kế hoạch của cấp trên thành dự thảo kế hoạch của Công an xã.
Không gửi tài liệu ra Internet. Giao diện mở trong trình duyệt tại `http://127.0.0.1:8765` và chỉ máy này truy cập được.

## Cách làm việc

1. **Đọc kế hoạch cấp trên.** App nhận file Word, PDF có chữ, ảnh chụp từng trang hoặc văn bản dán vào. Ảnh được nhận dạng chữ (OCR) tiếng Việt và tự xoay khi chụp nghiêng.
2. **Nhập thông tin xã.** Gồm tên đơn vị, ký hiệu văn bản, đoạn căn cứ, nơi nhận, chức danh người ký và bảng thay thế cụm từ.
3. **Duyệt từng mục.** App tự tách kế hoạch thành các mục I, 1, 1.1… Với mỗi mục, bạn chọn *Giữ nguyên*, *Viết lại cho cấp xã* hoặc *Bỏ*. App tự đánh dấu:
   - thuật ngữ thuộc nhiệm vụ cấp trên (PC01, Phòng…, Viện kiểm sát, Giám đốc Công an…);
   - **mốc thời hạn đã qua** so với ngày ban hành;
   - **con số do AI tự thêm**, không có trong bản gốc.
4. **Xuất Word.** File được trình bày theo thể thức văn bản hành chính. Các cụm cần kiểm tra được tô vàng. Đây là **dự thảo**, cán bộ phải duyệt trước khi ban hành.

AI là tuỳ chọn. Khi không có AI, app vẫn tách mục, thay cụm từ, kiểm tra thời hạn và xuất Word.

## Kho tài liệu và cách AI viết

- **Kho tài liệu tham khảo:** thêm nghị quyết, quy định, hướng dẫn, tài liệu nội bộ (Word, PDF, ảnh, dán văn bản). Khi viết lại một mục, phần mềm tìm 2–3 đoạn liên quan nhất bằng từ khoá (BM25, không cần mô hình thêm) và đưa cho AI làm căn cứ. Mục được viết lại hiện tên tài liệu đã dùng. Kho lưu ở `work/library.json` và `work/library/`.
- **Cách AI viết:** ô lời dặn (system prompt) sửa được ngay trên giao diện, lưu trong `work/state.json`. Để trống hoặc bấm "Khôi phục mặc định" để dùng lời dặn gốc trong `core/llm.py`.
- **Yêu cầu riêng từng mục:** ô nhập ngay dưới tiêu đề mục, chỉ áp dụng khi AI viết mục đó.

## Giao ban hằng ngày

Mở bằng liên kết **Giao ban hằng ngày** trên thanh tiêu đề (địa chỉ `http://127.0.0.1:8765/giaoban`).

- **Lịch họp:** thứ 2 đến thứ 6, kể cả ngày lễ. Thứ 7, chủ nhật không tạo biên bản.
- **Đầu vào:** danh sách tổ (họ tên, chức vụ, có luân phiên hay không, lý do vắng dài ngày), kho ý kiến riêng của từng người (mỗi ý kiến cách nhau một dòng trống), thông tin cố định (đơn vị, địa điểm, giờ, chủ tọa, thư ký, số người phát biểu mỗi buổi, nội dung và kết luận mặc định của chủ tọa).
- **Mỗi buổi:** chọn ngày, tích người vắng, bấm "Chuẩn bị biên bản". Ô "Nội dung thêm" là tùy chọn (quán triệt công văn, việc đột xuất). Sửa chữ nếu cần rồi bấm "Chốt và tải Word".
- **Luân phiên:** mỗi buổi lấy 2 người đầu lượt đang có mặt (bỏ qua chủ tọa), chốt xong họ chuyển xuống cuối. Người vắng giữ chỗ nên phát biểu ở buổi sau. Ý kiến chọn câu người đó lâu chưa dùng nhất.
- **Đầu ra:** file Word `Bien_ban_giao_ban_dd.mm.yyyy.docx` theo mẫu biên bản của tổ; tạo nhiều ngày một lúc thì tải về file nén.
- Buổi đã chốt vẫn sửa được chữ nhưng không đổi người. Muốn làm lại lượt thì "Huỷ buổi đã chốt gần nhất".

## Cài đặt

**Trên máy chuẩn bị (một máy có Internet, làm một lần):**

1. Cài **Python 3.13** từ python.org. Khi cài, tích ô *Add python.exe to PATH*.
2. Nhấn đúp **`chuan_bi_ai.bat`**. Script tải về:
   - `wheels/`: các thư viện Python (khoảng 12 MB), để máy khách cài không cần mạng;
   - `ai/llama/`: llama.cpp bản Windows chạy bằng CPU (khoảng 30 MB, giấy phép MIT);
   - `ai/models/`: mô hình `qwen2.5-3b-instruct-q4_k_m.gguf` (khoảng 2 GB).

   Máy yếu hơn có thể dùng mô hình nhỏ hơn: `chuan_bi_ai.bat qwen2.5-1.5b`.
   Nếu một bước lỗi, script báo rõ bước nào và in cách tải tay bằng trình duyệt. Chạy lại thì phần đã có được bỏ qua.
3. Tesseract OCR đã nằm sẵn trong thư mục `tesseract/`, không cần cài.

**Trên máy khách (không cần Internet):**

1. Cài **Python 3.13** (cùng phiên bản với máy chuẩn bị), tích *Add python.exe to PATH*. File cài có thể chép bằng USB.
2. Chép nguyên thư mục phần mềm, gồm cả `wheels/` và `ai/`, vào ổ đĩa, ví dụ `D:\kehoach_xa`.
3. Nhấn đúp **`chay.bat`**. Lần đầu, phần mềm tự cài thư viện từ `wheels/` (vài chục giây) và bật AI. Những lần sau chạy ngay.

Phần mềm tự bật AI khi mở và tự tắt khi đóng. Nếu máy đã cài Ollama và không có thư mục `ai/`, phần mềm dùng Ollama.
Nếu máy khách cài khác phiên bản Python, `chay.bat` thử cài qua Internet. Nên cài đúng 3.13.

**Bản chạy ngay KeHoachXa.zip (khuyên dùng, máy khách không cần cài Python):** giải nén, nhấn đúp `KeHoachXa.exe`. Gói này có sẵn Python 3.13 bản nhúng (thư mục `python/`) và thư viện. `KeHoachXa.exe` chỉ là file khởi chạy, gọi `python\python.exe app.py`. Thiếu thư mục `ai/` thì chạy `chuan_bi_ai.bat` một lần (có Internet) hoặc chép `ai/` từ máy khác sang. Tạo lại gói từ Linux: `tools/build_embedded.sh`.

**Cách khác: đóng gói bằng PyInstaller trên Windows:**

1. Trên máy chuẩn bị, chạy `chuan_bi_ai.bat` như trên để có thư mục `ai/`.
2. Nhấn đúp **`dong_goi_exe.bat`**. Script cài PyInstaller vào `.venv-build/` và tạo thư mục `dist\KeHoachXa\` gồm `KeHoachXa.exe`, `_internal/`, `tesseract/`, `ai/`, `data/`.
3. Nén `dist\KeHoachXa` thành .zip, chép sang máy khách, giải nén, nhấn đúp `KeHoachXa.exe`. Cửa sổ đen là phần mềm đang chạy, đóng nó là tắt.

Bản .exe phải tạo trên Windows. File .exe không có chữ ký số nên Windows SmartScreen có thể cảnh báo lần đầu: bấm "Thông tin thêm" rồi "Vẫn chạy".

**Lỗi SSL khi chạy `chuan_bi_ai.bat`:** Python 3.13 kiểm tra chứng chỉ chặt hơn bản cũ, nên có thể lỗi khi mạng đi qua phần mềm diệt virus hoặc tường lửa quét HTTPS. Script tự thử lại với kiểm tra nới hơn (vẫn xác thực chứng chỉ), rồi thử bằng `curl.exe` của Windows.

## Giấy phép thành phần

Thư mục `tesseract/` chứa Tesseract OCR 5.4 (bản Windows của UB Mannheim), phát hành theo giấy phép Apache 2.0, xem `tesseract/LICENSE-tesseract.txt`.

## Dữ liệu nằm ở đâu

- `work/state.json`: tài liệu đã đọc và các chỉnh sửa.
- `work/uploads/`: file gốc đã tải lên.
- `work/ke_hoach_xa.docx`: bản Word xuất gần nhất.
- `work/giaoban.json`: danh sách tổ, kho ý kiến, lượt phát biểu và các biên bản đã chốt.
- `work/giaoban/`: các file Word biên bản đã tải.
- `work/llama.log`: nhật ký của AI, xem khi AI báo lỗi khởi động.

Muốn xoá sạch dữ liệu thì xoá thư mục `work/`.

## Chạy bằng dòng lệnh (để thử)

```
python app.py --cli trang1.jpg trang2.jpg ... --out ke_hoach_xa.docx
python app.py --cli samples/ke_hoach_cap_tren_ocr.txt --out thu.docx
python app.py --cli ... --ai                 # dùng AI viết lại các mục được gợi ý
python app.py --cli ... --ai --model fake    # thử luồng AI mà không cần Ollama
```

## Giới hạn hiện tại

- **OCR ảnh chụp có thể đọc sai chữ và số.** Trong ảnh mẫu, "15/8/2026" bị đọc thành "13/8/2026". Nên dùng file Word/PDF gốc, hoặc chụp/scan phẳng, đủ sáng, không nghiêng. Luôn so cột "Bản cấp trên" với giấy gốc.
- **AI cục bộ chậm và có thể viết sai.** Trên i3 với 8GB RAM, mỗi mục có thể mất vài phút. Thời gian thực tế cần đo trên máy. App đã chặn AI thêm số liệu mới, nhưng vẫn phải người duyệt.
- **Tìm kiếm trong kho theo từ khoá**, nên có thể bỏ sót đoạn diễn đạt khác từ. Với mô hình nhỏ, chỉ đưa được khoảng 1.800 ký tự tài liệu tham khảo cho mỗi mục.
- **Chưa đóng gói thành file cài đặt.** Bản cho khách hàng sẽ dùng PyInstaller và Inno Setup.

## Tải bản chạy ngay

Mỗi lần đẩy code lên nhánh `main`, GitHub Actions tạo gói `KeHoachXa` (Python nhúng + `KeHoachXa.exe` + Tesseract). Vào tab **Actions**, chọn lần chạy mới nhất, tải mục **KeHoachXa** ở phần Artifacts. Gói chưa có thư mục `ai/` (mô hình 2 GB): chạy `chuan_bi_ai.bat` một lần trên máy có mạng.

Thư mục `work/` chứa dữ liệu nghiệp vụ và đã bị loại khỏi git (`.gitignore`). Không đưa tài liệu thật lên kho này.
