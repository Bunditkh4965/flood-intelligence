"""Run the branch-master importer against an XLSX workbook."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.branch_importer import import_workbook, validate_workbook


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Branch Master XLSX data")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--database-url")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps(validate_workbook(args.workbook).report.to_dict(), ensure_ascii=False, indent=2))
        return
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core import get_settings

    engine = create_engine(args.database_url or get_settings().database_url, pool_pre_ping=True)
    with sessionmaker(bind=engine)() as session:
        print(json.dumps(import_workbook(session, args.workbook).to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
