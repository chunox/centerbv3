"""
Valida invariantes v2 del seed demo Scrum (t6/t7) contra la BD local.

Uso (tras reset_and_seed_demo.py):
  .venv\\Scripts\\python.exe scripts/validate_scrum_seed.py
  .venv\\Scripts\\python.exe scripts/validate_scrum_seed.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.services.scrum_seed_validation import validate_demo_scrum_seed


def main() -> int:
    parser = argparse.ArgumentParser(description="Validar seed Scrum demo (t6/t7)")
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = validate_demo_scrum_seed(db)
    finally:
        db.close()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        for result in report.results:
            status = "OK" if result.ok else "FAIL"
            print(f"\n[{status}] {result.nombre} ({result.template_slug})")
            if result.counts:
                parts = ", ".join(f"{k}={v}" for k, v in sorted(result.counts.items()))
                print(f"  counts: {parts}")
            for issue in result.issues:
                print(f"  - [{issue.check}] {issue.message}")
        print()
        print("VALIDACIÓN:", "OK" if report.ok else "FALLÓ")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
