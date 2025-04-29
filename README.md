# 🎉 Event Management

Dự án quản lý sự kiện được xây dựng bằng **Django REST Framework (DRF)** và **React Native**. Hỗ trợ người dùng tìm kiếm, đặt vé, thanh toán và tham gia sự kiện một cách dễ dàng.

---

## 🚀 Tính năng chính

- **Xác thực & phân quyền**: Vai trò người tham gia, nhà tổ chức, quản trị viên; nhà tổ chức cần được duyệt.
- **Tạo & quản lý sự kiện**: Tên, mô tả, thời gian, địa điểm, giá vé, hình ảnh/video minh họa.
- **Tìm kiếm & duyệt sự kiện**: Theo từ khóa, danh mục, địa điểm, thời gian; sắp xếp theo độ phổ biến, ngày, giá.
- **Đặt vé & thanh toán**: Hỗ trợ nhiều loại vé; thanh toán qua Momo, ZaloPay, thẻ; gửi vé QR/email.
- **Quản lý vé & check-in**: Xem lịch sử, hủy vé, quét mã QR tại sự kiện.
- **Đánh giá & phản hồi**: Đánh giá sao, bình luận; nhà tổ chức phản hồi để cải thiện.
- **Thông báo & nhắc nhở**: Nhắc lịch, thông báo vé gần hết hạn qua email/push.
- **Thống kê & báo cáo**: Doanh thu, số vé, người tham gia; quản trị viên theo dõi toàn hệ thống.

---

## 📁 Cấu trúc thư mục (Backend)

```
event-management/
├── eventapis/               # Dự án Django
│   ├── settings.py          # Cấu hình chính
│   ├── urls.py             # Định tuyến
│   └── ...
├── events/                 # Ứng dụng chính
│   ├── models.py           # CSDL sự kiện, người dùng, vé
│   ├── views.py            # API logic
│   ├── serializers.py      # DRF serializers
│   ├── perms.py            # Phân quyền
│   ├── vnpay.py            # Tích hợp thanh toán
│   └── ...
├── requirements.txt        # Thư viện Python cần thiết
└── manage.py               # Lệnh quản lý Django
```

---

## ⚙️ Khởi động nhanh

```bash
git clone https://github.com/yourusername/event-management.git
cd event-management
python -m venv venv
source venv/bin/activate      # hoặc venv\Scripts\activate trên Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

---

## 📦 Công nghệ sử dụng

- **Backend**: Django REST Framework, MySQL
- **Thanh toán**: VNPAY
- **Frontend**: React Native
- **Thông báo**: Email, FCM Push Notification
- **Xác thực**: OAuth2
