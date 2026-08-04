from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.complaint import Complaint
from app.schemas.complaint import ComplaintCreate, ComplaintOut

router = APIRouter(prefix="/complaints", tags=["complaints"])

@router.post("/ingest", response_model=ComplaintOut)
def ingest_complaint(payload: ComplaintCreate, db: Session = Depends(get_db)):
    complaint = Complaint(source=payload.source, complaint_text=payload.complaint_text)
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return complaint

@router.get("/", response_model=list[ComplaintOut])
def list_complaints(db: Session = Depends(get_db)):
    return db.query(Complaint).all()

@router.get("/{complaint_id}", response_model=ComplaintOut)
def get_complaint(complaint_id: int, db: Session = Depends(get_db)):
    return db.query(Complaint).filter(Complaint.id == complaint_id).first()