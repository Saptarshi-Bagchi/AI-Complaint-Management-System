from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ComplaintCreate(BaseModel):
    source: str
    complaint_text: str

class ComplaintOut(BaseModel):
    id: int
    source: str
    product_name: Optional[str] = None
    batch_no: Optional[str] = None
    customer_name: Optional[str] = None
    complaint_text: str
    category: Optional[str] = None
    severity: Optional[str] = None
    risk_score: Optional[float] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True