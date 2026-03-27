"""
Detection Router
POST /api/v1/detect/mobile        — mobile app video frame analysis (5-sec intervals)
POST /api/v1/detect/yolo          — direct YOLO inference on uploaded image
POST /api/v1/detect/report        — submit a pothole detection (form-based)
POST /api/v1/detect/batch         — batch submit multiple sensor readings
GET  /api/v1/detect/status/{pothole_id} — check pothole confirmation status
"""

import uuid
import json
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.dependencies import get_db, get_current_rider
from app.schemas.schemas import DetectionResponse, MobileDetectionPayload, SensorWindow
from app.models.rider import Rider
from app.models.pothole import Pothole, PotholeReport, PotholeStatus, Severity, PotholeType
from app.services.clustering import find_nearby_pothole, create_candidate, update_confirmation, deduplicate_nearby_candidates
from app.services.alert_service import trigger_nearby_alerts, update_rider_location
from app.services.ml_inference import run_yolo_inference, run_lstm_inference
from app.config import get_settings

router = APIRouter(prefix="/detect", tags=["detection"])
settings = get_settings()


import logging
logger = logging.getLogger(__name__)

@router.post("/mobile", response_model=DetectionResponse, status_code=202)
async def mobile_video_frame_analysis_wrapper(
    background_tasks: BackgroundTasks,
    rider_id: str = Form(..., description="Rider ID (UUID)"),
    latitude: float = Form(..., ge=-90, le=90, description="GPS Latitude"),
    longitude: float = Form(..., ge=-180, le=180, description="GPS Longitude"),
    speed_kmh: Optional[float] = Form(None, ge=0, le=200, description="Current speed in km/h"),
    frame_timestamp_ms: float = Form(..., description="Frame timestamp in milliseconds"),
    accuracy_meters: Optional[float] = Form(None, description="GPS accuracy in meters"),
    altitude_meters: Optional[float] = Form(None, description="Altitude in meters"),
    heading_degrees: Optional[float] = Form(None, ge=-1, le=360, description="Heading in degrees"),
    video_segment_id: Optional[str] = Form(None, description="Video segment ID"),
    ride_id: Optional[str] = Form(None, description="Ride session ID"),
    is_night_mode: bool = Form(False, description="Night mode enabled"),
    weather_condition: Optional[str] = Form(None, description="clear/rain/fog/haze"),
    road_type: Optional[str] = Form(None, description="highway/main_road/side_street"),
    sensor_readings_json: Optional[str] = Form(None, description="JSON array of accelerometer readings"),
    image: UploadFile = File(..., description="Video frame image file"),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _mobile_detection_impl(
            background_tasks, rider_id, latitude, longitude, speed_kmh,
            frame_timestamp_ms, accuracy_meters, altitude_meters, heading_degrees,
            video_segment_id, ride_id, is_night_mode, weather_condition, road_type,
            sensor_readings_json, image, db
        )
    except Exception as e:
        logger.error(f"Detection error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _mobile_detection_impl(
    background_tasks: BackgroundTasks,
    rider_id: str,
    latitude: float,
    longitude: float,
    speed_kmh: Optional[float],
    frame_timestamp_ms: float,
    accuracy_meters: Optional[float],
    altitude_meters: Optional[float],
    heading_degrees: Optional[float],
    video_segment_id: Optional[str],
    ride_id: Optional[str],
    is_night_mode: bool,
    weather_condition: Optional[str],
    road_type: Optional[str],
    sensor_readings_json: Optional[str],
    image: UploadFile,
    db: AsyncSession,
):
    """
    Mobile app endpoint for video frame analysis.
    
    **In Swagger UI:**
    1. Fill in the form fields (rider_id, latitude, longitude, speed_kmh, etc.)
    2. Click "Choose File" button to select an image for the image field
    3. Click Execute
    
    **For sensor data**, paste JSON like:
    ```json
    [{"x":0.1,"y":0.2,"z":9.8,"timestamp_ms":1712345678901}]
    ```
    """
    lat = latitude
    lon = longitude
    
    yolo_result = None
    lstm_result = None
    image_s3_key = None
    yolo_bbox_json = None
    
    # ── 1. YOLO Inference (if image provided) ──────────────────────────────────
    if image and image.content_type and image.content_type.startswith("image/"):
        image_bytes = await image.read()
        yolo_result = await run_yolo_inference(image_bytes)
        
        if yolo_result.detected:
            yolo_bbox_json = json.dumps(yolo_result.bbox)
            image_s3_key = f"reports/{rider_id}/{uuid.uuid4()}.jpg"
            background_tasks.add_task(_upload_to_s3, image_bytes, image_s3_key)
    
    # ── 2. LSTM Inference (if sensor window provided) ─────────────────────────
    if sensor_readings_json:
        try:
            readings = json.loads(sensor_readings_json)
            if readings and len(readings) > 0:
                lstm_result = await run_lstm_inference(readings)
        except (json.JSONDecodeError, Exception):
            pass
    
    # ── 3. Fuse Results ────────────────────────────────────────────────────────
    detected = False
    confidence = (speed_kmh or 0) / 200.0
    severity = "S1"
    pothole_type = "dry"
    
    if yolo_result and yolo_result.detected:
        detected = True
        confidence = max(confidence, yolo_result.confidence)
        severity = yolo_result.severity
        if yolo_result.water_filled:
            pothole_type = "water_filled"
    
    if lstm_result and lstm_result.detected:
        detected = True
        confidence = max(confidence, lstm_result.confidence)
        severity = _max_severity(severity, lstm_result.severity)
    
    # Neither model detected - skip recording
    if not detected:
        return DetectionResponse(
            pothole_id="",
            status="not_detected",
            report_count=0,
            severity=severity,
            message="No pothole detected by ML models.",
            yolo_confidence=yolo_result.confidence if yolo_result else None,
            lstm_severity=lstm_result.severity if lstm_result else None,
        )
    
    # ── 4. Record Detection ───────────────────────────────────────────────────
    rider_result = await db.execute(
        text("SELECT accuracy_score FROM riders WHERE id = :id"),
        {"id": rider_id}
    )
    rider_row = rider_result.fetchone()
    rider_weight = float(rider_row[0]) if rider_row and rider_row[0] is not None else 1.0
    
    pothole = await find_nearby_pothole(lat, lon, db)
    
    if not pothole:
        city = await _reverse_geocode_city(lat, lon)
        pothole = await create_candidate(
            lat=lat, lon=lon,
            severity=severity, pothole_type=pothole_type,
            city=city, db=db,
        )
    
    detection_method = "both" if (yolo_result and lstm_result) else ("camera" if yolo_result else "sensor")
    
    # Convert severity string to enum
    severity_enum = Severity.S1
    if severity == "S2":
        severity_enum = Severity.S2
    elif severity == "S3":
        severity_enum = Severity.S3
    
    report = PotholeReport(
        id=str(uuid.uuid4()),
        pothole_id=pothole.id,
        rider_id=rider_id,
        latitude=lat,
        longitude=lon,
        severity=severity_enum,
        detection_method=detection_method,
        confidence=confidence,
        pothole_type=pothole_type,
        image_s3_key=image_s3_key,
        yolo_bbox=yolo_bbox_json,
        rider_weight=rider_weight,
        speed_kmh=speed_kmh,
    )
    db.add(report)
    await db.flush()
    
    pothole, just_confirmed = await update_confirmation(pothole, report, db)
    await db.commit()
    
    # ── 5. Side Effects ───────────────────────────────────────────────────────
    if just_confirmed:
        background_tasks.add_task(_run_dedup, pothole.id, lat, lon)
        background_tasks.add_task(trigger_nearby_alerts, pothole.id, lat, lon)
        background_tasks.add_task(_run_accountability, pothole.id)
        if image_s3_key:
            background_tasks.add_task(_set_best_image, pothole.id, image_s3_key)
    
    background_tasks.add_task(update_rider_location, rider_id, lat, lon, db)
    background_tasks.add_task(_increment_rider_reports, rider_id)
    
    status_msg = {
        PotholeStatus.CANDIDATE: f"Candidate logged. {settings.CONFIRMED_THRESHOLD - pothole.report_count} more reports to confirm.",
        PotholeStatus.CONFIRMED: "Pothole confirmed! Alerts dispatched.",
        PotholeStatus.REPAIR_CLAIMED: "Under repair claim.",
        PotholeStatus.REPAIRED: "Marked repaired.",
        PotholeStatus.FRAUD: "Under investigation.",
    }
    
    return DetectionResponse(
        pothole_id=pothole.id,
        status=pothole.status,
        report_count=pothole.report_count,
        severity=pothole.severity,
        message=status_msg.get(pothole.status, "Report recorded."),
        yolo_confidence=yolo_result.confidence if yolo_result else None,
        lstm_severity=lstm_result.severity if lstm_result else None,
        fused_confidence=confidence,
    )


@router.post("/yolo", response_model=dict, status_code=200)
async def yolo_detect(
    image: UploadFile = File(..., description="Upload an image for YOLO pothole detection. Supported formats: JPEG, PNG, JPG"),
):
    """
    Direct YOLO inference endpoint.
    Upload an image file and get instant pothole detection results.
    Returns bounding box, confidence score, severity, and water detection.
    """
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image (JPEG, PNG, or JPG)")

    image_bytes = await image.read()
    yolo_result = await run_yolo_inference(image_bytes)

    return {
        "detected": yolo_result.detected,
        "confidence": yolo_result.confidence,
        "severity": yolo_result.severity,
        "water_filled": yolo_result.water_filled,
        "bbox": yolo_result.bbox,
    }


@router.post("/report", response_model=DetectionResponse, status_code=202)
async def submit_detection(
    background_tasks: BackgroundTasks,
    rider_id: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    detection_method: str = Form(...),
    confidence: float = Form(...),
    severity: str = Form(...),
    pothole_type: str = Form("dry"),
    speed_kmh: Optional[float] = Form(None),
    sensor_json: Optional[str] = Form(None),
    image: UploadFile = File(..., description="Upload an image file for YOLO pothole detection. Supported formats: JPEG, PNG, JPG"),
    db: AsyncSession = Depends(get_db),
):
    """
    Main detection ingestion endpoint.
    Called by rider app passively as they ride.
    Handles ML inference, clustering, confirmation, and alert dispatch.
    
    **Image is required** - if no image is uploaded, use /api/v1/detect/mobile endpoint instead.
    """

    # ── 1. Run YOLO inference if image provided ───────────────────────────────
    yolo_result = None
    image_s3_key = None
    yolo_bbox_json = None

    if image and image.content_type and image.content_type.startswith("image/"):
        image_bytes = await image.read()
        yolo_result = await run_yolo_inference(image_bytes)

        # If YOLO disagrees strongly with reported confidence, reconcile
        if yolo_result.detected:
            # Camera confirmed — take max confidence
            confidence = max(confidence, yolo_result.confidence)
            severity = _max_severity(severity, yolo_result.severity)
            if yolo_result.water_filled:
                pothole_type = "water_filled"
            if yolo_result.bbox:
                yolo_bbox_json = json.dumps(yolo_result.bbox)
        elif detection_method == "camera" and not yolo_result.detected:
            # Camera-only report rejected by YOLO — discard
            return DetectionResponse(
                pothole_id="",
                status="rejected",
                report_count=0,
                severity=severity,
                message="Image analysis did not confirm pothole. Report discarded.",
            )

        # Upload image to S3 in background
        if image_bytes:
            image_s3_key = f"reports/{rider_id}/{uuid.uuid4()}.jpg"
            background_tasks.add_task(_upload_to_s3, image_bytes, image_s3_key)

    # ── 2. Run LSTM inference if sensor data provided ─────────────────────────
    if sensor_json and detection_method in ("sensor", "both"):
        try:
            sensor_window = json.loads(sensor_json)
            lstm_result = await run_lstm_inference(sensor_window)
            if lstm_result.detected:
                severity = _max_severity(severity, lstm_result.severity)
                confidence = max(confidence, lstm_result.confidence)
            elif detection_method == "sensor" and not lstm_result.detected:
                return DetectionResponse(
                    pothole_id="",
                    status="rejected",
                    report_count=0,
                    severity=severity,
                    message="Sensor analysis did not confirm pothole impact.",
                )
        except (json.JSONDecodeError, Exception):
            pass  # sensor parsing failure — proceed with reported confidence

    # ── 3. Get rider weight for weighted clustering ───────────────────────────
    rider_result = await db.execute(
        text("SELECT accuracy_score FROM riders WHERE id = :id"),
        {"id": rider_id}
    )
    rider_row = rider_result.fetchone()
    rider_weight = float(rider_row[0]) if rider_row else 1.0

    # ── 4. Find existing nearby pothole or create candidate ───────────────────
    pothole = await find_nearby_pothole(latitude, longitude, db)

    if not pothole:
        city = await _reverse_geocode_city(latitude, longitude)
        pothole = await create_candidate(
            lat=latitude, lon=longitude,
            severity=severity, pothole_type=pothole_type,
            city=city, db=db,
        )

    # ── 5. Record the individual report ──────────────────────────────────────
    report = PotholeReport(
        id=str(uuid.uuid4()),
        pothole_id=pothole.id,
        rider_id=rider_id,
        latitude=latitude,
        longitude=longitude,
        severity=severity,
        detection_method=detection_method,
        confidence=confidence,
        pothole_type=pothole_type,
        image_s3_key=image_s3_key,
        yolo_bbox=yolo_bbox_json,
        rider_weight=rider_weight,
        speed_kmh=speed_kmh,
    )
    db.add(report)
    await db.flush()

    # ── 6. Update confirmation state ──────────────────────────────────────────
    pothole, just_confirmed = await update_confirmation(pothole, report, db)
    await db.commit()

    # ── 7. Post-confirmation side effects ─────────────────────────────────────
    if just_confirmed:
        # Merge duplicate nearby candidates
        background_tasks.add_task(_run_dedup, pothole.id, latitude, longitude)
        # Push real-time alerts to nearby riders
        background_tasks.add_task(trigger_nearby_alerts, pothole.id, latitude, longitude)
        # Link to contractor + calculate damage
        background_tasks.add_task(_run_accountability, pothole.id)
        # Update best image
        if image_s3_key:
            background_tasks.add_task(_set_best_image, pothole.id, image_s3_key)

    # ── 8. Update rider location ──────────────────────────────────────────────
    background_tasks.add_task(update_rider_location, rider_id, latitude, longitude, db)

    # ── 9. Update rider report count ─────────────────────────────────────────
    background_tasks.add_task(_increment_rider_reports, rider_id)

    status_msg = {
        PotholeStatus.CANDIDATE: f"Candidate logged. {settings.CONFIRMED_THRESHOLD - pothole.report_count} more reports to confirm.",
        PotholeStatus.CONFIRMED: "Pothole confirmed! Alerts dispatched to nearby riders.",
        PotholeStatus.REPAIR_CLAIMED: "Pothole under repair claim.",
        PotholeStatus.REPAIRED: "This pothole is marked repaired.",
        PotholeStatus.FRAUD: "Repair claim under investigation.",
    }

    return DetectionResponse(
        pothole_id=pothole.id,
        status=pothole.status,
        report_count=pothole.report_count,
        severity=pothole.severity,
        message=status_msg.get(pothole.status, "Report recorded."),
    )


@router.get("/status/{pothole_id}")
async def get_detection_status(pothole_id: str, db: AsyncSession = Depends(get_db)):
    pothole = await db.get(Pothole, pothole_id)
    if not pothole:
        raise HTTPException(status_code=404, detail="Pothole not found")
    return {
        "id": pothole.id,
        "status": pothole.status,
        "severity": pothole.severity,
        "report_count": pothole.report_count,
        "camera_confirmed": pothole.camera_confirmed,
        "sensor_confirmed": pothole.sensor_confirmed,
        "contractor_id": pothole.contractor_id,
        "estimated_damage_inr": pothole.estimated_damage_inr,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _max_severity(a: str, b: str) -> str:
    rank = {"S1": 1, "S2": 2, "S3": 3}
    return a if rank.get(a, 0) >= rank.get(b, 0) else b


async def _reverse_geocode_city(lat: float, lon: float) -> Optional[str]:
    """Best-effort city extraction. Returns None if unavailable."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": lat, "lon": lon, "format": "json"},
                headers={"User-Agent": "SadakSathi/1.0"},
            )
            data = r.json()
            return data.get("address", {}).get("city") or data.get("address", {}).get("town")
    except Exception:
        return None


async def _upload_to_s3(image_bytes: bytes, s3_key: str):
    try:
        import boto3
        from app.config import get_settings
        s = get_settings()
        client = boto3.client("s3", region_name=s.AWS_REGION)
        client.put_object(Bucket=s.S3_BUCKET, Key=s3_key, Body=image_bytes, ContentType="image/jpeg")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"S3 upload failed for {s3_key}: {e}")


async def _run_dedup(pothole_id: str, lat: float, lon: float):
    from app.db.session import AsyncSessionLocal
    from app.services.clustering import deduplicate_nearby_candidates
    async with AsyncSessionLocal() as db:
        pothole = await db.get(Pothole, pothole_id)
        if pothole:
            await deduplicate_nearby_candidates(pothole, db)
            await db.commit()


async def _run_accountability(pothole_id: str):
    from app.services.accountability import link_pothole_to_contractor
    await link_pothole_to_contractor(pothole_id)


async def _set_best_image(pothole_id: str, s3_key: str):
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE potholes SET best_image_s3_key=:key WHERE id=:id AND best_image_s3_key IS NULL"),
            {"key": s3_key, "id": pothole_id}
        )
        await db.commit()


async def _increment_rider_reports(rider_id: str):
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE riders SET total_reports = total_reports + 1 WHERE id = :id"),
            {"id": rider_id}
        )
        await db.commit()