from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from app.services.audit_service import AuditService
from fastapi import Form
from fastapi import Body
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional, Dict, Any
import uuid
import qrcode
from io import BytesIO
import base64
from datetime import datetime
import os
import shutil

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.sample import Sample, SampleStatus, SampleType, CustodyScan
from app.schemas.sample import (
    SampleCreate, SampleUpdate, SampleResponse,
    SampleListResponse, CustodyScanCreate, CustodyScanResponse
)
from app.core.config import settings

router = APIRouter()

# ==================== HELPER FUNCTIONS ====================

def generate_sample_id() -> str:
    """Generate a unique sample ID"""
    return f"SMP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

def generate_qr_code(sample_id: str) -> str:
    """Generate QR code as base64 string"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(sample_id)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

# ==================== SAMPLE CRUD ====================

@router.post("/", response_model=SampleResponse, status_code=status.HTTP_201_CREATED)
async def create_sample(
    sample_data: SampleCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None
):
    """Create a new sample"""
    sample_id = generate_sample_id()
    qr_code = generate_qr_code(sample_id)
    
    sample = Sample(
        sample_id=sample_id,
        qr_code=qr_code[:100],
        mill_id=sample_data.mill_id,
        collection_point=sample_data.collection_point,
        sample_type=sample_data.sample_type,
        description=sample_data.description,
        latitude=sample_data.latitude,
        longitude=sample_data.longitude,
        metadata_json=sample_data.metadata_json,
        created_by_id=current_user.id,
        status=SampleStatus.COLLECTED
    )
    
    db.add(sample)
    await db.commit()
    await db.refresh(sample)
    
    # Log the action
    audit_service = AuditService(db)
    await audit_service.log_action(
        user_id=current_user.id,
        action="CREATE",
        resource="sample",
        resource_id=sample.sample_id,
        changes={"sample_data": sample_data.model_dump()},
        request=request
    )
    
    return sample
@router.get("/", response_model=SampleListResponse)
async def get_samples(
    skip: int = 0,
    limit: int = 20,
    mill_id: Optional[int] = None,
    sample_type: Optional[SampleType] = None,
    status: Optional[SampleStatus] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get samples with filtering"""
    query = select(Sample)
    
    if mill_id:
        query = query.where(Sample.mill_id == mill_id)
    if sample_type:
        query = query.where(Sample.sample_type == sample_type)
    if status:
        query = query.where(Sample.status == status)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.offset(skip).limit(limit).order_by(Sample.created_at.desc())
    result = await db.execute(query)
    samples = result.scalars().all()
    
    total_pages = (total + limit - 1) // limit if limit > 0 else 1
    
    return {
        "items": samples,
        "total": total or 0,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "page_size": limit,
        "total_pages": total_pages
    }

@router.get("/{sample_id}", response_model=SampleResponse)
async def get_sample(
    sample_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific sample by ID"""
    result = await db.execute(
        select(Sample).where(Sample.sample_id == sample_id)
    )
    sample = result.scalar_one_or_none()
    
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sample not found"
        )
    
    return sample

@router.patch("/{sample_id}", response_model=SampleResponse)
async def update_sample(
    sample_id: str,
    sample_update: SampleUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a sample"""
    result = await db.execute(
        select(Sample).where(Sample.sample_id == sample_id)
    )
    sample = result.scalar_one_or_none()
    
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sample not found"
        )
    
    for field, value in sample_update.model_dump(exclude_unset=True).items():
        setattr(sample, field, value)
    
    await db.commit()
    await db.refresh(sample)
    
    return sample

@router.delete("/{sample_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sample(
    sample_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a sample (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete samples"
        )
    
    result = await db.execute(
        select(Sample).where(Sample.sample_id == sample_id)
    )
    sample = result.scalar_one_or_none()
    
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sample not found"
        )
    
    await db.delete(sample)
    await db.commit()
    
    return None

# ==================== PHOTO UPLOAD ====================

@router.post("/{sample_id}/upload-photo")
async def upload_sample_photo(
    sample_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload a photo for a sample"""
    result = await db.execute(
        select(Sample).where(Sample.sample_id == sample_id)
    )
    sample = result.scalar_one_or_none()
    
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sample not found"
        )
    
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image"
        )
    
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > settings.MAX_PHOTO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Max size: {settings.MAX_PHOTO_SIZE // 1024 // 1024}MB"
        )
    
    file_extension = file.filename.split('.')[-1] if file.filename and '.' in file.filename else 'jpg'
    filename = f"{sample_id}.{file_extension}"
    file_path = os.path.join(settings.UPLOAD_DIR, filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    
    sample.photo_url = f"/uploads/photos/{filename}"
    await db.commit()
    await db.refresh(sample)
    
    return {
        "message": "Photo uploaded successfully",
        "photo_url": sample.photo_url,
        "sample_id": sample.sample_id
    }

# ==================== CUSTODY SCANS ====================

@router.post("/{sample_id}/scan", response_model=CustodyScanResponse)
async def add_custody_scan(
    sample_id: str,
    scan_data: CustodyScanCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a custody scan event (pickup, dropoff, check_in)"""
    result = await db.execute(
        select(Sample).where(Sample.sample_id == sample_id)
    )
    sample = result.scalar_one_or_none()
    
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sample not found"
        )
    
    valid_scan_types = ["pickup", "dropoff", "check_in"]
    if scan_data.scan_type not in valid_scan_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scan type. Must be one of: {', '.join(valid_scan_types)}"
        )
    
    scan = CustodyScan(
        sample_id=sample.id,
        scanned_by_id=current_user.id,
        scan_type=scan_data.scan_type,
        location=scan_data.location,
        latitude=scan_data.latitude,
        longitude=scan_data.longitude,
        notes=scan_data.notes
    )
    
    if scan_data.scan_type == "pickup":
        sample.status = SampleStatus.IN_TRANSIT
        sample.pickup_at = datetime.utcnow()
    elif scan_data.scan_type == "dropoff":
        sample.status = SampleStatus.RECEIVED_AT_LAB
        sample.received_at_lab = datetime.utcnow()
    elif scan_data.scan_type == "check_in":
        sample.status = SampleStatus.PROCESSING
    
    db.add(scan)
    await db.commit()
    await db.refresh(scan)
    
    return scan

@router.get("/{sample_id}/scans", response_model=List[CustodyScanResponse])
async def get_sample_scans(
    sample_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all custody scans for a sample"""
    result = await db.execute(
        select(Sample).where(Sample.sample_id == sample_id)
    )
    sample = result.scalar_one_or_none()
    
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sample not found"
        )
    
    result = await db.execute(
        select(CustodyScan)
        .where(CustodyScan.sample_id == sample.id)
        .order_by(CustodyScan.scanned_at.desc())
    )
    scans = result.scalars().all()
    
    return scans

# ==================== LAB RESULTS ====================

from fastapi import Form

@router.post("/{sample_id}/results", response_model=SampleResponse)
async def add_lab_results(
    sample_id: str,
    moisture: Optional[str] = Form(None),
    protein: Optional[str] = Form(None),
    ph: Optional[str] = Form(None),
    temperature: Optional[str] = Form(None),
    quality_grade: Optional[str] = Form(None),
    result_notes: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Add lab results to a sample using form data"""
    if current_user.role not in ["lab_tech", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only lab technicians and admins can add results"
        )
    
    result = await db.execute(
        select(Sample).where(Sample.sample_id == sample_id)
    )
    sample = result.scalar_one_or_none()
    
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sample not found"
        )
    
    # Build result_data dictionary from form fields
    result_data = {}
    if moisture:
        result_data["moisture"] = moisture
    if protein:
        result_data["protein"] = protein
    if ph:
        result_data["ph"] = ph
    if temperature:
        result_data["temperature"] = temperature
    if quality_grade:
        result_data["quality_grade"] = quality_grade
    
    sample.result_data = result_data
    if result_notes:
        sample.result_notes = result_notes
    sample.status = SampleStatus.COMPLETED
    sample.processed_at = datetime.utcnow()
    sample.processed_by_id = current_user.id
    
    await db.commit()
    await db.refresh(sample)
    
    return sample
# ==================== QR CODE ====================

@router.get("/{sample_id}/qr-code")
async def get_sample_qr_code(
    sample_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get QR code for a sample as base64 image"""
    result = await db.execute(
        select(Sample).where(Sample.sample_id == sample_id)
    )
    sample = result.scalar_one_or_none()
    
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sample not found"
        )
    
    qr_base64 = generate_qr_code(sample_id)
    
    return {
        "sample_id": sample_id,
        "qr_code_base64": qr_base64,
        "qr_code_data": sample.qr_code
    }