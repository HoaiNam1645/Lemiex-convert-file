
import requests
import json

def test_batch():
    url = "https://manage.lemiex.us/api/orders/process-order"
    # Danh sách ID lấy từ log của bạn
    ids_list = ["100", "112", "113", "114", "117", "118", "214"]
    ids_str = ",".join(ids_list)
    
    params = {"ids": ids_str}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"Calling API with {len(ids_list)} IDs: {ids_str}")
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and "data" in data:
                items = data["data"]
                print(f"Received {len(items)} items in response.")
                
                received_ids = []
                for item in items:
                    oid = str(item.get("id"))
                    received_ids.append(oid)
                    print(f" - Found ID: {oid}")
                
                # Check missing
                missing = set(ids_list) - set(received_ids)
                if missing:
                    print(f"WARNING: The following IDs were requested but NOT returned: {missing}")
                else:
                    print("SUCCESS: All requested IDs were returned.")
            else:
                print("Response data format unexpected.")
        else:
            print(f"Error response: {response.text}")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_batch()
