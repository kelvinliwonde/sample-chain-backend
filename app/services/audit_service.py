from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import Request

from app.models.audit import AuditLog
from app.models.user import User

class AuditService:
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def log_action(
        self,
        user_id: int,
        action: str,
        resource: str,
        resource_id: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None
    ):
        """Log an action to the audit trail"""
        ip_address = None
        user_agent = None
        
        if request:
            if hasattr(request, 'client') and request.client:
                ip_address = request.client.host
            user_agent = request.headers.get("user-agent") if hasattr(request, 'headers') else None
        
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        self.db.add(audit_log)
        await self.db.commit()
    
    async def get_audit_logs(
        self,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        days: int = 7,
        limit: int = 100,
        skip: int = 0
    ) -> List[AuditLog]:
        """Get audit logs with filters"""
        query = select(AuditLog)
        
        if user_id:
            query = query.where(AuditLog.user_id == user_id)
        if action:
            query = query.where(AuditLog.action == action)
        if resource:
            query = query.where(AuditLog.resource == resource)
        
        # Filter by date (last N days)
        if days:
            date_threshold = datetime.utcnow() - timedelta(days=days)
            query = query.where(AuditLog.created_at >= date_threshold)
        
        query = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def get_user_activity_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get summary of user activity"""
        date_threshold = datetime.utcnow() - timedelta(days=days)
        
        # Total actions
        total_result = await self.db.execute(
            select(func.count()).where(AuditLog.created_at >= date_threshold)
        )
        total_actions = total_result.scalar() or 0
        
        # Actions by type
        actions_result = await self.db.execute(
            select(AuditLog.action, func.count())
            .where(AuditLog.created_at >= date_threshold)
            .group_by(AuditLog.action)
        )
        actions_by_type = {row[0]: row[1] for row in actions_result.all()}
        
        # Actions by user
        users_result = await self.db.execute(
            select(AuditLog.user_id, func.count())
            .where(AuditLog.created_at >= date_threshold)
            .group_by(AuditLog.user_id)
            .order_by(func.count().desc())
            .limit(10)
        )
        actions_by_user = {row[0]: row[1] for row in users_result.all()}
        
        return {
            "total_actions": total_actions,
            "actions_by_type": actions_by_type,
            "actions_by_user": actions_by_user,
            "days": days
        }