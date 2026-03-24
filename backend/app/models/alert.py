from sqlalchemy import Column, String, DateTime, Enum, Boolean
from datetime import datetime
import enum
import uuid

from app.models.base import Base


class AlertType(str, enum.Enum):
    POTHOLES_DETECTED = "potholes_detected"
    ROAD_DAMAGE = "road_damage"
    REPAIR_COMPLETED = "repair_completed"
    EMERGENCY = "emergency"


class AlertPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    rider_id = Column(String, nullable=True)
    pothole_id = Column(String, nullable=True)
    contractor_id = Column(String, nullable=True)

    alert_type = Column(Enum(AlertType), nullable=False)
    priority = Column(Enum(AlertPriority), default=AlertPriority.MEDIUM)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)

    is_read = Column(Boolean, default=False)
    is_resolved = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
