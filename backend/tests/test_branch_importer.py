from pathlib import Path

from app.services.branch_importer import EXPECTED_ROW_COUNT, REQUIRED_COLUMNS, validate_rows, validate_workbook


WORKBOOK = Path(__file__).parents[2] / "Stores Master Sep2026.xlsx"


def test_actual_branch_master_workbook_validates() -> None:
    result = validate_workbook(WORKBOOK)

    assert result.sheet_name == "Sheet1"
    assert result.columns == list(REQUIRED_COLUMNS)
    assert result.report.total_rows == EXPECTED_ROW_COUNT
    assert result.report.valid_rows == EXPECTED_ROW_COUNT
    assert result.report.invalid_rows == 0
    assert result.report.duplicate_rows == 0
    assert result.report.expected_row_count_match is True
    assert result.report.validation_errors == []


def test_validation_reports_all_row_errors_and_duplicates() -> None:
    rows = [
        (2, {"StoreNumber": "1", "StoreName": "First", "Lat": "13.7", "Long": "100.5"}),
        (3, {"StoreNumber": "1", "StoreName": "", "Lat": "91", "Long": ""}),
        (4, {"StoreNumber": "not-a-number", "StoreName": "Third", "Lat": "13", "Long": "181"}),
    ]
    result = validate_rows(rows, columns=list(REQUIRED_COLUMNS), sheet_name="Sheet1")

    assert result.report.valid_rows == 0
    assert result.report.invalid_rows == 3
    assert result.report.duplicate_rows == 2
    assert {error.field for error in result.report.validation_errors} >= {"StoreNumber", "StoreName", "Lat", "Long", "row_count"}


def test_non_numeric_store_number_is_rejected() -> None:
    result = validate_rows(
        [(2, {"StoreNumber": "not-a-number", "StoreName": "Branch", "Lat": "13", "Long": "100"})],
        columns=list(REQUIRED_COLUMNS),
        sheet_name="Sheet1",
    )

    assert result.report.invalid_rows == 1
    assert any(error.field == "StoreNumber" for error in result.report.validation_errors)
