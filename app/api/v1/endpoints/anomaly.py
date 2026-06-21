from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.sample import Sample
from app.models.anomaly import AnomalyRule, AnomalyAlert
from app.services.anomaly_detection import AnomalyDetectionService

router = APIRouter()

@router.post("/samples/{sample_id}/check")
async def check_sample_anomalies(
    sample_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Check a sample for anomalies"""
    # Get sample
    from sqlalchemy import select
    result = await db.execute(
        select(Sample).where(Sample.sample_id == sample_id)
    )
    sample = result.scalar_one_or_none()
    
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sample not found"
        )
    
    # Run anomaly detection
    service = AnomalyDetectionService(db)
    alerts = await service.check_sample(sample.id)
    
    # Save alerts to database
    created_alerts = []
    for alert_data in alerts:
        alert = AnomalyAlert(
            sample_id=sample.id,
            rule_id=alert_data["rule_id"],
            severity=alert_data["severity"],
            message=alert_data["message"],
            details=alert_data["details"],
            is_resolved=False
        )
        db.add(alert)
        created_alerts.append(alert)
    
    # Update sample anomaly flag
    if alerts:
        sample.is_anomaly = True
        sample.anomaly_reasons = [a["message"] for a in alerts]
    else:
        sample.is_anomaly = False
        sample.anomaly_reasons = None
    
    await db.commit()
    
    return {
        "sample_id": sample_id,
        "anomalies_found": len(alerts),
        "alerts": alerts
    }

@router.get("/alerts")
async def get_alerts(
    resolved: bool = False,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get anomaly alerts"""
    service = AnomalyDetectionService(db)
    alerts = await service.get_active_alerts(limit)
    
    return {
        "total": len(alerts),
        "alerts": alerts
    }

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Resolve an anomaly alert"""
    service = AnomalyDetectionService(db)
    success = await service.resolve_alert(alert_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )
    
    return {"message": "Alert resolved successfully"}

@router.post("/rules/init")
async def initialize_anomaly_rules(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Initialize default anomaly rules"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can initialize rules"
        )
    
    default_rules = [
        {
            "name": "Too Many Samples Per Hour",
            "description": "Flags when a sampler creates more than 50 samples in an hour",
            "rule_type": "timing",
            "parameters": {"max_samples_per_hour": 50}
        },
        {
            "name": "Sample Frequency Too High",
            "description": "Flags when samples are created too quickly by the same sampler",
            "rule_type": "timing",
            "parameters": {"min_time_between_samples": 5}
        },
        {
            "name": "Custody Gap Too Long",
            "description": "Flags when there is a gap of more than 24 hours between custody events",
            "rule_type": "custody",
            "parameters": {"max_gap_hours": 24}
        },
        {
            "name": "Duplicate Scan Events",
            "description": "Flags when duplicate scan types are detected",
            "rule_type": "duplicate",
            "parameters": {}
        },
        {
            "name": "Result Variance Outlier",
            "description": "Flags when test results vary significantly from averages",
            "rule_type": "variance",
            "parameters": {"variance_threshold": 0.3}
        }
    ]
    
    created_rules = []
    for rule_data in default_rules:
        rule = AnomalyRule(
            name=rule_data["name"],
            description=rule_data["description"],
            rule_type=rule_data["rule_type"],
            parameters=rule_data["parameters"],
            is_active=True
        )
        db.add(rule)
        created_rules.append(rule)
    
    await db.commit()
    
    return {
        "message": "Default anomaly rules initialized",
        "rules_created": len(created_rules)
    }