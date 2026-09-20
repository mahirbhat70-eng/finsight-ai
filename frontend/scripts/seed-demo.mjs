#!/usr/bin/env node
// Dev seed helper (P5.2): a fresh stack demos in one command.
// Boots nothing — assumes `docker compose up -d` and `make seed` ran.
// Hits the API to verify the demo state is queryable.

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

async function main() {
  const health = await fetch(`${BASE}/health`).then((r) => r.json());
  console.log("health:", health);

  const companies = await fetch(`${BASE}/companies`).then((r) => r.json());
  console.log("companies:", companies.map((c: { name: string }) => c.name));

  const nova = companies.find((c: { name: string }) => c.name.includes("NovaTech"));
  if (!nova) {
    console.error("NovaTech missing — run `make seed` first");
    process.exit(1);
  }
  const metrics = await fetch(`${BASE}/companies/${nova.id}/metrics`).then((r) => r.json());
  console.log("periods:", metrics.periods);
  console.log("latest revenue:", metrics.series.revenue.at(-1), "INR cr");

  const valuation = await fetch(`${BASE}/companies/${nova.id}/valuation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persist: false }),
  }).then((r) => r.json());
  console.log("fair value per share: Rs", valuation.dcf.bridge.per_share_inr);
  console.log("demo state OK");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
