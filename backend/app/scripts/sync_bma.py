import argparse
import logging

from app.core import get_settings
from app.db.session import SessionLocal
from app.services.bma import sync_bma_observations


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Synchronize BMA road-water observations")
    if not get_settings().bma_enabled:
        parser.error("BMA_ENABLED must be true")
    with SessionLocal() as db:
        run = sync_bma_observations(db)
        print(f"{run.status} received={run.records_received} inserted={run.records_inserted} "
              f"updated={run.records_updated} unchanged={run.records_unchanged} rejected={run.records_rejected} "
              f"geometry_failures={run.geometry_failures} page_failures={run.page_failures}")
        return 1 if run.status == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
