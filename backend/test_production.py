import sys
import os
from pathlib import Path

# Resolve path dynamically to the directory of this file
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

# Force mock environment variables before importing app configurations
os.environ["DATABASE_URL"] = "sqlite:///./test_temp_db.db"
os.environ["LINE_CHANNEL_SECRET"] = "mock_line_channel_secret"
os.environ["LINE_CHANNEL_ACCESS_TOKEN"] = "mock_line_channel_token"
os.environ["LLM_PROVIDER"] = "gemini"

print("Testing Production Refactored Backend System in NongKanvelaAssistant...")

try:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import get_db, Base, engine
    from app import models
    print("[OK] Test dependencies loaded successfully.")
except Exception as e:
    print(f"[FAIL] Failed to load test dependencies: {e}")
    sys.exit(1)

# Force recreate tables for test database
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

client = TestClient(app)

# 1. Test User Registration
print("\n--- 1. Testing User Registration ---")
user_payload = {
    "name": "Somchai Affiliate",
    "role": "affiliate_manager",
    "line_user_id": "U123456789somchai",
    "shopee_affiliate_id": "SOMCHAI_AFF_01"
}
response = client.post("/api/users/", json=user_payload)
assert response.status_code == 201, f"Failed: {response.text}"
user_data = response.json()
user_id = user_data["id"]
print(f"[OK] User created with ID: {user_id}, Name: {user_data['name']}")

# 2. Test Product Creation
print("\n--- 2. Testing Product Creation ---")
product_payload = {
    "name": "Smart Vacuum Cleaner Xiaomi",
    "category": "Home Appliances",
    "price": 4999.00,
    "rating": 4.90,
    "sales_count": 850,
    "commission": 250.00,
    "affiliate_url": "https://shope.ee/xiaomi_vacuum"
}
response = client.post("/api/products/", json=product_payload)
assert response.status_code == 201, f"Failed: {response.text}"
product_data = response.json()
product_id = product_data["id"]
print(f"[OK] Product created with ID: {product_id}, Score: {product_data['score']}/100, AI Score: {product_data['ai_score']}/100")

# 3. Test Deep AI Analysis on the Product
print("\n--- 3. Testing Deep AI Analysis & Script Generation ---")
response = client.post(f"/api/products/{product_id}/analyze")
assert response.status_code == 200, f"Failed: {response.text}"
analysis_data = response.json()
print(f"[OK] Analysis returned. Recommendation: {analysis_data['recommendation']}")
print(f"Hook Script: {analysis_data['script']['hook']}")

# 4. Test Performance Logging
print("\n--- 4. Testing Performance Logging ---")
db = next(get_db())
content = db.query(models.Content).filter(models.Content.product_id == product_id).first()
assert content is not None, "Content script was not generated in database"
content_id = content.id

perf_payload = {
    "content_id": content_id,
    "views": 10000,
    "clicks": 500,
    "orders": 25,
    "commission_earned": 6250.00 # Tests backward compatibility
}
response = client.post(f"/api/performance/contents/{content_id}", json=perf_payload)
assert response.status_code == 201, f"Failed: {response.text}"
print(f"[OK] Logged performance statistics. Commission Earned: {response.json()['commission']}")

# 5. Test Performance Summary Analytics (CTR, Conv Rate, EPC)
print("\n--- 5. Testing Performance Summary (Dashboard Stats) ---")
response = client.get("/api/performance/summary")
assert response.status_code == 200, f"Failed: {response.text}"
summary = response.json()
print(f"[OK] Analytics Summary fetched successfully:")
print(f"  Total Views: {summary['total_views']}")
print(f"  Total Clicks: {summary['total_clicks']}")
print(f"  Total Orders: {summary['total_orders']}")
print(f"  Total Commission: {summary['total_commission']} THB")
print(f"  Average CTR (Click-Through Rate): {summary['average_ctr']}% (Expected 5.0%)")
print(f"  Conversion Rate: {summary['conversion_rate']}% (Expected 5.0%)")
print(f"  Earnings Per Click (EPC): {summary['earnings_per_click']} THB (Expected 12.50)")

assert summary["average_ctr"] == 5.0
assert summary["conversion_rate"] == 5.0
assert summary["earnings_per_click"] == 12.50

# 6. Test LINE Bot Webhook Integration
print("\n--- 6. Testing LINE Bot Webhook (วันนี้ขายอะไรดี?) ---")
line_webhook_payload = {
    "destination": "xxxxxxxxxx",
    "events": [
        {
            "type": "message",
            "replyToken": "test_reply_token_123",
            "message": {
                "type": "text",
                "id": "event_msg_01",
                "text": "วันนี้ขายอะไรดี?"
            },
            "timestamp": 1625682000000,
            "source": {
                "type": "user",
                "userId": "U123456789somchai"
            }
        }
    ]
}
response = client.post("/api/webhooks/line", json=line_webhook_payload)
assert response.status_code == 200, f"Failed: {response.text}"
print("[OK] LINE Bot responded with status code 200.")

# Clean up temp test database file
db.close()
if os.path.exists("./test_temp_db.db"):
    try:
        os.remove("./test_temp_db.db")
        print("\n[OK] Cleaned up temporary test database.")
    except Exception as e:
        print(f"\n[Warning] Could not delete temp test database file: {e}")

print("\n[SUCCESS] ALL PRODUCTION SUITE TESTS PASSED SUCCESSFULLY!")
