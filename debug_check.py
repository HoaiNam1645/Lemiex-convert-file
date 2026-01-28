
import requests
import json
import logging

# Copy y hệt logic từ progress_scanner.py
class LemiexClient:
    def __init__(self):
        self.base_url = "https://manage.lemiex.us/api/orders/process-order"
        self.session = requests.Session()
        # Header y hệt server đang chạy
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    def debug_lookup(self, order_id):
        print(f"--- Debugging Order ID: {order_id} ---")
        try:
            print(f"1. Sending Request to {self.base_url}...")
            response = self.session.get(
                self.base_url,
                params={"ids": str(order_id)},
                timeout=15,
            )
            print(f"2. Response Status: {response.status_code}")
            
            if response.status_code != 200:
                print("LỖI: Server trả về lỗi, không phải 200 OK")
                print(response.text)
                return

            data = response.json()
            print("3. Raw Data Received:")
            print(json.dumps(data, indent=2))

            # Mô phỏng logic parse
            items = []
            if isinstance(data, dict):
                if isinstance(data.get("data"), list):
                    items = data["data"]
                    print(f"4. Parse: Tìm thấy danh sách 'data' với {len(items)} phần tử.")
                else:
                    print(f"4. Parse: Không tìm thấy key 'data' là list. Data keys: {list(data.keys())}")
            
            if not items:
                print("-> KẾT LUẬN: API trả về thành công nhưng KHÔNG CÓ DỮ LIỆU cho ID này.")
            else:
                print("-> KẾT LUẬN: Lấy dữ liệu THÀNH CÔNG.")
                # Validate item completion logic
                item = items[0]
                status_val = str(item.get("status", "")).lower()
                metas = item.get("order_item_metas", [])
                print(f"   Item Status: {status_val}")
                print(f"   Metas Count: {len(metas)}")
                if metas:
                    for m in metas:
                        print(f"     - Meta {m.get('meta_key')}: {m.get('status')}")

        except Exception as e:
            print(f"LỖI EXCEPTION: {e}")

if __name__ == "__main__":
    client = LemiexClient()
    # Test với ID 214 (Id bạn bảo có data)
    client.debug_lookup("214")
    
    print("\n" + "="*30 + "\n")
    
    # Test với ID 100 (Id trong ảnh bị lỗi)
    client.debug_lookup("100")
