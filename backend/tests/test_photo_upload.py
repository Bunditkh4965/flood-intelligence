from pathlib import Path
from unittest.mock import Mock
import pytest
from app.schemas.flood_report import FloodReportCreate
from app.services.flood_reports import create_public_report, record_photo_and_recalculate
from app.services.photo_storage import InvalidPhoto, LocalPhotoStorage

JPEG=b"\xff\xd8\xffpayload\xff\xd9"

def test_local_storage_generates_safe_key_and_validates_content(tmp_path: Path):
    stored=LocalPhotoStorage(str(tmp_path),100).save(JPEG)
    assert stored.content_type=="image/jpeg" and stored.size==len(JPEG)
    assert "/" not in stored.key and (tmp_path/stored.key).read_bytes()==JPEG
    with pytest.raises(InvalidPhoto): LocalPhotoStorage(str(tmp_path),100).save(b"not an image")
    with pytest.raises(InvalidPhoto): LocalPhotoStorage(str(tmp_path),2).save(JPEG)

def test_create_never_trusts_client_has_photo(monkeypatch):
    db=Mock(); db.refresh=lambda _:None
    monkeypatch.setattr("app.services.flood_reports.allocate_report_code",lambda *_:"FR-20260924-00001")
    monkeypatch.setattr("app.services.flood_reports.calculate_distance_m",lambda *_ ,**__:10.0)
    monkeypatch.setattr("app.services.flood_reports.get_verification_radius_m",lambda _:300.0)
    report=create_public_report(db,FloodReportCreate(flood_latitude=14,flood_longitude=100,reporter_latitude=14,reporter_longitude=100,water_level_cm=5,has_photo=True))
    assert report.has_photo is False
    assert report.verification_status=="PENDING_REVIEW"

def test_persisted_photo_recalculates_verification(monkeypatch):
    report=Mock(id=1,reporter_latitude=14.0,reporter_flood_distance_m=10.0)
    db=Mock(); monkeypatch.setattr("app.services.flood_reports.get_verification_radius_m",lambda _:300.0)
    record_photo_and_recalculate(db,report,storage_key="safe.jpg",content_type="image/jpeg",file_size=12)
    assert report.has_photo is True and report.verification_status=="VERIFIED"
    db.commit.assert_called_once()
