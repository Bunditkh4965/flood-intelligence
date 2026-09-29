import argparse
import logging
from datetime import date

from app.core import get_settings
from app.db.session import SessionLocal
from app.services.hdms import sync_hdms_incidents


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Synchronize official DOH/HDMS road incidents")
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    if not get_settings().hdms_enabled:
        parser.error("HDMS_ENABLED must be true")
    if args.end < args.start:
        parser.error("--end must be on or after --start")
    with SessionLocal() as db:
        run = sync_hdms_incidents(db, args.start, args.end)
        print(
            f"{run.status} received={run.records_received} inserted={run.records_inserted} "
            f"updated={run.records_updated} unchanged={run.records_unchanged} "
            f"rejected={run.records_rejected} geometry_failures={run.geometry_failures}"
        )
        if run.status == "FAILED":
            print(f"reason: {run.error_message or 'failure reason was not recorded'}")
        return 1 if run.status == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
