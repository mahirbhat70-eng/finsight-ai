"""NovaTech fixture orchestrator (Playbook P1.3-P1.5).

Usage:
  python scripts/generate_novatech.py --validate   # articulation asserts only
  python scripts/generate_novatech.py --all        # json + xlsx + pdf + ground truth
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from novatech_model import build_model, summarize

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"


def export_json(model: dict, path: Path) -> None:
    payload = {
        "company": model["company"],
        "periods": model["periods"],
        "currency": model["currency"],
        "unit": model["unit"],
        "items": {k: [round(v, 2) for v in vals] for k, vals in model["items"].items()},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    args = set(sys.argv[1:])
    model = build_model()

    if "--validate" in args:
        print("articulation asserts: PASS")
        print(summarize(model))
        return 0

    FIXTURES.mkdir(parents=True, exist_ok=True)
    export_json(model, FIXTURES / "novatech_statements.json")
    print(f"wrote {FIXTURES / 'novatech_statements.json'}")

    if "--all" in args:
        from novatech_pdf import build_ground_truth, build_pdf
        from novatech_xlsx import build_xlsx

        build_xlsx(str(FIXTURES / "novatech.xlsx"), model)
        print(f"wrote {FIXTURES / 'novatech.xlsx'}")

        registry = build_pdf(str(FIXTURES / "novatech_annual_report.pdf"), model)
        print(f"wrote {FIXTURES / 'novatech_annual_report.pdf'} "
              f"({registry['num_pages']} pages)")

        gt = build_ground_truth(model, registry)
        gt_path = FIXTURES / "novatech_ground_truth.json"
        gt_path.write_text(json.dumps(gt, indent=2), encoding="utf-8")
        print(f"wrote {gt_path}: {len(gt['facts'])} facts, "
              f"{len(gt['qa_pairs'])} qa pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
