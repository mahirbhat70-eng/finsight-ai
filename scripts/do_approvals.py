import requests
import time

BASE_URL = "http://127.0.0.1:8000/api/v1"

# 1. Fetch queue items
q_res = requests.get(f"{BASE_URL}/review/queue")
items = q_res.json()
print(f"Review queue count: {len(items)}")

# 2. Approve each item
for item in items:
    item_id = item["item_id"]
    res = requests.post(f"{BASE_URL}/review/items/{item_id}", json={"approve": True})
    print(f"Approved {item_id}: {res.status_code}")

print("Waiting for embedding stage to finish...")
time.sleep(5)

# Check queue again
q2 = requests.get(f"{BASE_URL}/review/queue").json()
print(f"Remaining in review queue: {len(q2)}")
