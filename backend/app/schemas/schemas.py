from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ─── Enums ───────────────────────────────────────────────────────────────────

class DetectionMethod(str, Enum):
    camera = "camera"
    sensor = "sensor"
    both = "both"

class SeverityEnum(str, Enum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"

class PotholeTypeEnum(str, Enum):
    dry = "dry"
    water_filled = "water_filled"
    debris = "debris"


# ─── Detection ────────────────────────────────────────────────────────────────

class AccelerometerReading(BaseModel):
    x: float = Field(..., description="X-axis acceleration (m/s²)")
    y: float = Field(..., description="Y-axis acceleration (m/s²)")
    z: float = Field(..., description="Z-axis acceleration (m/s²)")
    timestamp_ms: float = Field(..., description="Unix timestamp in milliseconds")


class SensorWindow(BaseModel):
    readings: List[AccelerometerReading] = Field(..., description="List of readings over 1-2 seconds (~50Hz)")
    avg_speed_kmh: float = Field(0.0, ge=0, description="Average speed during this window")
    road_condition: Optional[str] = Field(None, description="User-reported condition: smooth/bumpy/very_bumpy")


class LocationData(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy_meters: Optional[float] = Field(None, ge=0, description="GPS accuracy in meters")
    altitude_meters: Optional[float] = None
    heading_degrees: Optional[float] = Field(None, ge=0, le=360)
    timestamp_ms: float = Field(..., description="Unix timestamp in milliseconds")


class DeviceInfo(BaseModel):
    device_id: Optional[str] = None
    device_model: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = "1.0.0"
    camera_resolution: Optional[str] = None
    is_5g_available: Optional[bool] = False


class RideContext(BaseModel):
    ride_id: Optional[str] = Field(None, description="UUID for the ride session")
    is_night_mode: bool = Field(False, description="Whether it's night time")
    weather_condition: Optional[str] = Field(None, description="clear/rain/fog/haze")
    road_type: Optional[str] = Field(None, description="highway/main_road/side_street")


class MobileDetectionPayload(BaseModel):
    rider_id: str
    location: LocationData
    speed_kmh: float = Field(..., ge=0, le=200, description="Current speed from GPS")
    sensor_window: Optional[SensorWindow] = None
    device_info: Optional[DeviceInfo] = None
    ride_context: Optional[RideContext] = None
    frame_timestamp_ms: float = Field(..., description="Video frame timestamp")
    video_segment_id: Optional[str] = None


class DetectionResponse(BaseModel):
    pothole_id: str
    status: str
    report_count: int
    severity: str
    message: str
    yolo_confidence: Optional[float] = None
    lstm_severity: Optional[str] = None
    fused_confidence: Optional[float] = None


# ─── Pothole ──────────────────────────────────────────────────────────────────

class HazardMapItem(BaseModel):
    id: str
    latitude: float
    longitude: float
    severity: str
    status: str
    pothole_type: str
    report_count: int
    camera_confirmed: int
    sensor_confirmed: int
    estimated_damage_inr: float
    contractor_name: Optional[str] = None
    days_unrepaired: int
    created_at: datetime

    class Config:
        from_attributes = True


class PotholeDetail(HazardMapItem):
    address: Optional[str]
    high_confidence_count: int
    best_image_url: Optional[str] = None
    road_segment_name: Optional[str] = None


# ─── Rider ────────────────────────────────────────────────────────────────────

class RiderCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    password: str = Field(..., min_length=6)
    platform: Optional[str] = None


class RiderLogin(BaseModel):
    phone: str
    password: str


class RiderOut(BaseModel):
    id: str
    name: str = Field(..., alias="full_name")
    phone: str
    email: Optional[str] = None
    platform: Optional[str] = None
    total_reports: float = 0
    accuracy_score: float = 100.0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        populate_by_name = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rider: RiderOut


# ─── Alerts ──────────────────────────────────────────────────────────────────

class AlertMessage(BaseModel):
    event: str = "pothole_alert"
    pothole_id: str
    latitude: float
    longitude: float
    severity: str
    pothole_type: str
    distance_meters: float
    message: str


class LocationUpdate(BaseModel):
    rider_id: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    speed_kmh: Optional[float] = None


# ─── Routes ──────────────────────────────────────────────────────────────────

class RoutePoint(BaseModel):
    latitude: float
    longitude: float


class RouteRequest(BaseModel):
    origin: RoutePoint
    destination: RoutePoint
    rider_id: Optional[str] = None


class RouteOption(BaseModel):
    type: str                       # "fastest" | "safest"
    distance_km: float
    estimated_time_minutes: float
    pothole_count: int
    pothole_severity_score: float   # 0-100, lower is better
    waypoints: List[RoutePoint]
    description: str


class RouteResponse(BaseModel):
    fastest: RouteOption
    safest: RouteOption
    recommended: str                # "fastest" | "safest"


# ─── Contractor ──────────────────────────────────────────────────────────────

class ContractorCreate(BaseModel):
    name: str
    registration_number: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    city: str


class ContractorOut(BaseModel):
    id: str
    name: str
    registration_number: str
    city: str
    status: str
    performance_score: float
    total_potholes_caused: int
    total_potholes_repaired: int
    total_damage_inr: float
    payment_withheld_inr: float
    fraud_attempts: int
    created_at: datetime

    class Config:
        from_attributes = True


class DamageReport(BaseModel):
    pothole_id: str
    contractor_id: Optional[str]
    contractor_name: Optional[str]
    road_segment: Optional[str]
    under_warranty: bool
    days_unrepaired: int
    estimated_damage_inr: float
    severity: str
    report_count: int


class RepairClaimCreate(BaseModel):
    pothole_id: str
    contractor_id: str
    notes: Optional[str] = None


class RepairClaimOut(BaseModel):
    id: str
    pothole_id: str
    contractor_id: str
    claimed_at: datetime
    is_verified: Optional[bool]
    payment_released: bool
    satellite_confidence: Optional[float]
    verification_notes: Optional[str]

    class Config:
        from_attributes = True


# ─── Stats / Dashboard ────────────────────────────────────────────────────────

class CityStats(BaseModel):
    city: str
    total_potholes: int
    confirmed_potholes: int
    repaired_potholes: int
    total_damage_inr: float
    active_riders: int
    top_problematic_road: Optional[str]


class LeaderboardEntry(BaseModel):
    rank: int
    contractor_id: str
    contractor_name: str
    performance_score: float
    total_damage_inr: float
    potholes_caused: int
    potholes_repaired: int
    fraud_attempts: int