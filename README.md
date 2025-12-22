# PES Design Information Viewer

Giao diện web hiển thị thông tin design PES (embroidery) với khả năng quản lý kim may thêu.

## Tính năng chính

### 1. Hiển thị thông tin file PES
- **Thumbnail**: Hiển thị preview của design (hiện tại là placeholder, cần tích hợp với pyembroidery)
- **File info**: Tên file, số mũi (stitches), chiều cao, chiều rộng, số màu
- **Format**: Giống như trong hình mẫu được cung cấp

### 2. Quản lý 12 kim may thêu (Needles 1-12)
- **Hiển thị**: 12 ô kim với số thứ tự từ 1-12
- **Màu mặc định**: 
  - Kim số 5: Màu đen (code 137)
  - Kim số 8: Màu trắng (code 135)
- **Drag & Drop**: Kéo màu từ bảng color table vào kim
- **Visual feedback**: Kim có màu sẽ hiển thị màu tương ứng và code

### 3. Bảng Color Stop Sequence
- **Cột hiển thị**: #, N#, Color, Code, Name, Chart
- **N# column**: Hiển thị số kim được gán (tự động cập nhật khi drag-drop)
- **Drag support**: Mỗi dòng màu có thể kéo thả vào kim
- **Color swatch**: Hiển thị mẫu màu thực tế

### 4. Tính năng nâng cao
- **Responsive design**: Tương thích mobile/tablet
- **Status messages**: Thông báo khi gán/xóa kim
- **Clear needle**: Click vào kim để xóa màu
- **Consistent UI**: Thiết kế giống với pesinfo.py output

## Cách sử dụng

### 1. Mở giao diện
```bash
# Mở file index.html trong trình duyệt web
# Hoặc sử dụng local server:
python -m http.server 8000
# Truy cập: http://localhost:8000
```

### 2. Load file PES (tương lai)
- Click nút "Load PES File" 
- Chọn file .pes (hiện tại chỉ hiển thị sample data)

### 3. Quản lý kim
- **Gán màu**: Kéo dòng màu từ bảng vào kim muốn gán
- **Xóa kim**: Click vào kim đã có màu để xóa
- **Xem assignment**: Cột N# trong bảng hiển thị kim được gán

## Cấu trúc file

```
UI-web-pes/
├── index.html          # Giao diện chính
├── styles.css          # Styling và responsive
├── app.js              # Logic JavaScript
├── pesinfo.py          # Script Python tham khảo
└── README.md           # Tài liệu này
```

## Tích hợp với pesinfo.py

### Đã tham khảo từ pesinfo.py:
- **Cấu trúc dữ liệu**: Format thông tin file và màu
- **Needle assignment logic**: Mặc định đen/trắng ở kim 5/8
- **Color processing**: Xử lý code màu và chart
- **Memory system**: Concept lưu trữ assignment (chưa implement)

### Cần implement thêm:
- **PES file parser**: Đọc file .pes thực tế
- **Thumbnail generator**: Tạo preview image từ PES
- **Memory persistence**: Lưu needle assignment
- **Export functionality**: Xuất thông tin đã gán kim

## Customization

### Thay đổi màu mặc định
```javascript
// Trong app.js, hàm setupDefaultNeedleAssignment()
const blackColor = this.colorData.find(color => color.code === 137);
const whiteColor = this.colorData.find(color => color.code === 135);
```

### Thay đổi số kim
```javascript
// Thay đổi số kim từ 12 thành số khác
// Cập nhật trong initializeNeedles() và needleAssignment array
```

### Thêm cột bảng
```html
<!-- Trong index.html, thêm cột mới vào color table -->
<th>New Column</th>
```

## Browser Support
- Chrome/Edge: ✅ Full support
- Firefox: ✅ Full support  
- Safari: ✅ Full support
- Mobile browsers: ✅ Responsive design

## Roadmap
1. **Tích hợp pyembroidery**: Đọc file PES thực tế
2. **Server backend**: API để xử lý file upload
3. **Needle memory**: Lưu trữ assignment giữa các session
4. **Export features**: Xuất DST, JPG với needle info
5. **Batch processing**: Xử lý multiple files
6. **Advanced UI**: Zoom, pan cho preview image