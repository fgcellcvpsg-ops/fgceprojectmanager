# TÀI LIỆU HƯỚNG DẪN SỬ DỤNG VÀ MÔ TẢ HỆ THỐNG FGCE PROJECT MANAGER

## 1. Tổng Quan Hệ Thống

**FGCE Project Manager** là giải pháp phần mềm quản lý dự án chuyên biệt dành cho các công ty kỹ thuật và xây dựng. Hệ thống được thiết kế để thay thế quy trình quản lý thủ công (Excel, Zalo) bằng một nền tảng tập trung, giúp kiểm soát chặt chẽ tiến độ, hồ sơ và nguồn lực.

### Mục tiêu cốt lõi:
- **Tập trung hóa dữ liệu:** Quản lý thông tin dự án, khách hàng, và nhân sự trên một nền tảng duy nhất.
- **Kiểm soát chặt chẽ:** Ngăn chặn việc báo cáo sai lệch (ví dụ: không thể báo cáo hoàn thành 100% nếu còn việc chưa làm).
- **Tăng năng suất:** Hỗ trợ công cụ Kanban trực quan và báo cáo tự động.

---

## 2. Cấu Trúc Cây Thư Mục Dự Án

Cấu trúc mã nguồn được tổ chức theo mô hình Modular (Blueprints) để dễ dàng bảo trì và mở rộng:

```text
FGCEProjectManager/
├── .venv/                   # Môi trường ảo Python
├── app/                     # Mã nguồn chính của ứng dụng
│   ├── routes/              # Xử lý Logic nghiệp vụ (Controllers)
│   │   ├── admin.py         # Quản trị hệ thống, users
│   │   ├── auth.py          # Xác thực, đăng nhập/xuất
│   │   ├── backup.py        # Sao lưu dữ liệu
│   │   ├── clients.py       # Quản lý khách hàng
│   │   ├── export.py        # Xuất báo cáo (Excel/PDF)
│   │   ├── main.py          # Dashboard, trang chủ
│   │   ├── projects.py      # Quản lý dự án, Kanban, Calendar
│   │   └── tasks.py         # Quản lý công việc
│   ├── static/              # Tài nguyên tĩnh
│   │   ├── js/              # Mã nguồn JavaScript
│   │   │   ├── client_form.js
│   │   │   ├── project_form.js
│   │   │   └── toastmanager.js
│   │   ├── css/             # (Tùy chọn) style.css
│   │   ├── favicon.ico
│   │   └── logo.png
│   ├── templates/           # Giao diện người dùng (HTML/Jinja2)
│   │   ├── partials/        # Các thành phần giao diện nhỏ (HTMX)
│   │   │   ├── kanban_card.html
│   │   │   └── question_list.html
│   │   ├── 400.html         # Trang lỗi Bad Request
│   │   ├── 404.html         # Trang lỗi Not Found
│   │   ├── 500.html         # Trang lỗi Server Error
│   │   ├── admin_users.html # Quản lý người dùng
│   │   ├── backup.html      # Trang sao lưu/phục hồi
│   │   ├── base.html        # Layout chung
│   │   ├── calendar_view.html # Xem lịch
│   │   ├── change_password.html
│   │   ├── client_form.html
│   │   ├── clients.html
│   │   ├── dashboard.html
│   │   ├── edit_history.html
│   │   ├── edit_task.html
│   │   ├── export.html
│   │   ├── kanban.html      # Giao diện Kanban Board
│   │   ├── login.html
│   │   ├── project_detail.html
│   │   ├── project_form.html
│   │   ├── projects_export.html
│   │   └── reports.html
│   ├── __init__.py          # Khởi tạo ứng dụng (App Factory)
│   ├── export_tools.py      # Công cụ hỗ trợ xuất file
│   ├── extensions.py        # Khởi tạo extensions (DB, Login...)
│   ├── forms.py             # Định nghĩa WTForms
│   ├── models.py            # Database Models
│   └── utils.py             # Hàm tiện ích
├── instance/                # Dữ liệu cục bộ
│   └── data/
│       └── projects.db      # SQLite Database
├── migrations/              # Quản lý version Database (Alembic)
├── Dockerfile               # Cấu hình Docker Image
├── docker-compose.yml       # Cấu hình Docker Compose
├── requirements.txt         # Danh sách thư viện Python
├── wsgi.py                  # Entry point cho Production
└── README.md                # Tài liệu dự án
```

---

## 3. Hướng Dẫn Sử Dụng Chi Tiết

### A. Đăng Nhập & Dashboard
- **Đăng nhập:** Truy cập trang login, nhập Username/Password. Hệ thống hỗ trợ "Ghi nhớ đăng nhập".
- **Dashboard:** Ngay sau khi đăng nhập, bạn sẽ thấy:
    - Biểu đồ thống kê trạng thái dự án.
    - Danh sách các dự án đang tham gia.
    - Cảnh báo các dự án sắp đến hạn (Deadline).

### B. Quản Lý Dự Án (Projects Hub)
1.  **Tạo Dự Án Mới:**
    - Truy cập menu "Projects" -> "Add Project".
    - Nhập thông tin: Tên, Khách hàng, Số PO (bắt buộc với dự án FGC), Deadline, v.v.
    - Hệ thống sẽ tự động kiểm tra tính hợp lệ của dữ liệu.
2.  **Chi Tiết Dự Án:**
    - Xem thông tin tổng quan và tiến độ.
    - **Tab Tasks (Công việc):** Xem danh sách việc cần làm.
    - **Tab Q&A:** Đặt câu hỏi kỹ thuật và nhận câu trả lời từ Leader/Manager.
    - **Kanban View:** Nhấn nút "Kanban" để chuyển sang chế độ xem thẻ bài.

### C. Sử Dụng Kanban Board (Mới)
Đây là tính năng giúp quản lý công việc trực quan:
- **Giao diện:** Gồm 3 cột: **New** (Mới), **Doing** (Đang làm), **Done** (Hoàn thành).
- **Thao tác:**
    - Dùng chuột **kéo và thả** thẻ công việc từ cột này sang cột khác.
    - Hệ thống tự động lưu trạng thái mới ngay lập tức.
    - Màu sắc thẻ giúp phân biệt mức độ ưu tiên hoặc người thực hiện.

### D. Báo Cáo & Xuất Dữ Liệu
- Hệ thống hỗ trợ xuất báo cáo tiến độ ra file Excel/PDF để gửi cho khách hàng hoặc lưu trữ nội bộ.
- Truy cập menu "Reports" để tùy chỉnh và tải báo cáo.

---

## 4. Đặc Tả Kỹ Thuật & Bảo Mật

### Công Nghệ Sử Dụng
- **Backend:** Python Flask (Framework nhẹ, mạnh mẽ).
- **Database:** SQLite (Mặc định) / PostgreSQL (Tùy chọn cho quy mô lớn).
- **Frontend:** Bootstrap 5 (Responsive), HTMX (Tương tác mượt mà), SortableJS (Kéo thả).
- **Containerization:** Docker & Docker Compose.

### Cơ Chế Bảo Mật
1.  **Xác thực (Authentication):** Mật khẩu người dùng được mã hóa (Hash) an toàn.
2.  **Phân quyền (Authorization):**
    - **Admin:** Quản lý toàn bộ hệ thống.
    - **Manager:** Quản lý dự án và báo cáo.
    - **Leader:** Quản lý nhóm và phân công việc.
    - **Member:** Thực hiện công việc được giao.
3.  **Bảo vệ dữ liệu:**
    - Chống tấn công CSRF trên tất cả các form.
    - Chống SQL Injection thông qua ORM.
    - Logic nghiệp vụ chặt chẽ (Ví dụ: Không cho phép member xóa dự án).

---

## 5. Hướng Dẫn Cài Đặt & Triển Khai

### Yêu Cầu Hệ Thống
- Máy tính cài đặt Docker Desktop (Khuyên dùng) HOẶC Python 3.10+.

### Cách 1: Chạy bằng Docker (Đơn giản nhất)
1.  Tải mã nguồn về máy.
2.  Mở terminal tại thư mục gốc dự án.
3.  Chạy lệnh: `docker-compose up --build`
4.  Truy cập: `http://localhost:8000`

### Cách 2: Chạy Thủ Công (Python)
1.  Tạo môi trường ảo: `python -m venv .venv`
2.  Kích hoạt môi trường: `.venv\Scripts\activate` (Windows)
3.  Cài đặt thư viện: `pip install -r requirements.txt`
4.  Chạy ứng dụng: `flask run`

---

## 6. Khả Năng Mở Rộng & Web Online
Hệ thống này hoàn toàn có thể triển khai lên Internet (Cloud Server/VPS):
- **Web Server:** Sử dụng Nginx làm Reverse Proxy.
- **Application Server:** Sử dụng Gunicorn để xử lý request hiệu năng cao.
- **Database:** Dễ dàng chuyển đổi sang PostgreSQL/MySQL để phục vụ hàng ngàn người dùng đồng thời.
- **Domain:** Có thể trỏ tên miền riêng (ví dụ: `quanlyduan.congty.com`) và cài đặt SSL (HTTPS) miễn phí qua Let's Encrypt.
