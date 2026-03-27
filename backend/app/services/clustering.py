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
            AND status NOT IN ('REPAIRED', 'FRAUD')
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
    from app.models.pothole import Severity as PotholeSeverity
    
    # Convert severity string to enum
    severity_enum = PotholeSeverity.S1
    if severity == "S2":
        severity_enum = PotholeSeverity.S2
    elif severity == "S3":
        severity_enum = PotholeSeverity.S3
    
    pothole = Pothole(
        id=str(uuid.uuid4()),
        location=make_point_wkt(lat, lon),
        severity=severity_enum,
        status=PotholeStatus.CANDIDATE,
        report_count=1,
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
    # Check current status via raw SQL
    status_result = await db.execute(
        text("SELECT status FROM potholes WHERE id = :id"),
        {"id": pothole.id}
    )
    status_row = status_result.fetchone()
    current_status = status_row[0] if status_row else "candidate"
    was_confirmed = current_status == "CONFIRMED"
    
    # Get current counts
    count_result = await db.execute(
        text("SELECT report_count FROM potholes WHERE id = :id"),
        {"id": pothole.id}
    )
    count_row = count_result.fetchone()
    current_count = count_row[0] if count_row else 0
    
    # Determine what to add
    method = report.detection_method
    cam_add = 1 if method in ("camera", "both") else 0
    sens_add = 1 if method in ("sensor", "both") else 0
    
    # Update via raw SQL
    await db.execute(
        text("""
            UPDATE potholes 
            SET report_count = COALESCE(report_count, 0) + 1,
                camera_confirmed = COALESCE(camera_confirmed, 0) + :cam_add,
                sensor_confirmed = COALESCE(sensor_confirmed, 0) + :sens_add,
                updated_at = NOW()
            WHERE id = :id
        """),
        {"cam_add": cam_add, "sens_add": sens_add, "id": pothole.id}
    )

    # Check if should be confirmed
    new_count = current_count + 1
    if new_count >= settings.CONFIRMED_THRESHOLD and not was_confirmed:
        await db.execute(
            text("UPDATE potholes SET status = 'CONFIRMED' WHERE id = :id"),
            {"id": pothole.id}
        )
        logger.info(f"Pothole {pothole.id} CONFIRMED ({new_count} reports)")
        just_confirmed = True
    else:
        just_confirmed = False

    await db.flush()
    return pothole, just_confirmed


async def deduplicate_nearby_candidates(
    pothole: Pothole, db: AsyncSession
) -> int:
    """
    After a pothole is confirmed, merge any nearby candidates into it.
    Returns number of merged candidates.
    """
    # Get the pothole's location
    loc_result = await db.execute(
        text("SELECT ST_X(location), ST_Y(location) FROM potholes WHERE id = :id"),
        {"id": pothole.id}
    )
    loc_row = loc_result.fetchone()
    if not loc_row:
        return 0
    pothole_lon, pothole_lat = loc_row[0], loc_row[1]
    
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
        {"lat": pothole_lat, "lon": pothole_lon,
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