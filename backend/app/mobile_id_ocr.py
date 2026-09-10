"""In-memory Egyptian National ID OCR adapted from IFIND's MIT pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import logging
from pathlib import Path
import re
from threading import Lock
from time import perf_counter
from typing import Any

logger = logging.getLogger(__name__)
# The app configures no root logging handler/level, so these diagnostic
# .info() calls (dimensions/confidence/counts only, never PII) would
# otherwise be silently dropped at the default WARNING root level. Attach a
# handler directly to this logger only, so OCR pipeline diagnostics are
# visible without changing logging behavior anywhere else in the app.
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    logger.addHandler(_handler)
    logger.propagate = False
logger.setLevel(logging.INFO)

IDENTITY_SOURCE = "EGYPTIAN_ID_OCR_DEMO"
_MODEL_DIR = Path(__file__).resolve().parent / "ai_models" / "egyptian_id"
_OCR_TRANSLATION = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹OoIlSBDG",
    "0123456789012345678900115806",
)
_GOVERNORATES = {
    "01": "Cairo",
    "02": "Alexandria",
    "03": "Port Said",
    "04": "Suez",
    "11": "Damietta",
    "12": "Dakahlia",
    "13": "Sharqia",
    "14": "Qalyubia",
    "15": "Kafr El Sheikh",
    "16": "Gharbia",
    "17": "Monufia",
    "18": "Beheira",
    "19": "Ismailia",
    "21": "Giza",
    "22": "Beni Suef",
    "23": "Fayoum",
    "24": "Minya",
    "25": "Assiut",
    "26": "Sohag",
    "27": "Qena",
    "28": "Aswan",
    "29": "Luxor",
    "31": "Red Sea",
    "32": "New Valley",
    "33": "Matrouh",
    "34": "North Sinai",
    "35": "South Sinai",
    "88": "Foreign",
}


@dataclass(frozen=True)
class DecodedNationalId:
    birth_date: date
    governorate: str
    gender: str


@dataclass(frozen=True)
class _ModelBundle:
    card_detector: Any
    field_detector: Any
    digit_detector: Any
    reader: Any


_models: _ModelBundle | None = None
_models_lock = Lock()


def model_paths() -> tuple[Path, Path, Path]:
    return (
        _MODEL_DIR / "detect_id_card.pt",
        _MODEL_DIR / "detect_odjects.pt",
        _MODEL_DIR / "detect_id.pt",
    )


def normalize_ocr_digits(value: str) -> str:
    """Normalize only OCR-typical glyph mistakes; manual input bypasses this."""
    return re.sub(r"[\s-]", "", str(value)).translate(_OCR_TRANSLATION)


def decode_national_id(value: str) -> DecodedNationalId:
    if re.fullmatch(r"[0-9]{14}", value) is None:
        raise ValueError("National ID must contain exactly 14 ASCII digits")
    century = {"2": 1900, "3": 2000}.get(value[0])
    if century is None:
        raise ValueError("Unsupported National ID century")
    birth_date = date(
        century + int(value[1:3]),
        int(value[3:5]),
        int(value[5:7]),
    )
    return DecodedNationalId(
        birth_date=birth_date,
        governorate=_GOVERNORATES.get(value[7:9], "Unknown"),
        gender="Male" if int(value[12]) % 2 else "Female",
    )


def _load_models() -> _ModelBundle:
    from easyocr import Reader
    from ultralytics import YOLO

    card_path, field_path, digit_path = model_paths()
    return _ModelBundle(
        card_detector=YOLO(card_path),
        field_detector=YOLO(field_path),
        digit_detector=YOLO(digit_path),
        reader=Reader(["ar"], gpu=False),
    )


def _get_models() -> _ModelBundle:
    global _models
    if _models is None:
        with _models_lock:
            if _models is None:
                _models = _load_models()
    return _models


def _box_coordinates(
    box: Any, shape: tuple[int, ...], *, pad_ratio: float = 0.08
) -> tuple[int, int, int, int] | None:
    """Detector box clamped to the image, with a small margin added first.

    A detector box is a best-effort estimate, not a pixel-perfect crop; a box
    drawn a few pixels too tight can shave off an edge digit or letter before
    OCR ever sees it. Padding by a ratio of the box's own size (rather than a
    fixed pixel count) keeps this proportionate across both a 250x196 field
    crop and a 1163x137 one.
    """
    height, width = shape[:2]
    x1, y1, x2, y2 = (int(value) for value in box.xyxy[0].tolist())
    pad_x = max(2, round((x2 - x1) * pad_ratio))
    pad_y = max(2, round((y2 - y1) * pad_ratio))
    x1, x2 = max(0, x1 - pad_x), min(width, x2 + pad_x)
    y1, y2 = max(0, y1 - pad_y), min(height, y2 + pad_y)
    return (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None


def _best_box_confidence(results: list[Any]) -> float | None:
    """Highest detector confidence across all boxes, or None if nothing fired."""
    scores = [
        float(box.conf[0])
        for result in results
        for box in result.boxes
    ]
    return max(scores) if scores else None


def _largest_crop(image: Any, results: list[Any]) -> Any | None:
    candidates: list[tuple[int, tuple[int, int, int, int]]] = []
    for result in results:
        for box in result.boxes:
            coords = _box_coordinates(box, image.shape)
            if coords is not None:
                x1, y1, x2, y2 = coords
                candidates.append(((x2 - x1) * (y2 - y1), coords))
    if not candidates:
        return None
    _, (x1, y1, x2, y2) = max(candidates, key=lambda item: item[0])
    return image[y1:y2, x1:x2]


def _read_arabic(reader: Any, crop: Any, *, field_label: str) -> str:
    import cv2

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    fragments = reader.readtext(gray, detail=0, paragraph=True)
    # Token count only, never the recognized text itself.
    logger.info(
        "OCR field=%s crop_wh=%dx%d tokens=%d",
        field_label,
        crop.shape[1],
        crop.shape[0],
        len(fragments),
    )
    return " ".join(str(fragment).strip() for fragment in fragments if str(fragment).strip())


def _read_national_id(detector: Any, crop: Any) -> str:
    digits: list[tuple[float, int]] = []
    for result in detector.predict(crop, verbose=False):
        for box in result.boxes:
            digits.append((float(box.xyxy[0][0]), int(box.cls[0])))
    logger.info(
        "OCR field=nid crop_wh=%dx%d digit_boxes=%d",
        crop.shape[1],
        crop.shape[0],
        len(digits),
    )
    return normalize_ocr_digits("".join(str(value) for _, value in sorted(digits)))


def _orient_card(card: Any, field_detector: Any) -> tuple[Any, list[Any]]:
    """Pick the rotation of the card crop that the field detector reads best.

    The card detector locates the card reliably regardless of how it was
    held, but a correctly-oriented Egyptian ID is landscape; if the citizen
    photographed it sideways, the crop comes out portrait-shaped and the
    field/digit detectors (trained on upright cards) fail almost entirely.
    Detecting that from the crop's own aspect ratio and testing both 90-degree
    rotations lets us pick the orientation the field detector actually
    recognizes, instead of guessing or asking for a retake unnecessarily.
    """
    import cv2

    height, width = card.shape[:2]
    candidates = [card]
    if height > width:
        candidates.append(cv2.rotate(card, cv2.ROTATE_90_CLOCKWISE))
        candidates.append(cv2.rotate(card, cv2.ROTATE_90_COUNTERCLOCKWISE))

    best_card = candidates[0]
    best_results: list[Any] = []
    best_score = (-1, -1.0)
    for candidate in candidates:
        results = list(field_detector.predict(candidate, verbose=False))
        classes = {
            str(result.names[int(box.cls[0])]).lower()
            for result in results
            for box in result.boxes
        }
        score = (len(classes), _best_box_confidence(results) or 0.0)
        if score > best_score:
            best_score = score
            best_card = candidate
            best_results = results
    return best_card, best_results


def _extract_fields(
    card: Any, models: _ModelBundle, field_results: list[Any] | None = None
) -> tuple[str, str, str]:
    names: dict[str, str] = {}
    address = ""
    national_id = ""
    if field_results is None:
        field_results = list(models.field_detector.predict(card, verbose=False))
    detected_classes = sorted(
        {
            str(result.names[int(box.cls[0])]).lower()
            for result in field_results
            for box in result.boxes
        }
    )
    logger.info(
        "Field detector confidence=%s classes_found=%s",
        _best_box_confidence(field_results),
        detected_classes,
    )
    for result in field_results:
        for box in result.boxes:
            coords = _box_coordinates(box, card.shape)
            if coords is None:
                continue
            x1, y1, x2, y2 = coords
            class_name = str(result.names[int(box.cls[0])]).lower()
            crop = card[y1:y2, x1:x2]
            if class_name in {"firstname", "lastname"}:
                names[class_name] = _read_arabic(models.reader, crop, field_label=class_name)
            elif class_name == "address":
                address = _read_arabic(models.reader, crop, field_label="address")
            elif class_name == "nid":
                national_id = _read_national_id(models.digit_detector, crop)
    full_name = " ".join(
        part for part in (names.get("firstname", ""), names.get("lastname", "")) if part
    )
    logger.info(
        "Fields resolved name_found=%s nid_len=%d address_found=%s",
        bool(full_name),
        len(national_id),
        bool(address),
    )
    return full_name, national_id, address


def _failure(code: str, message: str) -> dict[str, object]:
    return {"success": False, "code": code, "message": message, "extracted": None}


def scan_id_image(image_bytes: bytes) -> dict[str, object]:
    """Run the front-card OCR pipeline without persisting bytes or extracted PII."""
    import cv2
    import numpy as np

    started = perf_counter()
    logger.info("ID scan started, payload_bytes=%d", len(image_bytes))
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        logger.info("OCR validation failed: image did not decode")
        return _failure("INVALID_IMAGE", "The uploaded file is not a readable image.")
    logger.info(
        "Image decoded wh=%dx%d orientation=%s",
        image.shape[1],
        image.shape[0],
        "landscape" if image.shape[1] >= image.shape[0] else "portrait",
    )

    models = _get_models()
    card_results = list(models.card_detector.predict(image, verbose=False))
    logger.info(
        "Card detector confidence=%s", _best_box_confidence(card_results)
    )
    card = _largest_crop(image, card_results)
    if card is None:
        logger.info("OCR validation failed: no card bounding box above threshold")
        return _failure(
            "ID_CARD_NOT_DETECTED",
            "We could not detect the ID card. Retake the photo with the full card visible.",
        )
    logger.info("ID card detected, crop_wh=%dx%d", card.shape[1], card.shape[0])

    oriented_card, field_results = _orient_card(card, models.field_detector)
    if oriented_card.shape[:2] != card.shape[:2]:
        logger.info(
            "Card orientation corrected, crop_wh=%dx%d",
            oriented_card.shape[1],
            oriented_card.shape[0],
        )
    card = oriented_card

    full_name, national_id, address = _extract_fields(card, models, field_results)
    try:
        decoded = decode_national_id(national_id)
    except ValueError:
        logger.info(
            "OCR validation failed: national id did not decode, nid_len=%d",
            len(national_id),
        )
        return _failure(
            "INVALID_NATIONAL_ID",
            "We could not read a valid National ID. Retake the photo in good lighting.",
        )

    warnings = []
    if not full_name:
        warnings.append("Full name could not be read; enter it manually.")
    if not address:
        warnings.append("Registered address could not be read; enter it manually.")
    logger.info("OCR completed in %d ms", round((perf_counter() - started) * 1000))
    return {
        "success": True,
        "extracted": {
            "full_name": full_name,
            "national_id": national_id,
            "registered_address_text": address,
            "birth_date": decoded.birth_date.isoformat(),
            "governorate": decoded.governorate,
            "gender": decoded.gender,
        },
        "warnings": warnings,
        "identity_source": IDENTITY_SOURCE,
    }
