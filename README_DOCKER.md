# Hướng dẫn chạy hệ thống bằng Docker

## Yêu cầu
- Docker Desktop đã được cài đặt.

## Cấu trúc
- `Dockerfile`: Cấu hình image cho ứng dụng.
- `docker-compose.yml`: Cấu hình service để chạy ứng dụng.

## Cách chạy
1. Mở terminal tại thư mục gốc của dự án.
2. Chạy lệnh:
   ```bash
   docker-compose up --build
   ```
3. Truy cập ứng dụng tại: `http://localhost:8000`

## Ghi chú
- Dữ liệu database được lưu trong thư mục `instance/data` (được mount ra ngoài container để đảm bảo dữ liệu không bị mất khi restart container).
- Để dừng hệ thống, nhấn `Ctrl+C` hoặc chạy `docker-compose down`.
