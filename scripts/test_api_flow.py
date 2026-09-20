import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000/api/v1"

# 1. Check queue
r = requests.get(f"{BASE_URL}/review/queue")
print(f"Queue status: {r.status_code}")
items = r.json()
print(f"Items in queue: {len(items)}")

# 2. Approve each item
for item in items:
    item_id = item["item_id"]
    name = item.get("canonical_key", "unknown")
    res = requests.post(f"{BASE_URL}/review/items/{item_id}", json={"approve": True})
    print(f"Approved {item_id} ({name}): {res.status_code} -> {res.json()}")

# Wait a couple seconds for background/inline job transition if any
time.sleep(2)

# 3. Check queue again
r2 = requests.get(f"{BASE_URL}/review/queue")
print(f"Remaining in queue: {len(r2.json())}")

# 4. Check filings & chunks
cos = requests.get(f"{BASE_URL}/companies").json()
cid = [c["id"] for c in cos if "NovaTech" in c["name"]][0]
print(f"Company ID: {cid}")

# Check metrics
metrics = requests.get(f"{BASE_URL}/companies/{cid}/metrics").json()
print(f"Metrics available: {list(metrics.keys()) if isinstance(metrics, dict) else len(metrics)}")

# Check valuation
val = requests.post(f"{BASE_URL}/companies/{cid}/valuation", json={"persist": False}).json()
print(f"Valuation fair value: {val.get('fair_value_per_share')}, EV: {val.get('enterprise_value')}")

# Check risk
risk = requests.get(f"{BASE_URL}/companies/{cid}/risk").json()
print(f"Risk status: {risk.get('status') if isinstance(risk, dict) else 'ok'}")

# Check peers
peers = requests.get(f"{BASE_URL}/companies/{cid}/peers").json()
print(f"Peers count: {len(peers) if isinstance(peers, list) else peers}")

# Check copilot query_sync
copilot_res = requests.post(
    f"{BASE_URL}/copilot/query_sync",
    json={"company_id": cid, "question": "What drove NovaTech revenue growth in FY2024?"}
).json()
print(f"Copilot query result keys: {list(copilot_res.keys())}")
print(f"Copilot answer: {copilot_res.get('answer')}")
print(f"Copilot citations: {len(copilot_res.get('citations', []))}")
print(f"Copilot insufficient_evidence: {copilot_res.get('insufficient_evidence')}")

# Check exports
xlsx_res = requests.post(f"{BASE_URL}/exports/xlsx?company_id={cid}", json={})
print(f"XLSX export status: {xlsx_res.status_code}, content-type: {xlsx_res.headers.get('content-type')}, bytes: {len(xlsx_res.content)}")
with open("data/novatech_exported.xlsx", "wb") as f:
    f.write(xlsx_res.content)

pdf_res = requests.post(f"{BASE_URL}/exports/memo_pdf?company_id={cid}", json={})
print(f"PDF export status: {pdf_res.status_code}, content-type: {pdf_res.headers.get('content-type')}, bytes: {len(pdf_res.content)}")
with open("data/novatech_memo.pdf", "wb") as f:
    f.write(pdf_res.content)
