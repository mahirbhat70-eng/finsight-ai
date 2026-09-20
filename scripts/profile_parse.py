import time
from app.ingestion.parser import parse_pdf
from app.ingestion.chunker import chunk_document

print("Starting parse_pdf...")
t0 = time.time()
doc = parse_pdf("data/fixtures/novatech_annual_report.pdf")
t1 = time.time()
print(f"parse_pdf completed in {t1 - t0:.2f}s, pages: {len(doc.pages)}, tables: {len(doc.tables)}")

print("Starting chunk_document...")
chunks = chunk_document(doc)
t2 = time.time()
print(f"chunk_document completed in {t2 - t1:.2f}s, chunks: {len(chunks)}")
