# PES Embroidery API

API service để xử lý file thêu PES - convert sang JSON, DST và generate preview.

## Tech Stack

- Python 3.9+
- FastAPI + Uvicorn
- pyembroidery (đọc/ghi file thêu)
- Pillow (render preview)
- Backblaze B2 (storage)

## Cài đặt

```bash
# Clone project
git clone <repo-url>
cd pes-api

# Tạo virtual environment
python3 -m venv venv
source venv/bin/activate

# Cài dependencies
pip install -r api/requirements.txt
```

## Chạy server

```bash
python3 api/main.py
```

Server chạy tại: http://localhost:8009

API Docs: http://localhost:8009/docs

## API Endpoints

### Health Check
```
GET /api/health
```

### Convert PES → JSON (upload B2)
```
POST /api/convert-pes-to-json
```
```json
{
  "url": "https://.../file.pes",
  "include_preview": true,
  "preview_size": 400
}
```

### Batch Convert PES → DST (upload B2)
```
POST /api/convert-pes-to-dst
```
```json
{
  "urls": [
    {"side": "front", "item_id": 61, "url": "https://.../front.pes"},
    {"side": "back", "item_id": 61, "url": "https://.../back.pes"}
  ],
  "order_id": 63,
  "include_dst": true
}
```

### Convert PES → JSON (trả về trực tiếp)
```
POST /api/convert
```
Form data: `file` hoặc `url`

### Generate Preview
```
POST /api/preview
```
Form data: `file` hoặc `url`

### Convert Format (PES ↔ DST ↔ JEF...)
```
POST /api/convert-format
```
Form data: `file` hoặc `url`, `output_format`

## Cấu trúc project

```
api/
├── main.py              # FastAPI app
├── config.py            # Configuration
├── requirements.txt     # Dependencies
├── routes/              # API endpoints
│   ├── convert.py
│   ├── convert_b2.py
│   ├── batch_convert.py
│   ├── preview.py
│   └── format.py
└── services/            # Business logic
    ├── file_handler.py
    ├── pes_converter.py
    └── b2_storage.py
```

## Environment Variables

```bash
B2_ACCESS_KEY_ID=xxx
B2_SECRET_ACCESS_KEY=xxx
B2_DEFAULT_REGION=us-east-005
B2_BUCKET=Lemiex-Fulfillment
B2_ENDPOINT=https://s3.us-east-005.backblazeb2.com
```

## Deployment

Xem chi tiết tại [DEPLOYMENT.md](DEPLOYMENT.md)
