"""
PostGIS helper utilities used across services.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional


async def potholes_in_bbox(
    min_lat: float, min_lon: float,
    max_lat: float, max_lon: float,
    db: AsyncSession,
    status_filter: Optional[list] = None,
    limit: int = 500,
) -> list:
    statuses = status_filter or ["candidate", "confirmed"]
    placeholders = ", ".join(f"'{s}'" for s in statuses)

    result = await db.execute(
        text(f"""
            SELECT
                id,
                ST_Y(location::geometry) as latitude,
                ST_X(location::geometry) as longitude,
                severity,
                status,
                report_count,
                water_filled,
                estimated_damage_inr,
                contractor_id,
                created_at
            FROM potholes
            WHERE status IN ({placeholders})
              AND ST_Within(
                    location::geometry,
                    ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
                  )
            ORDER BY report_count DESC
            LIMIT :limit
        """),
        {
            "min_lat": min_lat, "min_lon": min_lon,
            "max_lat": max_lat, "max_lon": max_lon,
            "limit": limit,
        },
    )
    return result.mappings().fetchall()


async def count_potholes_near(lat: float, lon: float, radius_meters: float, db: AsyncSession) -> int:
    result = await db.execute(
        text("""
            SELECT COUNT(*) FROM potholes
            WHERE ST_DWithin(
                location::geography,
                ST_MakePoint(:lon, :lat)::geography,
                :radius
            ) AND status IN ('candidate', 'confirmed')
        """),
        {"lat": lat, "lon": lon, "radius": radius_meters},
    )
    return result.scalar() or 0


async def find_potholes_within_radius(
    lat: float,
    lon: float,
    radius_meters: float,
    db: AsyncSession,
    status_filter: Optional[list] = None,
) -> list:
    """
    Find all potholes within a given radius from a point.
    Returns a list of pothole records with distance.
    """
    statuses = status_filter or ["candidate", "confirmed"]
    placeholders = ", ".join(f"'{s}'" for s in statuses)

    result = await db.execute(
        text(f"""
            SELECT
                id,
                ST_Y(location::geometry) as latitude,
                ST_X(location::geometry) as longitude,
                severity,
                status,
                report_count,
                water_filled,
                estimated_damage_inr,
                contractor_id,
                ST_Distance(
                    location::geography,
                    ST_MakePoint(:lon, :lat)::geography
                ) AS distance_meters,
                created_at
            FROM potholes
            WHERE status IN ({placeholders})
            AND ST_DWithin(
                location::geography,
                ST_MakePoint(:lon, :lat)::geography,
                :radius
            )
            ORDER BY distance_meters
        """),
        {"lat": lat, "lon": lon, "radius": radius_meters},
    )
    return result.mappings().fetchall()


def make_point_wkt(lat: float, lon: float) -> str:
    """Create a WKT point string from lat/lon coordinates."""
    return f"SRID=4326;POINT({lon} {lat})"


async def cluster_centroid(pothole_ids: list, db: AsyncSession) -> Optional[tuple[float, float]]:
    """
    Calculate the weighted centroid of a cluster of potholes.
    Returns (lat, lon) tuple or None if no valid centroid.
    """
    if not pothole_ids:
        return None
    
    placeholders = ", ".join(f":id{i}" for i in range(len(pothole_ids)))
    params = {f"id{i}": pid for i, pid in enumerate(pothole_ids)}
    
    result = await db.execute(
        text(f"""
            SELECT 
                ST_Y(ST_Centroid(ST_Collect(location))) as centroid_lat,
                ST_X(ST_Centroid(ST_Collect(location))) as centroid_lon
            FROM potholes
            WHERE id IN ({placeholders})
        """),
        params,
    )
    row = result.fetchone()
    if row and row[0] and row[1]:
        return float(row[0]), float(row[1])
    return None
