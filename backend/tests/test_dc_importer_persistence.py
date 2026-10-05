from unittest.mock import Mock

import pytest

pytest.importorskip("sqlalchemy")

from app.models.transport import DistributionCenter
from app.services import dc_importer
from app.services.dc_importer import (
    DistributionCenterImportValidationError,
    EXPECTED_ROW_COUNT,
    REQUIRED_COLUMNS,
    import_workbook,
    validate_rows,
)


def _result():
    rows = [
        (row_number, {"Dc Code": f"DC{row_number}", "Dcname": f"DC {row_number}", "Lat": "13", "Long": "100"})
        for row_number in range(2, EXPECTED_ROW_COUNT + 2)
    ]
    return validate_rows(rows, columns=list(REQUIRED_COLUMNS), sheet_name="Sheet1")


def test_import_inserts_and_updates_without_overwriting_status(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _result()
    existing = DistributionCenter(
        dc_code="DC2", dc_name="Old", latitude=0, longitude=0, location="POINT(0 0)", status="INACTIVE"
    )
    session = Mock()
    session.scalar.side_effect = [existing, *([None] * (EXPECTED_ROW_COUNT - 1))]
    monkeypatch.setattr(dc_importer, "validate_workbook", lambda path: result)

    report = import_workbook(session, "unused.xlsx")

    assert report.inserted_rows == EXPECTED_ROW_COUNT - 1
    assert report.updated_rows == 1
    assert existing.dc_name == "DC 2"
    assert existing.latitude == 13.0
    assert existing.longitude == 100.0
    assert existing.status == "INACTIVE"
    assert session.add.call_count == EXPECTED_ROW_COUNT - 1
    inserted = session.add.call_args_list[0].args[0]
    assert inserted.dc_code == "DC3"
    assert "status" not in inserted.__dict__
    session.commit.assert_called_once_with()


def test_invalid_workbook_performs_no_database_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _result()
    result.report.validation_errors.append(dc_importer.ValidationError(2, "Lat", "invalid"))
    session = Mock()
    monkeypatch.setattr(dc_importer, "validate_workbook", lambda path: result)

    with pytest.raises(DistributionCenterImportValidationError):
        import_workbook(session, "unused.xlsx")

    session.scalar.assert_not_called()
    session.add.assert_not_called()
    session.commit.assert_not_called()
