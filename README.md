# Vé Số Xuyên Không (Time-Traveling Lottery) 🎰

**Vé Số Xuyên Không** là một ứng dụng tra cứu kết quả xổ số kiến thiết của Việt Nam (XSKT) trong quá khứ. Ứng dụng mô phỏng ý tưởng: *"Nếu bạn có thể mang một tờ vé số về quá khứ, liệu bạn có trúng giải hay không?"*.
### ✨ Tính Năng Nổi Bật
- **Data Scraper Cực Nhanh**: Tự động thu thập kết quả XSKT từ Miền Bắc, Miền Trung và Miền Nam theo thời gian (hỗ trợ cào dữ liệu theo năm hoặc theo khoảng ngày tùy chọn).
- **Backend Mạnh Mẽ**: Sử dụng FastAPI và SQLite để xử lý hàng ngàn request tra cứu mượt mà.
- **Frontend Đẹp Mắt**: Giao diện Glassmorphism đương đại, tương tác mượt mà với hiệu ứng làm mờ nền (backdrop-filter) và hình nền HD Casino chất lượng cao.
- **Dò Số Thông Minh**:
  - Hỗ trợ dò 6 chữ số theo đúng số lượng chữ số yêu cầu của từng giải (Đặc Biệt đến Giải Tám).
  - Hỗ trợ dò các giải đặc thù như **Giải Phụ Đặc Biệt** và **Giải Khuyến Khích**.
  - Liên kết trực tiếp (hyperlink) tới trang web nguồn (xskt.com.vn) của ngày mở thưởng đó để xác minh.

### ⚙️ Hướng dẫn cài đặt

1. **Yêu cầu hệ thống**: Python 3.10+
2. **Cài đặt thư viện**:
   ```bash
   pip install -r requirements.txt
   ```

### 🚀 Cách sử dụng

**1. Khởi tạo cơ sở dữ liệu (Cào dữ liệu)**
Sử dụng script `scraper.py` để tạo database SQLite (`lottery_data.db`) và lấy dữ liệu về.
  ```bash
  # Ví dụ: Cào dữ liệu xổ số trong 2 năm qua
  python scraper.py --year 2

  # Ví dụ khác: Cào từ khoảng thời gian cụ thể
  python scraper.py --start-date 01-01-2024 --end-date 31-12-2024 --region mn
  ```

**2. Chạy ứng dụng Web (FastAPI)**
Khởi động server backend để phục vụ API và trang web.
  ```bash
  python app.py
  # Hoặc dùng uvicorn: uvicorn app:app --host 0.0.0.0 --port 8000 --reload
  ```

**3. Tra cứu**
- Mở trình duyệt và truy cập: `http://localhost:8000/`
- Nhập 6 số dự thưởng của bạn, chọn các miền muốn tra cứu và bấm **Dò vé**.