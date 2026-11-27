# TV AutoSEO

Công cụ tự động hóa **SEO metadata, tạo thumbnail bằng GPT & lên lịch đăng YouTube Studio**, tách độc lập với dữ liệu, cổng mạng (`18101–18120`) và bộ cài Windows riêng (`TVAutoSEO_Setup.exe`).

## Chức năng chính
- **Kích hoạt & kiểm tra bản quyền (`/auth`)**: Xác thực Keygen gắn theo thiết bị.
- **Tài khoản & kênh (`/studio`)**: Đăng nhập Google/YouTube Studio để lấy session kênh, thêm kênh mới, load lại phiên kênh đã chọn và lọc/quét theo Gmail.
- **SEO, thumbnail & lên lịch (`/videos/publishing`)**: Quét video chưa công khai / bản nháp, tìm video tham chiếu YouTube, sinh ảnh thumbnail 16:9 qua ChatGPT worker (`gpt_backend`), nhập title/description/playlist/lịch đăng vào YouTube Studio và đọc xác nhận lại kết quả.
- **Cập nhật tự động**: Theo dõi bản phát hành mới nhất từ nhánh `main` của repo `duykhanh8386/TV-AutoSEO`.

## Chạy từ mã nguồn
```powershell
python -m pip install -r requirements.txt
npm ci --prefix gpt_backend
python app.py
```

## Đóng gói tự động (GitHub Actions)
Mỗi lần push lên nhánh `main` (hoặc chạy thủ công `workflow_dispatch`), workflow `.github/workflows/publish-installer.yml` sẽ tự build PyInstaller (`TV AutoSEO.spec`), đóng gói bộ cài Windows bằng Inno Setup (`TV AutoSEO.iss`) và phát hành `TVAutoSEO_Setup.exe` lên GitHub Releases.
