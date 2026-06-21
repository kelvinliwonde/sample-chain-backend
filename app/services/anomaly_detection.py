from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json

from app.models.sample import Sample, SampleStatus, CustodyScan
from app.models.anomaly import AnomalyRule, AnomalyAlert
from app.models.user import User

class AnomalyDetectionService:
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def check_sample(self, sample_id: int) -> List[Dict[str, Any]]:
        """Check a sample for all anomalies"""
        alerts = []
        
        # Get sample
        result = await self.db.execute(
            select(Sample).where(Sample.id == sample_id)
        )
        sample = result.scalar_one_or_none()
        if not sample:
            return alerts
        
        # Run all checks
        alerts.extend(await self.check_timing(sample))
        alerts.extend(await self.check_custody_gap(sample))
        alerts.extend(await self.check_duplicate_scans(sample))
        alerts.extend(await self.check_result_variance(sample))
        alerts.extend(await self.check_sampler_frequency(sample))
        
        return alerts
    
    async def check_timing(self, sample: Sample) -> List[Dict[str, Any]]:
        """Check for timing anomalies"""
        alerts = []
        
        # Get active timing rules
        result = await self.db.execute(
            select(AnomalyRule).where(
                and_(
                    AnomalyRule.rule_type == "timing",
                    AnomalyRule.is_active == True
                )
            )
        )
        rules = result.scalars().all()
        
        for rule in rules:
            params = rule.parameters or {}
            max_samples_per_hour = params.get("max_samples_per_hour", 50)
            
            # Count samples created by same user in last hour
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            count_result = await self.db.execute(
                select(func.count()).where(
                    and_(
                        Sample.created_by_id == sample.created_by_id,
                        Sample.created_at >= one_hour_ago,
                        Sample.id != sample.id
                    )
                )
            )
            count = count_result.scalar() or 0
            
            if count >= max_samples_per_hour:
                alerts.append({
                    "rule_id": rule.id,
                    "severity": "high",
                    "message": f"Sampler created {count + 1} samples in the last hour (limit: {max_samples_per_hour})",
                    "details": {
                        "sample_count": count + 1,
                        "limit": max_samples_per_hour,
                        "sampler_id": sample.created_by_id,
                        "time_window": "1 hour"
                    }
                })
        
        return alerts
    
    async def check_custody_gap(self, sample: Sample) -> List[Dict[str, Any]]:
        """Check for custody gaps"""
        alerts = []
        
        result = await self.db.execute(
            select(AnomalyRule).where(
                and_(
                    AnomalyRule.rule_type == "custody",
                    AnomalyRule.is_active == True
                )
            )
        )
        rules = result.scalars().all()
        
        for rule in rules:
            params = rule.parameters or {}
            max_gap_hours = params.get("max_gap_hours", 24)
            
            # Get scans for this sample
            scans_result = await self.db.execute(
                select(CustodyScan)
                .where(CustodyScan.sample_id == sample.id)
                .order_by(CustodyScan.scanned_at)
            )
            scans = scans_result.scalars().all()
            
            if len(scans) >= 2:
                # Check gap between pickup and dropoff
                for i in range(len(scans) - 1):
                    gap = (scans[i+1].scanned_at - scans[i].scanned_at).total_seconds() / 3600
                    if gap > max_gap_hours:
                        alerts.append({
                            "rule_id": rule.id,
                            "severity": "medium",
                            "message": f"Custody gap of {gap:.1f} hours between {scans[i].scan_type} and {scans[i+1].scan_type} (limit: {max_gap_hours}h)",
                            "details": {
                                "gap_hours": round(gap, 1),
                                "from_scan": scans[i].scan_type,
                                "to_scan": scans[i+1].scan_type,
                                "from_time": scans[i].scanned_at.isoformat(),
                                "to_time": scans[i+1].scanned_at.isoformat(),
                                "limit": max_gap_hours
                            }
                        })
        
        return alerts
    
    async def check_duplicate_scans(self, sample: Sample) -> List[Dict[str, Any]]:
        """Check for duplicate scan events"""
        alerts = []
        
        result = await self.db.execute(
            select(AnomalyRule).where(
                and_(
                    AnomalyRule.rule_type == "duplicate",
                    AnomalyRule.is_active == True
                )
            )
        )
        rules = result.scalars().all()
        
        for rule in rules:
            # Get scan types for this sample
            scans_result = await self.db.execute(
                select(CustodyScan.scan_type)
                .where(CustodyScan.sample_id == sample.id)
            )
            scan_types = [s[0] for s in scans_result.all()]
            
            # Check for duplicates
            from collections import Counter
            duplicates = [item for item, count in Counter(scan_types).items() if count > 1]
            
            if duplicates:
                alerts.append({
                    "rule_id": rule.id,
                    "severity": "medium",
                    "message": f"Duplicate scan types detected: {', '.join(duplicates)}",
                    "details": {
                        "duplicate_types": duplicates,
                        "scan_count": len(scan_types)
                    }
                })
        
        return alerts
    
    async def check_result_variance(self, sample: Sample) -> List[Dict[str, Any]]:
        """Check for result variance anomalies"""
        alerts = []
        
        if not sample.result_data:
            return alerts
        
        result = await self.db.execute(
            select(AnomalyRule).where(
                and_(
                    AnomalyRule.rule_type == "variance",
                    AnomalyRule.is_active == True
                )
            )
        )
        rules = result.scalars().all()
        
        for rule in rules:
            params = rule.parameters or {}
            variance_threshold = params.get("variance_threshold", 0.3)  # 30% variance
            
            # Get other samples from same mill
            samples_result = await self.db.execute(
                select(Sample)
                .where(
                    and_(
                        Sample.mill_id == sample.mill_id,
                        Sample.id != sample.id,
                        Sample.result_data.isnot(None),
                        Sample.status == SampleStatus.COMPLETED
                    )
                )
                .limit(10)
            )
            other_samples = samples_result.scalars().all()
            
            if not other_samples:
                return alerts
            
            # Compare numeric values
            for key, value in sample.result_data.items():
                try:
                    # Try to parse as number
                    if isinstance(value, str):
                        # Remove % and other symbols
                        clean_value = ''.join(c for c in value if c.isdigit() or c == '.')
                        if not clean_value:
                            continue
                        current_val = float(clean_value)
                    else:
                        current_val = float(value)
                    
                    # Calculate average of other samples
                    values = []
                    for other in other_samples:
                        if other.result_data and key in other.result_data:
                            other_val = other.result_data[key]
                            if isinstance(other_val, str):
                                clean_other = ''.join(c for c in other_val if c.isdigit() or c == '.')
                                if clean_other:
                                    values.append(float(clean_other))
                            else:
                                try:
                                    values.append(float(other_val))
                                except:
                                    pass
                    
                    if values:
                        avg = sum(values) / len(values)
                        if avg > 0:
                            variance = abs(current_val - avg) / avg
                            if variance > variance_threshold:
                                alerts.append({
                                    "rule_id": rule.id,
                                    "severity": "high",
                                    "message": f"Result '{key}' value {value} varies by {variance*100:.1f}% from average (threshold: {variance_threshold*100}%)",
                                    "details": {
                                        "parameter": key,
                                        "current_value": current_val,
                                        "average": round(avg, 2),
                                        "variance_percent": round(variance * 100, 1),
                                        "threshold": variance_threshold * 100,
                                        "sample_count": len(values)
                                    }
                                })
                except:
                    pass
        
        return alerts
    
    async def check_sampler_frequency(self, sample: Sample) -> List[Dict[str, Any]]:
        """Check if sampler is creating too many samples"""
        alerts = []
        
        result = await self.db.execute(
            select(AnomalyRule).where(
                and_(
                    AnomalyRule.rule_type == "timing",
                    AnomalyRule.is_active == True
                )
            )
        )
        rules = result.scalars().all()
        
        for rule in rules:
            params = rule.parameters or {}
            min_time_between_samples = params.get("min_time_between_samples", 5)  # minutes
            
            # Check time since last sample from same user
            last_sample_result = await self.db.execute(
                select(Sample)
                .where(
                    and_(
                        Sample.created_by_id == sample.created_by_id,
                        Sample.id != sample.id
                    )
                )
                .order_by(Sample.created_at.desc())
                .limit(1)
            )
            last_sample = last_sample_result.scalar_one_or_none()
            
            if last_sample:
                time_diff = (sample.created_at - last_sample.created_at).total_seconds() / 60
                if time_diff < min_time_between_samples and time_diff >= 0:
                    alerts.append({
                        "rule_id": rule.id,
                        "severity": "low",
                        "message": f"Only {time_diff:.1f} minutes since last sample by same sampler (min: {min_time_between_samples}m)",
                        "details": {
                            "minutes_since_last": round(time_diff, 1),
                            "last_sample_id": last_sample.sample_id,
                            "minimum_required": min_time_between_samples
                        }
                    })
        
        return alerts

    async def get_active_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all active (unresolved) alerts"""
        result = await self.db.execute(
            select(AnomalyAlert)
            .where(AnomalyAlert.is_resolved == False)
            .order_by(AnomalyAlert.created_at.desc())
            .limit(limit)
        )
        alerts = result.scalars().all()
        
        return [
            {
                "id": alert.id,
                "sample_id": alert.sample_id,
                "severity": alert.severity,
                "message": alert.message,
                "details": alert.details,
                "created_at": alert.created_at
            }
            for alert in alerts
        ]

    async def resolve_alert(self, alert_id: int, user_id: int) -> bool:
        """Resolve an alert"""
        result = await self.db.execute(
            select(AnomalyAlert).where(AnomalyAlert.id == alert_id)
        )
        alert = result.scalar_one_or_none()
        
        if not alert:
            return False
        
        alert.is_resolved = True
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by_id = user_id
        
        await self.db.commit()
        return True