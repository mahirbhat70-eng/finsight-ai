"""Load test (Phase 7): 10 concurrent users on the copilot path with the
mock provider. Reports p50/p95.

Usage: python scripts/load_test.py [--users 10] [--seconds 30] [--base URL]
"""

import argparse
import asyncio
import statistics
import time

import httpx

QUESTION = "What was NovaTech's revenue in FY2025?"


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


async def worker(client: httpx.AsyncClient, company_id: str, latencies: list[float],
                 errors: list[str], deadline: float) -> None:
    while time.monotonic() < deadline:
        started = time.monotonic()
        try:
            response = await client.post(
                "/copilot/query_sync",
                json={"company_id": company_id, "question": QUESTION},
                timeout=60.0,
            )
            if response.status_code != 200:
                errors.append(f"{response.status_code}")
        except Exception as exc:  # noqa: BLE001
            errors.append(type(exc).__name__)
        latencies.append((time.monotonic() - started) * 1000)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--base", default="http://localhost:8000/api/v1")
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base) as client:
        companies = (await client.get("/companies")).json()
        target = next((c for c in companies if "NovaTech" in c["name"]), None)
        if target is None:
            print("NovaTech not found — run `make seed` first")
            return 2

        latencies: list[float] = []
        errors: list[str] = []
        deadline = time.monotonic() + args.seconds
        async with asyncio.TaskGroup() as group:
            for _ in range(args.users):
                group.create_task(
                    worker(client, target["id"], latencies, errors, deadline))

    print(f"requests: {len(latencies)}  errors: {len(errors)}")
    if latencies:
        print(f"p50: {percentile(latencies, 0.5):.0f}ms  "
              f"p95: {percentile(latencies, 0.95):.0f}ms  "
              f"max: {max(latencies):.0f}ms")
    if errors:
        print("error sample:", errors[:5])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
