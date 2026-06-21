from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models.sample import SampleStatus, SampleType

class SampleBase(BaseModel):
    mill_id: int
    collection_point: Optional[str] = None
    sample_type: SampleType
    description: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    metadata_json: Optional[Dict[str, Any]] = None

class SampleCreate(SampleBase):
    pass

class SampleUpdate(BaseModel):
    collection_point: Optional[str] = None
    description: Optional[str] = None
    status: Optional[SampleStatus] = None
    result_data: Optional[Dict[str, Any]] = None
    result_notes: Optional[str] = None
    is_anomaly: Optional[bool] = None
    anomaly_reasons: Optional[List[str]] = None

class SampleResponse(SampleBase):
    id: int
    sample_id: str
    qr_code: str
    photo_url: Optional[str] = None
    status: SampleStatus
    collected_at: datetime
    pickup_at: Optional[datetime] = None
    received_at_lab: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    created_by_id: int
    processed_by_id: Optional[int] = None
    result_data: Optional[Dict[str, Any]] = None
    result_notes: Optional[str] = None
    is_anomaly: bool
    anomaly_reasons: Optional[List[str]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class SampleListResponse(BaseModel):
    items: List[SampleResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

class CustodyScanCreate(BaseModel):
    scan_type: str  # 'pickup', 'dropoff', 'check_in'
    location: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    notes: Optional[str] = None

class CustodyScanResponse(BaseModel):
    id: int
    sample_id: int
    scanned_by_id: int
    scan_type: str
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = None
    scanned_at: datetime
    
    model_config = ConfigDict(from_attributes=True)