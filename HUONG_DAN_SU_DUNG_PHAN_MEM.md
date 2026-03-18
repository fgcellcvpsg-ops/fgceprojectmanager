# HƯỚNG DẪN SỬ DỤNG VÀ THAO TÁC TRÊN PHẦN MỀM FGCE PROJECT MANAGER

Tài liệu này hướng dẫn chi tiết các thao tác cơ bản và nâng cao trên phần mềm, dành cho người dùng mới bắt đầu.

---

## MỤC LỤC

1.  [Đăng Nhập Hệ Thống](#1-dang-nhap-he-thong)
2.  [Giao Diện Chính (Dashboard)](#2-giao-dien-chinh-dashboard)
3.  [Thao Tác Với Dự Án (Projects)](#3-thao-tac-voi-du-an-projects)
    *   [Tạo Dự Án Mới](#tao-du-an-moi)
    *   [Cập Nhật Tiến Độ & Trạng Thái](#cap-nhat-tien-do--trang-thai)
    *   [Gán Người Phụ Trách](#gan-nguoi-phu-trach)
4.  [Thao Tác Với Báo Giá (Quotations)](#4-thao-tac-voi-bao-gia-quotations)
5.  [Quản Lý Công Việc (Tasks)](#5-quan-ly-cong-viec-tasks)
    *   [Sử Dụng Kanban Board](#su-dung-kanban-board)
    *   [Báo Cáo Công Việc Hàng Ngày](#bao-cao-cong-viec-hang-ngay)
6.  [Báo Cáo & Xuất Dữ Liệu](#6-bao-cao--xuat-du-lieu)
7.  [Phân Quyền & Tài Khoản Mẫu](#7-phan-quyen--tai-khoan-mau)

---

<a name="1-dang-nhap-he-thong"></a>
## 1. ĐĂNG NHẬP HỆ THỐNG

*   **Bước 1:** Mở trình duyệt web (Chrome, Edge, Firefox).
*   **Bước 2:** Truy cập địa chỉ phần mềm (thường là `http://localhost:5001` hoặc địa chỉ IP máy chủ nội bộ).
*   **Bước 3:** Nhập **Tên đăng nhập** (Username) và **Mật khẩu** (Password).
*   **Bước 4:** Nhấn nút **Sign In** (Đăng Nhập).
    *   *Lưu ý:* Tích chọn "Remember Me" để không phải đăng nhập lại lần sau.

<a name="2-giao-dien-chinh-dashboard"></a>
## 2. GIAO DIỆN CHÍNH (DASHBOARD)

Sau khi đăng nhập, bạn sẽ thấy màn hình Dashboard tổng quan:

*   **Status Overview:** Biểu đồ tròn hiển thị tỷ lệ các dự án theo trạng thái (New, In Progress, Completed...).
*   **Recent Projects:** Danh sách 5 dự án gần nhất bạn tham gia hoặc cập nhật.
*   **Upcoming Deadlines:** Cảnh báo các dự án sắp đến hạn chót (màu đỏ là quá hạn, màu vàng là sắp đến hạn).
*   **My Tasks:** Danh sách công việc cá nhân cần làm ngay.

<a name="3-thao-tac-voi-du-an-projects"></a>
## 3. THAO TÁC VỚI DỰ ÁN (PROJECTS)

### <a name="tao-du-an-moi"></a>A. Tạo Dự Án Mới
*(Dành cho: Admin, Manager, Leader, Secretary)*

1.  Trên thanh menu bên trái, chọn **Projects** -> **Add Project**.
2.  Điền đầy đủ thông tin vào form:
    *   **Project Name:** Tên dự án (Bắt buộc).
    *   **PO Number:** Số đơn hàng (Bắt buộc nếu là dự án FGC - 8 chữ số).
    *   **Client:** Chọn khách hàng từ danh sách.
    *   **Deadline:** Ngày hết hạn dự án.
    *   **Assignee:** Người chịu trách nhiệm chính (Leader/Manager).
3.  Nhấn nút **Save Project** để tạo mới.

### <a name="cap-nhat-tien-do--trang-thai"></a>B. Cập Nhật Tiến Độ & Trạng Thái
*(Dành cho: Leader, Manager, Member)*

1.  Vào danh sách dự án (**Project List**), click vào tên dự án cần cập nhật.
2.  Tại màn hình chi tiết dự án (**Project Detail**), nhấn nút **Update Status** (hoặc biểu tượng cái bút chì).
3.  Trong cửa sổ hiện ra:
    *   **Status:** Chọn trạng thái mới (Ví dụ: Chuyển từ `New` sang `In Progress`).
    *   **Progress (%):** Kéo thanh trượt hoặc nhập số % hoàn thành.
    *   **Note:** Ghi chú chi tiết công việc đã làm (Rất quan trọng để lưu lịch sử).
4.  Nhấn **Save Changes**.

*Lưu ý quan trọng:*
*   **Leader/Member:** Không được giảm % tiến độ (chỉ được tăng).
*   **Secretary:** Chỉ được phép cập nhật trạng thái thành **Closed** (Đóng dự án).

### <a name="gan-nguoi-phu-trach"></a>C. Gán Người Phụ Trách
*(Dành cho: Admin, Manager)*

1.  Trong trang chi tiết dự án, tìm mục **Project Owners** (bên phải).
2.  Nhấn nút **Edit** (hình bút chì).
3.  Tích chọn các thành viên tham gia dự án.
4.  Nhấn **Update** để lưu lại.

<a name="4-thao-tac-voi-bao-gia-quotations"></a>
## 4. THAO TÁC VỚI BÁO GIÁ (QUOTATIONS)
*(Dành cho: Admin, Manager, Quotation, Secretary)*

Quy trình quản lý báo giá tách biệt với dự án thi công:

1.  **Tạo Báo Giá:**
    *   Vào menu **Quotations** -> **Add Quotation**.
    *   Nhập thông tin tương tự dự án nhưng chọn trạng thái là `Quotation - Doing` hoặc `Quotation - Not Started`.
2.  **Cập Nhật Trạng Thái Báo Giá:**
    *   `Doing`: Đang làm hồ sơ thầu.
    *   `Submitted`: Đã gửi hồ sơ cho khách hàng.
    *   `Won`: Trúng thầu -> Hệ thống sẽ gợi ý chuyển thành Dự án chính thức (New Project).
    *   `Lost`: Trượt thầu -> Đóng hồ sơ.

<a name="5-quan-ly-cong-viec-tasks"></a>
## 5. QUẢN LÝ CÔNG VIỆC (TASKS)

### <a name="su-dung-kanban-board"></a>A. Sử Dụng Kanban Board
Đây là cách trực quan nhất để quản lý tiến độ:

1.  Vào menu **Kanban Board**.
2.  Bạn sẽ thấy các thẻ công việc (Task) được chia làm 3 cột:
    *   **New:** Việc mới được giao.
    *   **Doing:** Việc đang làm.
    *   **Done:** Việc đã xong.
3.  **Thao tác:** Dùng chuột **kéo và thả** thẻ từ cột này sang cột kia. Hệ thống tự động lưu trạng thái.

### <a name="bao-cao-cong-viec-hang-ngay"></a>B. Báo Cáo Công Việc Hàng Ngày (Work History)
*(Bắt buộc với Member)*

1.  Vào menu **Reports** -> **Daily Report** (hoặc nút "Log Work" trên Dashboard).
2.  Chọn dự án, nhập số giờ làm việc, mô tả chi tiết công việc.
3.  Nhấn **Submit**. Dữ liệu này sẽ dùng để tính lương/thưởng cuối tháng.

<a name="6-bao-cao--xuat-du-lieu"></a>
## 6. BÁO CÁO & XUẤT DỮ LIỆU

1.  **Xuất Danh Sách Dự Án (Excel):**
    *   Vào **Project List**.
    *   Sử dụng bộ lọc (Filter) để chọn dự án cần xuất (ví dụ: theo Khách hàng, theo Trạng thái).
    *   Nhấn nút **Export Excel** ở góc trên bên phải.
2.  **Báo Cáo Tổng Hợp (Dashboard Report):**
    *   Vào menu **Reports** -> **Dashboard Export**.
    *   Chọn khoảng thời gian.
    *   Nhấn **Download PDF** để tải về báo cáo đẹp, có biểu đồ.

<a name="7-phan-quyen--tai-khoan-mau"></a>
## 7. PHÂN QUYỀN & TÀI KHOẢN MẪU (Dùng thử)

Để làm quen, bạn có thể sử dụng các tài khoản có sẵn dưới đây (Mật khẩu chung: **`password123`**).

| Vai Trò (Role) | Username | Quyền Hạn Chính |
| :--- | :--- | :--- |
| **Manager** | `manager_user` | Quản lý toàn bộ dự án, xem báo cáo, gán nhân sự. |
| **Leader** | `leader_user` | Quản lý kỹ thuật, tạo task, cập nhật tiến độ (không được giảm %). |
| **Quotation** | `quotation_user` | Chuyên trách mảng Báo giá (Full quyền trên Quotation, Read-only dự án thường). |
| **Secretary** | `secretary_user` | Hỗ trợ hành chính, được tạo dự án, chỉ được cập nhật trạng thái **Closed** (đóng dự án). |
| **Member** | `member_user` | Chỉ làm việc trên các task được giao, báo cáo tiến độ cá nhân. |

---
*Tài liệu hướng dẫn nội bộ - Vui lòng không chia sẻ ra bên ngoài.*
