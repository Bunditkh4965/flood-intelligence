"""Validation and persistence for the Distribution Center Master XLSX workbook."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import math
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree
from zipfile import ZipFile


EXPECTED_ROW_COUNT = 7
REQUIRED_COLUMNS = ("Dc Code", "Dcname", "City", "Lat", "Long")
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


@dataclass(frozen=True)
class ValidationError:
    row_number: int | None
    field: str
    message: str


@dataclass(frozen=True)
class DistributionCenterImportRow:
    row_number: int
    dc_code: str
    dc_name: str
    latitude: float
    longitude: float


@dataclass
class ImportReport:
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    duplicate_rows: int = 0
    inserted_rows: int = 0
    updated_rows: int = 0
    expected_row_count: int = EXPECTED_ROW_COUNT
    expected_row_count_match: bool = False
    validation_errors: list[ValidationError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        report = asdict(self)
        report["validation_errors"] = [asdict(error) for error in self.validation_errors]
        return report


@dataclass(frozen=True)
class ValidationResult:
    report: ImportReport
    rows: list[DistributionCenterImportRow]
    sheet_name: str
    columns: list[str]


class DistributionCenterImportValidationError(ValueError):
    """Raised before persistence when the source workbook is invalid."""


def _column_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha())
    index = 0
    for character in letters:
        index = index * 26 + ord(character.upper()) - ord("A") + 1
    return index - 1


def _shared_strings(archive: ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.iter(f"{_NS}t")) for item in root.findall(f"{_NS}si")]


def _cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> Any:
    cell_type = cell.get("t")
    value = cell.find(f"{_NS}v")
    raw_value = value.text if value is not None else None
    if cell_type == "s" and raw_value is not None:
        return shared_strings[int(raw_value)]
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{_NS}t"))
    if cell_type == "b":
        return raw_value == "1"
    return raw_value


def _read_xlsx(path: Path) -> tuple[str, list[str], list[tuple[int, dict[str, Any]]]]:
    with ZipFile(path) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.find(f"{_NS}sheets")
        if sheets is None or not list(sheets):
            raise DistributionCenterImportValidationError("Workbook contains no worksheets")
        first_sheet = list(sheets)[0]
        sheet_name = first_sheet.get("name", "")
        relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationship_id = first_sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = next((item.get("Target") for item in relationships if item.get("Id") == relationship_id), None)
        if target is None:
            raise DistributionCenterImportValidationError("Unable to resolve the first worksheet")
        worksheet_path = target.lstrip("/")
        if not worksheet_path.startswith("xl/"):
            worksheet_path = "xl/" + worksheet_path
        shared_strings = _shared_strings(archive)
        worksheet = ElementTree.fromstring(archive.read(worksheet_path))

    sheet_data = worksheet.find(f"{_NS}sheetData")
    worksheet_rows = [] if sheet_data is None else list(sheet_data)
    if not worksheet_rows:
        raise DistributionCenterImportValidationError("Worksheet contains no header row")

    def row_values(row: ElementTree.Element) -> dict[int, Any]:
        return {_column_index(cell.get("r", "")): _cell_value(cell, shared_strings) for cell in row.findall(f"{_NS}c")}

    header_values = row_values(worksheet_rows[0])
    columns = [header_values.get(index, "") for index in range(max(header_values, default=-1) + 1)]
    rows = [
        (int(row.get("r", "0")), {columns[index]: value for index, value in row_values(row).items() if index < len(columns)})
        for row in worksheet_rows[1:]
    ]
    return sheet_name, columns, rows


def _required_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def _coordinate(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or not str(value).strip():
        return None
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        return None
    return coordinate if math.isfinite(coordinate) else None


def validate_rows(rows: Iterable[tuple[int, dict[str, Any]]], *, columns: list[str], sheet_name: str) -> ValidationResult:
    """Validate every source row before any persistence is attempted."""
    report = ImportReport()
    source_rows = list(rows)
    report.total_rows = len(source_rows)
    report.expected_row_count_match = report.total_rows == report.expected_row_count
    if tuple(columns) != REQUIRED_COLUMNS:
        report.validation_errors.append(ValidationError(None, "columns", f"Expected columns {list(REQUIRED_COLUMNS)!r}; found {columns!r}"))
    if not report.expected_row_count_match:
        report.validation_errors.append(ValidationError(None, "row_count", f"Expected {report.expected_row_count} rows; found {report.total_rows}"))

    normalized_codes = [_required_text(data.get("Dc Code")) for _, data in source_rows]
    duplicates = {code for code, count in Counter(code for code in normalized_codes if code is not None).items() if count > 1}
    valid_rows: list[DistributionCenterImportRow] = []
    for (row_number, data), dc_code in zip(source_rows, normalized_codes, strict=True):
        errors: list[ValidationError] = []
        if dc_code is None:
            errors.append(ValidationError(row_number, "Dc Code", "Dc Code is required"))
        elif dc_code in duplicates:
            report.duplicate_rows += 1
            errors.append(ValidationError(row_number, "Dc Code", f"Duplicate Dc Code: {dc_code}"))
        dc_name = _required_text(data.get("Dcname"))
        if dc_name is None:
            errors.append(ValidationError(row_number, "Dcname", "Dcname is required"))
        latitude = _coordinate(data.get("Lat"))
        longitude = _coordinate(data.get("Long"))
        if latitude is None:
            errors.append(ValidationError(row_number, "Lat", "Latitude is required and must be numeric and finite"))
        elif not -90 <= latitude <= 90:
            errors.append(ValidationError(row_number, "Lat", "Latitude must be between -90 and 90"))
        if longitude is None:
            errors.append(ValidationError(row_number, "Long", "Longitude is required and must be numeric and finite"))
        elif not -180 <= longitude <= 180:
            errors.append(ValidationError(row_number, "Long", "Longitude must be between -180 and 180"))
        if errors:
            report.invalid_rows += 1
            report.validation_errors.extend(errors)
            continue
        valid_rows.append(DistributionCenterImportRow(row_number, dc_code, dc_name, latitude, longitude))
    report.valid_rows = len(valid_rows)
    return ValidationResult(report=report, rows=valid_rows, sheet_name=sheet_name, columns=columns)


def validate_workbook(path: str | Path) -> ValidationResult:
    """Read and fully validate a Distribution Center Master XLSX workbook."""
    workbook_path = Path(path)
    if not workbook_path.is_file():
        raise FileNotFoundError(f"Workbook not found: {workbook_path}")
    sheet_name, columns, rows = _read_xlsx(workbook_path)
    return validate_rows(rows, columns=columns, sheet_name=sheet_name)


def import_workbook(session: Any, path: str | Path) -> ImportReport:
    """Upsert a fully valid workbook using ``dc_code`` as the natural key."""
    result = validate_workbook(path)
    if result.report.validation_errors:
        raise DistributionCenterImportValidationError(result.report.to_dict())

    from sqlalchemy import func, select
    from app.models.transport import DistributionCenter

    for row in result.rows:
        distribution_center = session.scalar(select(DistributionCenter).where(DistributionCenter.dc_code == row.dc_code))
        location = func.ST_SetSRID(func.ST_MakePoint(row.longitude, row.latitude), 4326)
        values = {
            "dc_name": row.dc_name,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "location": location,
        }
        if distribution_center is None:
            session.add(DistributionCenter(dc_code=row.dc_code, **values))
            result.report.inserted_rows += 1
        else:
            for field_name, value in values.items():
                setattr(distribution_center, field_name, value)
            result.report.updated_rows += 1
    session.commit()
    return result.report
