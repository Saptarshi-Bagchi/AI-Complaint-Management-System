from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from sqlalchemy.sql import func
from app.db.database import Base

class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String)
    product_name = Column(String, nullable=True)
    batch_no = Column(String, nullable=True)
    customer_name = Column(String, nullable=True)
    complaint_text = Column(Text)
    category = Column(String, nullable=True)
    severity = Column(String, nullable=True)
    risk_score = Column(Float, nullable=True)
    status = Column(String, default="New")
    created_at = Column(DateTime(timezone=True), server_default=func.now())