from sqlalchemy import Column, Integer, String, DateTime, Enum, Text, Float, ForeignKey, JSON, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base

class SampleStatus(str, enum.Enum):
    COLLECTED = "collected"
    IN_TRANSIT = "in_transit"
    RECEIVED_AT_LAB = "received_at_lab"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FLAGGED = "flagged"
    REJECTED = "rejected"

class SampleType(str, enum.Enum):
    RAW_MATERIAL = "raw_material"
    FINISHED_PRODUCT = "finished_product"
    IN_PROCESS = "in_process"
    ENVIRONMENTAL = "environmental"
    OTHER = "other"

class Sample(Base):
    __tablename__ = "samples"
    
    id = Column(Integer, primary_key=True, index=True)
    qr_code = Column(String(100), unique=True, index=True, nullable=False)
    sample_id = Column(String(50), unique=True, index=True, nullable=False)
    
    # Collection info
    mill_id = Column(Integer, nullable=False)
    collection_point = Column(String(200), nullable=True)
    sample_type = Column(Enum(SampleType), nullable=False)
    description = Column(Text, nullable=True)
    
    # Photos
    photo_url = Column(String(500), nullable=True)
    
    # Location
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    # Status
    status = Column(Enum(SampleStatus), default=SampleStatus.COLLECTED)
    
    # Custody chain
    collected_at = Column(DateTime(timezone=True), server_default=func.now())
    pickup_at = Column(DateTime(timezone=True), nullable=True)
    received_at_lab = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Users
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    processed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Lab results
    result_data = Column(JSON, nullable=True)
    result_notes = Column(Text, nullable=True)
    
    # Anomaly flags
    is_anomaly = Column(Boolean, default=False)
    anomaly_reasons = Column(JSON, nullable=True)
    
    # Metadata
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    creator = relationship("User", foreign_keys=[created_by_id], back_populates="samples_created")
    processor = relationship("User", foreign_keys=[processed_by_id], back_populates="samples_processed")
    scans = relationship("CustodyScan", back_populates="sample")

class CustodyScan(Base):
    __tablename__ = "custody_scans"
    
    id = Column(Integer, primary_key=True, index=True)
    sample_id = Column(Integer, ForeignKey("samples.id"), nullable=False)
    scanned_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    scan_type = Column(String(50), nullable=False)
    location = Column(String(200), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    scanned_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    sample = relationship("Sample", back_populates="scans")
    scanned_by = relationship("User")