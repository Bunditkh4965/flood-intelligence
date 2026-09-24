import argparse

from app.db.session import SessionLocal
from app.services.gistda import sync_gistda_flood


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize official GISTDA flood polygons")
    parser.add_argument("--period", required=True, choices=("1day", "3days", "7days", "30days", "all"))
    args = parser.parse_args()
    periods = ("1day", "3days", "7days", "30days") if args.period == "all" else (args.period,)
    failed = False
    with SessionLocal() as db:
        for period in periods:
            run = sync_gistda_flood(db, period)
            print(
                f"{run.period}: {run.status} received={run.records_received} "
                f"inserted={run.records_inserted} updated={run.records_updated} "
                f"unchanged={run.records_unchanged} rejected={run.records_rejected}"
            )
            failed = failed or run.status == "FAILED"
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
