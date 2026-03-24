"""initial

Revision ID: a32fd9897fc9
Revises: 
Create Date: 2026-03-25 02:02:55.117532

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a32fd9897fc9'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('alerts',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('rider_id', sa.String(), nullable=True),
    sa.Column('pothole_id', sa.String(), nullable=True),
    sa.Column('contractor_id', sa.String(), nullable=True),
    sa.Column('alert_type', sa.String(), nullable=False),
    sa.Column('priority', sa.String(), nullable=True),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('message', sa.String(), nullable=False),
    sa.Column('is_read', sa.Boolean(), nullable=True),
    sa.Column('is_resolved', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('contractors',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('name', sa.String(length=256), nullable=False),
    sa.Column('registration_number', sa.String(length=100), nullable=False),
    sa.Column('contact_email', sa.String(length=256), nullable=True),
    sa.Column('contact_phone', sa.String(length=20), nullable=True),
    sa.Column('performance_score', sa.Float(), nullable=True),
    sa.Column('warranty_violations', sa.Integer(), nullable=True),
    sa.Column('fraud_claims', sa.Integer(), nullable=True),
    sa.Column('verified_repairs', sa.Integer(), nullable=True),
    sa.Column('total_potholes_on_record', sa.Integer(), nullable=True),
    sa.Column('total_estimated_damage_inr', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('registration_number')
    )
    
    op.create_table('riders',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('email', sa.String(length=256), nullable=False),
    sa.Column('hashed_password', sa.String(length=256), nullable=False),
    sa.Column('full_name', sa.String(length=256), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('is_admin', sa.Boolean(), nullable=True),
    sa.Column('platform', sa.String(length=100), nullable=True),
    sa.Column('last_lat', sa.Float(), nullable=True),
    sa.Column('last_lon', sa.Float(), nullable=True),
    sa.Column('last_seen', sa.DateTime(), nullable=True),
    sa.Column('total_reports', sa.Integer(), nullable=True),
    sa.Column('confirmed_reports', sa.Integer(), nullable=True),
    sa.Column('accuracy_score', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    
    op.create_table('road_segments',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('name', sa.String(length=512), nullable=True),
    sa.Column('boundary', sa.String(), nullable=True),
    sa.Column('contractor_id', sa.String(), nullable=False),
    sa.Column('construction_date', sa.DateTime(), nullable=True),
    sa.Column('warranty_expiry', sa.DateTime(), nullable=True),
    sa.Column('road_type', sa.String(length=50), nullable=True),
    sa.ForeignKeyConstraint(['contractor_id'], ['contractors.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('potholes',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('avg_lat', sa.Float(), nullable=True),
    sa.Column('avg_lon', sa.Float(), nullable=True),
    sa.Column('severity', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('report_count', sa.Integer(), nullable=True),
    sa.Column('camera_confirmed', sa.Integer(), nullable=True),
    sa.Column('sensor_confirmed', sa.Integer(), nullable=True),
    sa.Column('water_filled', sa.Integer(), nullable=True),
    sa.Column('pothole_type', sa.String(), nullable=True),
    sa.Column('contractor_id', sa.String(), nullable=True),
    sa.Column('road_segment_id', sa.String(), nullable=True),
    sa.Column('estimated_damage_inr', sa.Float(), nullable=True),
    sa.Column('high_confidence_count', sa.Integer(), nullable=True),
    sa.Column('city', sa.String(), nullable=True),
    sa.Column('address', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('repaired_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['contractor_id'], ['contractors.id'], ),
    sa.ForeignKeyConstraint(['road_segment_id'], ['road_segments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('pothole_reports',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('pothole_id', sa.String(), nullable=True),
    sa.Column('rider_id', sa.String(), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('severity', sa.String(), nullable=True),
    sa.Column('detection_method', sa.String(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('image_s3_key', sa.String(), nullable=True),
    sa.Column('pothole_type', sa.String(), nullable=True),
    sa.Column('yolo_bbox', sa.String(), nullable=True),
    sa.Column('rider_weight', sa.Float(), nullable=True),
    sa.Column('speed_kmh', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['pothole_id'], ['potholes.id'], ),
    sa.ForeignKeyConstraint(['rider_id'], ['riders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('repair_claims',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('pothole_id', sa.String(), nullable=False),
    sa.Column('contractor_id', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('claimed_at', sa.DateTime(), nullable=True),
    sa.Column('verified_at', sa.DateTime(), nullable=True),
    sa.Column('verification_confidence', sa.Float(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('proof_image_s3_key', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['contractor_id'], ['contractors.id'], ),
    sa.ForeignKeyConstraint(['pothole_id'], ['potholes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('repair_claims')
    op.drop_table('pothole_reports')
    op.drop_table('potholes')
    op.drop_table('road_segments')
    op.drop_table('riders')
    op.drop_table('contractors')
    op.drop_table('alerts')
