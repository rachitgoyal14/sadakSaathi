"""
Contractors Router — Accountability Engine API
GET    /api/v1/contractors/                  — list all contractors
POST   /api/v1/contractors/                  — create contractor (admin)
GET    /api/v1/contractors/{id}              — contractor detail + stats
GET    /api/v1/contractors/{id}/potholes     — potholes linked to contractor
GET    /api/v1/contractors/{id}/damage       — damage report
POST   /api/v1/contractors/claims            — submit repair claim
GET    /api/v1/contractors/claims/{id}       — claim status
GET    /api/v1/contractors/leaderboard       — performance ranking
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.dependencies import get_db, get_current_admin
from app.schemas.schemas import (
    ContractorCreate, ContractorOut, DamageReport,
    RepairClaimCreate, RepairClaimOut, LeaderboardEntry
)
from app.models.contractor import Contractor, RepairClaim
from app.models.pothole import Pothole, PotholeStatus
from app.services.accountability import get_contractor_dashboard

router = APIRouter(prefix="/contractors", tags=["accountability"])


@router.get("/leaderboard", response_model=List[LeaderboardEntry])
async def get_leaderboard(
    city: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Contractor performance ranking — lower score = worse performance.
    This is the public accountability view.
    """
    city_filter = "WHERE c.city ILIKE :city" if city else ""
    params = {"limit": limit}
    if city:
        params["city"] = f"%{city}%"

    result = await db.execute(
        text(f"""
            SELECT
                c.id as contractor_id,
                c.name as contractor_name,
                c.performance_score,
                c.total_damage_inr,
                c.total_potholes_caused as potholes_caused,
                c.total_potholes_repaired as potholes_repaired,
                c.fraud_attempts,
                ROW_NUMBER() OVER (ORDER BY c.performance_score ASC) as rank
            FROM contractors c
            {city_filter}
            ORDER BY c.performance_score ASC
            LIMIT :limit
        """),
        params,
    )
    rows = result.mappings().fetchall()
    return [LeaderboardEntry(**dict(r)) for r in rows]


@router.get("/", response_model=List[ContractorOut])
async def list_contractors(
    city: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    filters = ["1=1"]
    params: dict = {"limit": limit}
    if city:
        filters.append("city ILIKE :city"); params["city"] = f"%{city}%"
    if status:
        filters.append("status = :status"); params["status"] = status

    result = await db.execute(
        text(f"SELECT * FROM contractors WHERE {' AND '.join(filters)} ORDER BY performance_score ASC LIMIT :limit"),
        params,
    )
    rows = result.mappings().fetchall()
    return [ContractorOut(**dict(r)) for r in rows]


@router.post("/", response_model=ContractorOut, status_code=201)
async def create_contractor(
    payload: ContractorCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    existing = await db.execute(
        text("SELECT id FROM contractors WHERE registration_number = :reg"),
        {"reg": payload.registration_number}
    )
    if existing.fetchone():
        raise HTTPException(status_code=400, detail="Registration number already exists")

    contractor = Contractor(
        id=str(uuid.uuid4()),
        name=payload.name,
        registration_number=payload.registration_number,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        city=payload.city,
    )
    db.add(contractor)
    await db.commit()
    await db.refresh(contractor)
    return ContractorOut.model_validate(contractor)


@router.get("/{contractor_id}", response_model=dict)
async def get_contractor(contractor_id: str, db: AsyncSession = Depends(get_db)):
    dashboard = await get_contractor_dashboard(contractor_id, db)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Contractor not found")
    return dashboard


@router.get("/{contractor_id}/potholes", response_model=List[DamageReport])
async def get_contractor_potholes(
    contractor_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    status_filter = "AND p.status = :status" if status else ""
    params = {"cid": contractor_id, "limit": limit}
    if status:
        params["status"] = status

    result = await db.execute(
        text(f"""
            SELECT
                p.id as pothole_id,
                p.contractor_id,
                c.name as contractor_name,
                rs.name as road_segment,
                rs.is_under_warranty as under_warranty,
                p.days_unrepaired,
                p.estimated_damage_inr,
                p.severity,
                p.report_count
            FROM potholes p
            LEFT JOIN contractors c ON c.id = p.contractor_id
            LEFT JOIN road_segments rs ON rs.id = p.road_segment_id
            WHERE p.contractor_id = :cid {status_filter}
            ORDER BY p.estimated_damage_inr DESC
            LIMIT :limit
        """),
        params,
    )
    rows = result.mappings().fetchall()
    return [DamageReport(**dict(r)) for r in rows]


@router.post("/claims", response_model=RepairClaimOut, status_code=201)
async def submit_repair_claim(
    payload: RepairClaimCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Contractor submits a repair claim for a pothole.
    Triggers satellite verification in the background.
    Payment is blocked until verification passes.
    """
    pothole = await db.get(Pothole, payload.pothole_id)
    if not pothole:
        raise HTTPException(status_code=404, detail="Pothole not found")
    if pothole.status == PotholeStatus.REPAIRED:
        raise HTTPException(status_code=400, detail="Pothole already verified as repaired")

    claim = RepairClaim(
        id=str(uuid.uuid4()),
        pothole_id=payload.pothole_id,
        contractor_id=payload.contractor_id,
        verification_notes=payload.notes,
    )
    db.add(claim)

    # Mark pothole as claim pending
    pothole.status = PotholeStatus.REPAIR_CLAIMED
    db.add(pothole)
    await db.commit()
    await db.refresh(claim)

    # Dispatch satellite verification (async — may take minutes)
    background_tasks.add_task(_verify_repair_claim, claim.id, pothole.avg_lat, pothole.avg_lon)

    return RepairClaimOut.model_validate(claim)


@router.get("/claims/{claim_id}", response_model=RepairClaimOut)
async def get_claim_status(claim_id: str, db: AsyncSession = Depends(get_db)):
    claim = await db.get(RepairClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return RepairClaimOut.model_validate(claim)


@router.patch("/{contractor_id}/suspend")
async def suspend_contractor(
    contractor_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    contractor = await db.get(Contractor, contractor_id)
    if not contractor:
        raise HTTPException(status_code=404, detail="Not found")
    contractor.status = "suspended"
    db.add(contractor)
    await db.commit()
    return {"status": "suspended", "contractor_id": contractor_id}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _verify_repair_claim(claim_id: str, lat: float, lon: float):
    """Background task: run satellite verification then process outcome."""
    from app.db.session import AsyncSessionLocal
    from app.services.satellite_verify import verify_pothole_repair
    from app.services.accountability import process_repair_claim
    from datetime import datetime

    async with AsyncSessionLocal() as db:
        claim = await db.get(RepairClaim, claim_id)
        if not claim:
            return

    result = await verify_pothole_repair(
        pothole_id=claim.pothole_id,
        lat=lat, lon=lon,
        reported_repaired_at=claim.claimed_at,
    )

    async with AsyncSessionLocal() as db:
        claim = await db.get(RepairClaim, claim_id)
        if claim:
            claim.is_verified = result.repaired
            claim.verified_at = datetime.utcnow()
            claim.satellite_confidence = result.confidence
            claim.verification_notes = result.notes
            db.add(claim)
            await db.commit()

    await process_repair_claim(claim_id, result.repaired, result.confidence)