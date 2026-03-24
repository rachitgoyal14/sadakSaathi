"""
Clustering & Confirmation Engine
---------------------------------
Core logic for:
  - Finding nearby existing potholes (geospatial clustering)
  - Updating confirmation state (candidate → confirmed)
  - Severity escalation
  - Weighted confidence using rider accuracy scores
"""

import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

from app.models.pothole import Pothole, PotholeReport, PotholeStatus, Severity
from app.core.geospatial import make_point_wkt, cluster_centroid
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SEVERITY_RANK = {"S1": 1, "S2": 2, "S3": 3}


async def find_nearby_pothole(
    lat: float, lon: float, db: AsyncSession
) -> Pothole | None:
    """
    Find an existing non-repaired pothole within CLUSTER_RADIUS_METERS.
    Uses PostGIS ST_DWithin on geography type for accurate meter-based search.
    """
    result = await db.execute(
        text("""
            SELECT id
            FROM potholes
            WHERE ST_DWithin(
                location::geography,
                ST_MakePoint(:lon, :lat)::geography,
                :radius
            )
            AND status NOT IN ('repaired', 'fraud')
            ORDER BY location::geography <-> ST_MakePoint(:lon, :lat)::geography
            LIMIT 1
        """),
        {"lat": lat, "lon": lon, "radius": settings.CLUSTER_RADIUS_METERS},
    )
    row = result.fetchone()
    if row:
        return await db.get(Pothole, row[0])
    return None


async def create_candidate(
    lat: float,
    lon: float,
    severity: str,
    pothole_type: str,
    city: str | None,
    db: AsyncSession,
) -> Pothole:
    """Create a new pothole candidate from first report."""
    import uuid
    pothole = Pothole(
        id=str(uuid.uuid4()),
        location=make_point_wkt(lat, lon),
        avg_lat=lat,
        avg_lon=lon,
        severity=severity,
        status=PotholeStatus.CANDIDATE,
        pothole_type=pothole_type,
        city=city,
        report_count=0,
    )
    db.add(pothole)
    await db.flush()
    return pothole


async def update_confirmation(
    pothole: Pothole,
    report: PotholeReport,
    db: AsyncSession,
) -> tuple[Pothole, bool]:
    """
    Update pothole confirmation state after a new report is attached.
    Returns (updated_pothole, just_confirmed) where just_confirmed=True
    means this report pushed it from candidate → confirmed.
    """
    was_confirmed = pothole.status == PotholeStatus.CONFIRMED
    pothole.report_count += 1

    # Track detection method counters
    method = report.detection_method
    if method in ("camera", "both"):
        pothole.camera_confirmed += 1
    if method in ("sensor", "both"):
        pothole.sensor_confirmed += 1
    if report.confidence >= 0.85:
        pothole.high_confidence_count += 1

    # Severity escalation — always take the worst reported
    if SEVERITY_RANK.get(report.severity, 0) > SEVERITY_RANK.get(pothole.severity, 0):
        pothole.severity = report.severity
        logger.info(f"Pothole {pothole.id} severity escalated to {pothole.severity}")

    # Water-filled type upgrade
    if report.pothole_type == "water_filled":
        pothole.pothole_type = "water_filled"

    # Recalculate centroid using all reports (load them)
    result = await db.execute(
        text("SELECT latitude, longitude, rider_weight FROM pothole_reports WHERE pothole_id = :pid"),
        {"pid": pothole.id}
    )
    all_reports = result.fetchall()
    if all_reports:
        total_w = sum(r[2] for r in all_reports)
        if total_w > 0:
            pothole.avg_lat = sum(r[0] * r[2] for r in all_reports) / total_w
            pothole.avg_lon = sum(r[1] * r[2] for r in all_reports) / total_w
            # Update PostGIS geometry to centroid
            await db.execute(
                text("UPDATE potholes SET location = ST_MakePoint(:lon, :lat) WHERE id = :id"),
                {"lon": pothole.avg_lon, "lat": pothole.avg_lat, "id": pothole.id}
            )

    # Status promotion logic
    # Bonus: camera + sensor both confirming = extra weight
    dual_confirmed = pothole.camera_confirmed > 0 and pothole.sensor_confirmed > 0
    effective_count = pothole.report_count + (2 if dual_confirmed else 0)

    if effective_count >= settings.CONFIRMED_THRESHOLD and not was_confirmed:
        pothole.status = PotholeStatus.CONFIRMED
        pothole.confirmed_at = datetime.utcnow()
        logger.info(f"Pothole {pothole.id} CONFIRMED ({pothole.report_count} reports, dual={dual_confirmed})")

    pothole.updated_at = datetime.utcnow()
    db.add(pothole)
    await db.flush()

    just_confirmed = (not was_confirmed) and (pothole.status == PotholeStatus.CONFIRMED)
    return pothole, just_confirmed


async def deduplicate_nearby_candidates(
    pothole: Pothole, db: AsyncSession
) -> int:
    """
    After a pothole is confirmed, merge any nearby candidates into it.
    Returns number of merged candidates.
    """
    result = await db.execute(
        text("""
            SELECT id, report_count FROM potholes
            WHERE ST_DWithin(
                location::geography,
                ST_MakePoint(:lon, :lat)::geography,
                :radius
            )
            AND status = 'candidate'
            AND id != :pid
        """),
        {"lat": pothole.avg_lat, "lon": pothole.avg_lon,
         "radius": settings.CLUSTER_RADIUS_METERS, "pid": pothole.id}
    )
    duplicates = result.fetchall()
    merged = 0

    for dup_id, dup_count in duplicates:
        # Re-parent reports from duplicate to this pothole
        await db.execute(
            text("UPDATE pothole_reports SET pothole_id = :new_id WHERE pothole_id = :old_id"),
            {"new_id": pothole.id, "old_id": dup_id}
        )
        # Delete duplicate pothole
        await db.execute(text("DELETE FROM potholes WHERE id = :id"), {"id": dup_id})
        pothole.report_count += dup_count
        merged += 1
        logger.info(f"Merged duplicate pothole {dup_id} into {pothole.id}")

    if merged:
        db.add(pothole)
        await db.flush()

    return merged