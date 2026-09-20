import requests
import json
import time

base = "http://127.0.0.1:8000/api/v1"
res = requests.get(f"{base}/companies")
print("Companies status:", res.status_code)
comps = res.json()
cid = [c["id"] for c in comps if "NovaTech" in c["name"]][0]
print(f"NovaTech CID: {cid}")

with open("data/fixtures/novatech_annual_report.pdf", "rb") as f:
    files = {"file": ("novatech_annual_report.pdf", f, "application/pdf")}
    upload_res = requests.post(f"{base}/companies/{cid}/filings", files=files)
    print("Upload status:", upload_res.status_code)
    job_data = upload_res.json()
    job_id = job_data["job_id"]
    print(f"Ingestion JOB ID: {job_id}")

for i in range(30):
    job_state = requests.get(f"{base}/jobs/{job_id}").json()
    print(f"[{i}] State: {job_state.get('state')} | Progress: {job_state.get('progress')}% | Detail: {job_state.get('stage_detail')}")
    if job_state.get("state") in ("done", "awaiting_review", "ready"):
        break
    time.sleep(2)
