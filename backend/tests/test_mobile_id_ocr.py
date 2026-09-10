from __future__ import annotations

from datetime import date
from typing import Any

import app.mobile_api as mobile_api
import numpy as np
import pytest
from app.db import init_db
from app.main import app
from app.models import CitizenProfile
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session


class _FakeBox:
    """Minimal stand-in for an ultralytics Boxes row: xyxy/conf/cls."""

    def __init__(self, xyxy: list[float], conf: float = 0.9, cls: int = 0) -> None:
        self.xyxy = [np.array(xyxy, dtype=float)]
        self.conf = [conf]
        self.cls = [cls]


class _FakeResult:
    def __init__(self, boxes: list[_FakeBox], names: dict[int, str]) -> None:
        self.boxes = boxes
        self.names = names


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _success() -> dict[str, object]:
    return {
        "success": True,
        "extracted": {
            "full_name": "Test Citizen",
            "national_id": "29001010123456",
            "registered_address_text": "Nasr City, Cairo",
            "birth_date": "1990-01-01",
            "governorate": "Cairo",
            "gender": "Male",
        },
        "warnings": [],
        "identity_source": "EGYPTIAN_ID_OCR_DEMO",
    }


@pytest.mark.parametrize(
    ("content_type", "payload"),
    [("image/jpeg", b"\xff\xd8\xffphoto"), ("image/png", b"\x89PNG\r\n\x1a\nphoto")],
)
def test_scan_accepts_supported_images(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    content_type: str,
    payload: bytes,
) -> None:
    monkeypatch.setattr(mobile_api, "scan_id_image", lambda _: _success())

    response = client.post(
        "/api/v1/mobile/auth/scan-national-id",
        files={"file": ("front", payload, content_type)},
    )

    assert response.status_code == 200
    assert response.json() == _success()


def test_scan_rejects_empty_upload(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mobile/auth/scan-national-id",
        files={"file": ("front.jpg", b"", "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EMPTY_IMAGE"


def test_scan_rejects_unsupported_media(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mobile/auth/scan-national-id",
        files={"file": ("front.gif", b"GIF89a", "image/gif")},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "UNSUPPORTED_IMAGE_TYPE"


def test_scan_rejects_oversized_upload(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mobile_api, "MAX_ID_IMAGE_BYTES", 4)
    response = client.post(
        "/api/v1/mobile/auth/scan-national-id",
        files={"file": ("front.jpg", b"12345", "image/jpeg")},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "IMAGE_TOO_LARGE"


@pytest.mark.parametrize("code", ["ID_CARD_NOT_DETECTED", "OCR_NOT_CLEAR"])
def test_scan_returns_controlled_ocr_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    result = {
        "success": False,
        "code": code,
        "message": "Retake the photo.",
        "extracted": None,
    }
    monkeypatch.setattr(mobile_api, "scan_id_image", lambda _: result)
    response = client.post(
        "/api/v1/mobile/auth/scan-national-id",
        files={"file": ("front.jpg", b"\xff\xd8\xffphoto", "image/jpeg")},
    )
    assert response.status_code == 200
    assert response.json() == result


def test_unexpected_ocr_exception_is_safe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_: bytes) -> dict[str, object]:
        raise RuntimeError("private model path and traceback")

    monkeypatch.setattr(mobile_api, "scan_id_image", fail)
    response = client.post(
        "/api/v1/mobile/auth/scan-national-id",
        files={"file": ("front.jpg", b"\xff\xd8\xffphoto", "image/jpeg")},
    )
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "OCR_UNAVAILABLE"
    assert "private" not in str(body)
    assert "traceback" not in str(body)


def test_scan_does_not_write_database(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mobile_api, "scan_id_image", lambda _: _success())
    client.post(
        "/api/v1/mobile/auth/scan-national-id",
        files={"file": ("front.jpg", b"\xff\xd8\xffphoto", "image/jpeg")},
    )
    assert db_session.scalars(select(CitizenProfile)).all() == []


def test_undecodable_image_returns_controlled_failure(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mobile/auth/scan-national-id",
        files={"file": ("front.jpg", b"not-an-image", "image/jpeg")},
    )
    assert response.status_code == 200
    assert response.json()["code"] == "INVALID_IMAGE"


def test_ocr_digit_cleanup_is_bounded() -> None:
    from app.mobile_id_ocr import normalize_ocr_digits

    assert normalize_ocr_digits("٢٩O٠١٠١O١٢٣٤٥٦") == "29001010123456"
    assert normalize_ocr_digits("not an id") == "n0tanid"


def test_valid_national_id_decodes_derived_fields() -> None:
    from app.mobile_id_ocr import decode_national_id

    decoded = decode_national_id("29001010123456")
    assert decoded.birth_date == date(1990, 1, 1)
    assert decoded.governorate == "Cairo"
    assert decoded.gender == "Male"


@pytest.mark.parametrize(
    "value",
    ["49001010123456", "29002310123456", "2900101012345", "2900101012345A"],
)
def test_invalid_national_id_is_rejected(value: str) -> None:
    from app.mobile_id_ocr import decode_national_id

    with pytest.raises(ValueError):
        decode_national_id(value)


def test_unknown_governorate_is_safe() -> None:
    from app.mobile_id_ocr import decode_national_id

    assert decode_national_id("29001019923456").governorate == "Unknown"


def test_model_paths_are_module_relative() -> None:
    from app.mobile_id_ocr import model_paths

    paths = model_paths()
    assert {path.name for path in paths} == {
        "detect_id_card.pt",
        "detect_odjects.pt",
        "detect_id.pt",
    }
    assert all(path.is_file() for path in paths)


def test_box_coordinates_pads_to_avoid_clipping_edge_content() -> None:
    """Regression: a real-device NID crop returned 13 of 14 digit boxes
    because the field detector's box was drawn a few pixels too tight,
    clipping the edge digit before the digit detector ever saw it."""
    from app.mobile_id_ocr import _box_coordinates

    box = _FakeBox([10, 10, 20, 20])
    assert _box_coordinates(box, (100, 100, 3)) == (8, 8, 22, 22)


def test_box_coordinates_padding_clamps_to_image_bounds() -> None:
    from app.mobile_id_ocr import _box_coordinates

    box = _FakeBox([0, 0, 5, 5])
    assert _box_coordinates(box, (50, 50, 3)) == (0, 0, 7, 7)


def test_orient_card_rotates_portrait_crop_to_landscape() -> None:
    """Regression: a card photographed sideways produced a portrait crop
    that the field detector (trained on upright cards) almost entirely
    failed to read (0.55 confidence, 2 of 8 classes, on a real capture)."""
    from app.mobile_id_ocr import _orient_card

    portrait_card = np.zeros((40, 20, 3), dtype=np.uint8)

    class _FieldDetector:
        def predict(self, image: Any, verbose: bool = False) -> list[_FakeResult]:
            height, width = image.shape[:2]
            if width > height:
                return [_FakeResult([_FakeBox([1, 1, 5, 5])], {0: "firstname"})]
            return [_FakeResult([], {})]

    oriented, results = _orient_card(portrait_card, _FieldDetector())

    assert oriented.shape[1] > oriented.shape[0]
    assert sum(len(result.boxes) for result in results) == 1


def test_orient_card_leaves_landscape_crop_untouched() -> None:
    """A correctly-oriented card must not be rotated or re-scored twice."""
    from app.mobile_id_ocr import _orient_card

    landscape_card = np.zeros((20, 40, 3), dtype=np.uint8)
    predict_calls: list[tuple[int, int]] = []

    class _FieldDetector:
        def predict(self, image: Any, verbose: bool = False) -> list[_FakeResult]:
            predict_calls.append(image.shape[:2])
            return [_FakeResult([], {})]

    oriented, _results = _orient_card(landscape_card, _FieldDetector())

    assert oriented is landscape_card
    assert predict_calls == [(20, 40)]


def test_models_are_cached_process_wide(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.mobile_id_ocr as ocr

    sentinel = object()
    loads = 0

    def load() -> object:
        nonlocal loads
        loads += 1
        return sentinel

    monkeypatch.setattr(ocr, "_models", None)
    monkeypatch.setattr(ocr, "_load_models", load)
    assert ocr._get_models() is sentinel
    assert ocr._get_models() is sentinel
    assert loads == 1
