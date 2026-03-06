# FGCE Project Manager

Hệ thống quản lý dự án (Project Manager) được xây dựng bằng Python Flask.

## Tính năng chính
- Quản lý Dự án (FGC / PEI)
- Quản lý Khách hàng (Clients)
- Theo dõi tiến độ và trạng thái (New, In Progress, Completed, Suspended)
- Xuất báo cáo PDF
- Phân quyền người dùng (Admin, Manager, Leader, Member)

## Cài đặt và Chạy (Local)

1. **Clone repository:**
   ```bash
   git clone https://github.com/username/repo-name.git
   cd repo-name
   ```

2. **Tạo môi trường ảo:**
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Mac/Linux:
   source venv/bin/activate
   ```

3. **Cài đặt thư viện:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Cấu hình môi trường:**
   - Tạo file `.env` từ file mẫu (nếu có) hoặc thêm:
     ```
     SECRET_KEY=your-secret-key
     DATABASE_URL=sqlite:///instance/data/projects.db
     ```

5. **Chạy ứng dụng:**
   ```bash
   python run.py
   ```
   Truy cập: `http://localhost:5000`

## Triển khai (Deployment)

Dự án đã sẵn sàng để triển khai trên các nền tảng như Render, Railway hoặc PythonAnywhere.
- **Database:** Khuyến nghị sử dụng PostgreSQL thay vì SQLite cho môi trường Production.
- **Server:** Sử dụng `gunicorn` (đã có trong requirements.txt).

## Cấu trúc dự án
- `app/`: Mã nguồn chính (Routes, Models, Templates)
- `instance/`: Chứa database SQLite (không commit lên Git)
- `migrations/`: Database migrations (Alembic)
