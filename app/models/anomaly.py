from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

class AnomalyRule(Base):
    __tablename__ = "anomaly_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    rule_type = Column(String(50), nullable=False)  # 'timing', 'location', 'custody', 'variance', 'duplicate'
    is_active = Column(Boolean, default=True)
    parameters = Column(JSON, nullable=True)  # JSON config for rule
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    alerts = relationship("AnomalyAlert", back_populates="rule")

class AnomalyAlert(Base):
    __tablename__ = "anomaly_alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    sample_id = Column(Integer, ForeignKey("samples.id"), nullable=False)
    rule_id = Column(Integer, ForeignKey("anomaly_rules.id"), nullable=False)
    severity = Column(String(20), nullable=False)  # 'low', 'medium', 'high', 'critical'
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)  # Additional context
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    sample = relationship("Sample")
    rule = relationship("AnomalyRule", back_populates="alerts")
    resolved_by = relationship("User")