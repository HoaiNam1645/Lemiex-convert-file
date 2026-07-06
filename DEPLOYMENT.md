# PES Embroidery API - Deployment Guide

## Tech Stack

- **Language:** Python 3.9+
- **Framework:** FastAPI
- **Server:** Uvicorn (ASGI)
- **Storage:** Backblaze B2 (S3-compatible)
- **Libraries:**
  - `pyembroidery` - đọc/ghi file thêu (PES, DST, JEF...)
  - `Pillow` - render preview image
  - `boto3` - upload lên B2/S3
  - `httpx` - async HTTP client

## Cấu trúc project

```
api/
├── main.py              # FastAPI app
├── config.py            # Configuration
├── requirements.txt     # Dependencies
├── routes/              # API endpoints
│   ├── convert.py       # POST /api/convert
│   ├── convert_b2.py    # POST /api/convert-pes-to-json
│   ├── batch_convert.py # POST /api/convert-pes-to-dst
│   ├── preview.py       # POST /api/preview
│   └── format.py        # POST /api/convert-format
└── services/            # Business logic
    ├── file_handler.py
    ├── pes_converter.py
    └── b2_storage.py
```

## API Endpoints

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/api/health` | GET | Health check |
| `/api/convert` | POST | Convert PES → JSON (trả về JSON) |
| `/api/convert-pes-to-json` | POST | Convert PES → JSON, upload B2 |
| `/api/convert-pes-to-dst` | POST | Batch convert PES → DST + preview, upload B2 |
| `/api/preview` | POST | Generate preview PNG |
| `/api/convert-format` | POST | Convert giữa các format (PES, DST, JEF...) |

## Deploy lên Ubuntu

### 1. Cài đặt dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Cài Python 3.9+
sudo apt install python3 python3-pip python3-venv -y

# Clone project
git clone <your-repo> /opt/pes-api
cd /opt/pes-api
```

### 2. Setup virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r api/requirements.txt
```

### 3. Cấu hình environment variables

```bash
# Tạo file .env
cat > /opt/pes-api/.env << EOF
B2_ACCESS_KEY_ID=your_b2_access_key_id
B2_SECRET_ACCESS_KEY=your_b2_secret_access_key
B2_DEFAULT_REGION=us-east-005
B2_BUCKET=Lemiex-Fulfillment
B2_ENDPOINT=https://s3.us-east-005.backblazeb2.com
EOF
```

### 4. Test chạy thử

```bash
cd /opt/pes-api
source venv/bin/activate
python3 api/main.py
```

### 5. Setup Systemd service

```bash
sudo cat > /etc/systemd/system/pes-api.service << EOF
[Unit]
Description=PES Embroidery API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/pes-api
Environment=PATH=/opt/pes-api/venv/bin
EnvironmentFile=/opt/pes-api/.env
ExecStart=/opt/pes-api/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8009 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable và start service
sudo systemctl daemon-reload
sudo systemctl enable pes-api
sudo systemctl start pes-api

# Check status
sudo systemctl status pes-api
```

### 6. Setup Nginx reverse proxy (optional)

```bash
sudo apt install nginx -y

sudo cat > /etc/nginx/sites-available/pes-api << EOF
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8009;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
        client_max_body_size 50M;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/pes-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 7. SSL với Certbot (optional)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

## Commands hữu ích

```bash
# Xem logs
sudo journalctl -u pes-api -f

# Restart service
sudo systemctl restart pes-api

# Stop service
sudo systemctl stop pes-api

# Check port
sudo lsof -i :8009
```

## Test API

```bash
# Health check
curl http://localhost:8009/api/health

# Convert PES to JSON
curl -X POST "http://localhost:8009/api/convert-pes-to-json" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://s3.us-east-005.backblazeb2.com/Lemiex-Fulfillment/pes_files/63_61_front.pes"}'
```

## Swagger Docs

Truy cập: `http://your-server:8009/docs`
