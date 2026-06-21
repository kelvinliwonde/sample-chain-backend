from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import json
from datetime import datetime

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Store request info
        method = request.method
        path = request.url.path
        
        # Skip static files and docs
        if path.startswith("/docs") or path.startswith("/openapi.json") or path.startswith("/uploads"):
            return await call_next(request)
        
        # Process request
        response = await call_next(request)
        
        # Log only write operations
        if method in ["POST", "PUT", "PATCH", "DELETE"]:
            # Get user from request state (set by auth middleware)
            user_id = getattr(request.state, "user_id", None)
            
            if user_id:
                from app.services.audit_service import AuditService
                from app.core.database import AsyncSessionLocal
                
                async with AsyncSessionLocal() as db:
                    audit_service = AuditService(db)
                    
                    # Get request body if available
                    body = await request.body()
                    body_data = None
                    if body:
                        try:
                            body_data = json.loads(body)
                        except:
                            pass
                    
                    # Extract resource from path
                    resource = "unknown"
                    if "samples" in path:
                        resource = "sample"
                    elif "auth" in path:
                        resource = "auth"
                    elif "scans" in path:
                        resource = "scan"
                    elif "results" in path:
                        resource = "result"
                    elif "anomaly" in path:
                        resource = "anomaly"
                    
                    await audit_service.log_action(
                        user_id=user_id,
                        action=method,
                        resource=resource,
                        resource_id=path.split("/")[-1] if len(path.split("/")) > 2 else None,
                        changes={"request": body_data} if body_data else None,
                        request=request
                    )
        
        return response