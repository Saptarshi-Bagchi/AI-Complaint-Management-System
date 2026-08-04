from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.complaint import Complaint
from app.schemas.complaint import ComplaintCreate, ComplaintOut
from app.services.complaint_ai import ComplaintAIService

router = APIRouter(prefix="/complaints", tags=["complaints"])
ai_service = ComplaintAIService()

class AnalyzeRequest(BaseModel):
    complaint_id: int
    complaint_text: str

class ChatRequest(BaseModel):
    message: str

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

@router.post("/{complaint_id}/analyze")
def analyze_complaint(complaint_id: int, payload: AnalyzeRequest, db: Session = Depends(get_db)):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        return {"status": "error", "message": "Complaint not found"}

    complaint_text = payload.complaint_text or complaint.complaint_text or ""
    extracted = ai_service.extract_fields(complaint_text)

    # Apply extracted fields to the stored complaint (map camelCase -> snake_case)
    # Only persist values that were actually extracted (non-empty / non-null)
    if extracted.get("productName"):
        complaint.product_name = extracted.get("productName")
    if extracted.get("batchNumber"):
        complaint.batch_no = extracted.get("batchNumber")
    if extracted.get("customerName"):
        complaint.customer_name = extracted.get("customerName")
    if extracted.get("complaintType"):
        complaint.category = extracted.get("complaintType")
    if extracted.get("severity"):
        complaint.severity = extracted.get("severity")
    # status may be provided by the extractor, otherwise keep existing
    if extracted.get("status"):
        complaint.status = extracted.get("status")
    db.commit()

    # Debug logging for development: print extracted payload so server logs show AI output
    try:
        print(f"[analyze] complaint_id={complaint_id} extracted_keys={list(extracted.keys())}")
        print(f"[analyze] extracted_sample={str({k: extracted.get(k) for k in ['customerName','productName','severity','description']})}")
    except Exception:
        pass

    # Return the normalized analysis response (camelCase keys expected by frontend)
    response = {
        "status": extracted.get("status", "Pending Triage"),
        "description": extracted.get("description"),
        "customerName": extracted.get("customerName"),
        "productName": extracted.get("productName"),
        "productStrength": extracted.get("productStrength"),
        "batchNumber": extracted.get("batchNumber"),
        "manufacturingDate": extracted.get("manufacturingDate"),
        "expiryDate": extracted.get("expiryDate"),
        "quantityAffected": extracted.get("quantityAffected"),
        "complaintType": extracted.get("complaintType"),
        "complaintDate": extracted.get("complaintDate"),
        "severity": extracted.get("severity"),
        "priority": extracted.get("priority"),
        "debug": {"extracted_keys": list(extracted.keys())},
    }

    return response

@router.post("/{complaint_id}/chat")
def chat_with_complaint(complaint_id: int, payload: ChatRequest):
    response = (
        f"Complaint {complaint_id} has been queued for triage review. "
        f"The intake note was: {payload.message[:120]}"
    )
    return {
        "response": response,
        "message": payload.message,
    }