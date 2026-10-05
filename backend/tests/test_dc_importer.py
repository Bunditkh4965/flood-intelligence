from app.services.dc_importer import EXPECTED_ROW_COUNT, REQUIRED_COLUMNS, validate_rows


def _valid_rows() -> list[tuple[int, dict[str, str]]]:
    return [
        (
            row_number,
            {
                "Dc Code": f"DC-{row_number - 1}",
                "Dcname": f"Distribution Center {row_number - 1}",
                "City": "ignored",
                "Lat": str(10 + row_number),
                "Long": str(100 + row_number),
            },
        )
        for row_number in range(2, EXPECTED_ROW_COUNT + 2)
    ]


def test_valid_distribution_center_rows_are_normalized_and_city_is_ignored() -> None:
    result = validate_rows(_valid_rows(), columns=list(REQUIRED_COLUMNS), sheet_name="Sheet1")

    assert result.report.total_rows == EXPECTED_ROW_COUNT
    assert result.report.valid_rows == EXPECTED_ROW_COUNT
    assert result.report.invalid_rows == 0
    assert result.report.duplicate_rows == 0
    assert result.report.expected_row_count_match is True
    assert result.report.validation_errors == []
    assert result.rows[0].dc_code == "DC-1"
    assert result.rows[0].dc_name == "Distribution Center 1"
    assert result.rows[0].latitude == 12.0
    assert result.rows[0].longitude == 102.0
    assert not hasattr(result.rows[0], "city")


def test_validation_reports_every_invalid_field_and_duplicate_row() -> None:
    rows = _valid_rows()
    rows[0][1].update({"Dc Code": " repeated ", "Dcname": "", "Lat": "nan", "Long": "181"})
    rows[1][1].update({"Dc Code": "repeated", "Lat": "-91", "Long": "infinity"})
    rows[2][1].update({"Dc Code": "", "Lat": "not-a-number", "Long": ""})

    result = validate_rows(rows, columns=list(REQUIRED_COLUMNS), sheet_name="Sheet1")

    assert result.report.valid_rows == 4
    assert result.report.invalid_rows == 3
    assert result.report.duplicate_rows == 2
    assert {error.field for error in result.report.validation_errors} == {"Dc Code", "Dcname", "Lat", "Long"}


def test_columns_and_expected_row_count_must_match_exactly() -> None:
    result = validate_rows(
        _valid_rows()[:-1],
        columns=["Dc Code", "Dcname", "Lat", "Long", "City"],
        sheet_name="Sheet1",
    )

    assert result.report.expected_row_count_match is False
    assert {error.field for error in result.report.validation_errors} >= {"columns", "row_count"}


def test_report_contains_the_documented_json_fields() -> None:
    report = validate_rows(_valid_rows(), columns=list(REQUIRED_COLUMNS), sheet_name="Sheet1").report.to_dict()

    assert set(report) == {
        "total_rows",
        "valid_rows",
        "invalid_rows",
        "duplicate_rows",
        "inserted_rows",
        "updated_rows",
        "expected_row_count",
        "expected_row_count_match",
        "validation_errors",
    }
