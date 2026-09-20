import requests
import json
from pathlib import Path
import openpyxl

BASE_URL = "http://127.0.0.1:8000/api/v1"

# 1. Get NovaTech CID
cos = requests.get(f"{BASE_URL}/companies").json()
cid = [c["id"] for c in cos if "NovaTech" in c["name"]][0]
print("Company ID:", cid)

# 2. Test Valuation POST
val = requests.post(f"{BASE_URL}/companies/{cid}/valuation", json={"persist": False}).json()
print("Valuation status: ok")
print("Valuation keys:", list(val.keys()))
dcf = val.get("dcf", {})
bridge = dcf.get("bridge", {})
wacc = val.get("wacc", {})
print(f"Fair Value per share: {bridge.get('per_share_inr')}")
print(f"Bridge keys: {list(bridge.keys())}")
print(f"Enterprise Value: {bridge.get('enterprise_value_cr') or bridge.get('enterprise_value') or bridge.get('ev')}")
print(f"WACC: {wacc}")

# 3. Test Risk GET
risk = requests.get(f"{BASE_URL}/companies/{cid}/risk").json()
print("Risk status: ok")
print("Risk composite score:", risk.get("composite_score"))
print("Risk flags count:", len(risk.get("flags", [])))

# 4. Test Export XLSX and verify formulas
xlsx_res = requests.post(f"{BASE_URL}/exports/xlsx?company_id={cid}", json={})
xlsx_meta = xlsx_res.json()
print("XLSX export meta:", xlsx_meta)
download_url = xlsx_meta["download_url"]

file_res = requests.get(f"http://127.0.0.1:8000{download_url}")
out_path = Path("/app/data/novatech_test_export.xlsx")
out_path.write_bytes(file_res.content)
print(f"Downloaded XLSX size: {len(file_res.content)} bytes to {out_path}")

# Inspect openpyxl
wb = openpyxl.load_workbook(out_path, data_only=False)
print("Sheet names:", wb.sheetnames)
for sheet_name in wb.sheetnames:
    ws = wb[sheet_name]
    formulas = []
    for row in ws.iter_rows(values_only=False):
        for cell in row:
            if str(cell.value).startswith("="):
                formulas.append((cell.coordinate, cell.value))
    print(f"Sheet '{sheet_name}' has {len(formulas)} formula cells")
    if formulas:
        print("Sample formulas:", formulas[:3])

# 5. Test Export Memo PDF
pdf_res = requests.post(f"{BASE_URL}/exports/memo_pdf?company_id={cid}", json={})
pdf_meta = pdf_res.json()
print("PDF export meta:", pdf_meta)
pdf_file_res = requests.get(f"http://127.0.0.1:8000{pdf_meta['download_url']}")
pdf_out_path = Path("/app/data/novatech_test_memo.pdf")
pdf_out_path.write_bytes(pdf_file_res.content)
print(f"Downloaded PDF size: {len(pdf_file_res.content)} bytes to {pdf_out_path}")
