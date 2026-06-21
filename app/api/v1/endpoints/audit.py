from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.models.user import User
from app.services.audit_service import AuditService

router = APIRouter()

@router.get("/logs")
async def get_audit_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    resource: Optional[str] = None,
    days: int = 7,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get audit logs (admin/supervisor only)"""
    if current_user.role not in ["admin", "supervisor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and supervisors can view audit logs"
        )
    
    service = AuditService(db)
    logs = await service.get_audit_logs(
        user_id=user_id,
        action=action,
        resource=resource,
        days=days,
        limit=limit,
        skip=skip
    )
    
    return {
        "total": len(logs),
        "logs": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "action": log.action,
                "resource": log.resource,
                "resource_id": log.resource_id,
                "changes": log.changes,
                "ip_address": log.ip_address,
                "created_at": log.created_at
            }
            for log in logs
        ]
    }

@router.get("/summary")
async def get_audit_summary(
    days: int = 7,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get audit summary (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view audit summary"
        )
    
    service = AuditService(db)
    summary = await service.get_user_activity_summary(days)
    
    return summary