# PHÂN TÍCH VAI TRÒ VÀ HƯỚNG DẪN SỬ DỤNG (User Guide & Role Analysis)

Tài liệu này cung cấp chi tiết về phân quyền, trách nhiệm và cách sử dụng hệ thống cho từng nhóm người dùng (trừ Admin).

---

## 1. DANH SÁCH TÀI KHOẢN MẶC ĐỊNH (Default Accounts)

Để thuận tiện cho việc trải nghiệm và kiểm thử, hệ thống đã tạo sẵn các tài khoản mẫu với mật khẩu mặc định là **`password123`**.

| Vai Trò (Role) | Username (Tên đăng nhập) | Mật khẩu (Password) | Ghi Chú |
| :--- | :--- | :--- | :--- |
| **Manager** | `manager_user` | `password123` | Quản lý dự án cao cấp |
| **Leader** | `leader_user` | `password123` | Trưởng nhóm kỹ thuật |
| **Quotation** | `quotation_user` | `password123` | Nhân viên báo giá |
| **Secretary** | `secretary_user` | `password123` | Thư ký dự án |
| **Member** | `member_user` | `password123` | Thành viên thực hiện |

---

## 2. PHÂN TÍCH CHI TIẾT VAI TRÒ (Role Analysis)

### A. Vai Trò MANAGER (Quản Lý Dự Án)
**Mục tiêu:** Giám sát tổng thể tiến độ, chất lượng và nguồn lực của toàn bộ các dự án trong công ty.

*   **Quyền hạn:**
    *   **Xem:** Toàn bộ dự án (Project List & Quotation List).
    *   **Tạo mới:** Được phép tạo cả Dự án thường và Báo giá.
    *   **Chỉnh sửa:** Full quyền chỉnh sửa thông tin dự án, xóa dự án (trừ khi dự án đã có dữ liệu ràng buộc quan trọng).
    *   **Gán nhân sự:** Có thể chỉ định Leader, Member, Secretary, Quotation cho dự án.
    *   **Báo cáo:** Xem và xuất tất cả các loại báo cáo (Tiến độ, Work History, Dashboard).
    *   **Duyệt:** Có quyền mở lại các dự án đã đóng (Status: Closed).

### B. Vai Trò LEADER (Trưởng Nhóm)
**Mục tiêu:** Quản lý kỹ thuật và điều phối công việc cho các dự án được giao hoặc quản lý chung.

*   **Quyền hạn:**
    *   **Xem:** Xem danh sách dự án (thường là tất cả hoặc theo phân công).
    *   **Tạo mới:** Được phép tạo dự án mới.
    *   **Chỉnh sửa:**
        *   Cập nhật thông tin dự án.
        *   Cập nhật tiến độ (%) và trạng thái (Status). **Lưu ý:** Không được phép giảm % tiến độ (chỉ tăng).
    *   **Quản lý Task:** Tạo, giao việc và theo dõi task của thành viên (Member).
    *   **Hạn chế:** Không thể xóa dự án hoặc can thiệp vào các cấu hình hệ thống.

### C. Vai Trò QUOTATION (Nhân Viên Báo Giá)
**Mục tiêu:** Tập trung vào giai đoạn chào giá, làm hồ sơ thầu và quản lý danh sách Báo giá.

*   **Quyền hạn đặc biệt:**
    *   **Phạm vi:** Chỉ tập trung vào các dự án có trạng thái là **Quotation** (Báo giá).
    *   **Xem:** Thấy danh sách các dự án Báo giá.
    *   **Tạo mới:** Chỉ được phép tạo dự án loại Quotation.
    *   **Chỉnh sửa:** Full quyền chỉnh sửa trên các dự án Báo giá (Sửa thông tin, Update Status, Gán người).
    *   **Gán nhân sự:** Khi gán người, chỉ nhìn thấy các user khác cùng thuộc nhóm Quotation (để bảo mật thông tin kinh doanh).
    *   **Hạn chế:** Chỉ xem (Read-only) đối với các Dự án thường (Normal Projects) đang chạy.

### D. Vai Trò SECRETARY (Thư Ký)
**Mục tiêu:** Hỗ trợ hành chính, cập nhật hồ sơ và đóng dự án khi hoàn thành thủ tục.

*   **Quyền hạn:**
    *   **Xem:** Xem tất cả dự án.
    *   **Tạo mới:** Được phép tạo dự án mới (nhập liệu ban đầu).
    *   **Chỉnh sửa (Dự án thường):**
        *   **Không** được sửa thông tin chi tiết dự án.
        *   **Không** được cập nhật tiến độ (%) hàng ngày.
        *   **Duy nhất:** Chỉ được quyền cập nhật trạng thái dự án thành **Closed** (Đóng dự án) khi đã xong thủ tục giấy tờ.
    *   **Chỉnh sửa (Báo giá):** Có quyền sửa và cập nhật trạng thái cho Báo giá (tương tự như nhân viên Quotation) để hỗ trợ làm thầu.

### E. Vai Trò MEMBER (Thành Viên)
**Mục tiêu:** Thực hiện các công việc cụ thể được giao và báo cáo tiến độ.

*   **Quyền hạn:**
    *   **Xem:** Chỉ thấy các dự án mình được phân công (Assignee) hoặc các dự án Public.
    *   **Tương tác:**
        *   Xem danh sách công việc (Tasks) của mình.
        *   Cập nhật trạng thái Task (New -> Doing -> Done).
        *   Gửi báo cáo công việc (Work History) hàng ngày.
    *   **Hạn chế:**
        *   Không được tạo mới dự án.
        *   Không được sửa thông tin dự án.
        *   Không được xóa bất cứ thứ gì.

---

## 3. QUY TRÌNH PHỐI HỢP (Workflow)

1.  **Khởi tạo:**
    *   **Quotation** hoặc **Secretary** tạo Báo giá mới -> Trạng thái: `Quotation - Doing`.
    *   Khi trúng thầu -> Chuyển trạng thái sang `Quotation - Submitted` hoặc `New` (Dự án mới).

2.  **Thực hiện:**
    *   **Manager** hoặc **Leader** tiếp nhận dự án `New`.
    *   Phân công **Member** vào dự án.
    *   **Member** thực hiện task, cập nhật tiến độ task.
    *   **Leader** cập nhật tiến độ tổng thể (%) của dự án.

3.  **Kết thúc:**
    *   Dự án đạt 100% -> Trạng thái `Completed`.
    *   **Secretary** kiểm tra hồ sơ, thanh quyết toán -> Chuyển trạng thái `Closed` (Kết thúc vòng đời).

---
*Tài liệu này được cập nhật ngày 24/02/2026.*
