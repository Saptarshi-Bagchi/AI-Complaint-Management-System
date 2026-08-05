from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.complaint import Complaint
from app.schemas.complaint import ComplaintCreate, ComplaintOut
from app.services.complaint_ai import ComplaintAIService
from app.agents.graph import analyze_complaint_text, parse_uploaded_file

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
async def analyze_complaint(complaint_id: int, request: Request, db: Session = Depends(get_db)):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    complaint_text = complaint.complaint_text or ""
    source = complaint.source
    file_upload: UploadFile | None = None

    if request.headers.get("content-type", "").startswith("multipart/"):
        form = await request.form()
        file_upload = form.get("file") if form.get("file") else None
        complaint_text = str(form.get("complaint_text") or complaint_text)
        source = str(form.get("source") or source)
    else:
        payload = await request.json()
        complaint_text = str(payload.get("complaint_text") or complaint_text)
        source = str(payload.get("source") or source)

    if file_upload is not None:
        extracted_text = await parse_uploaded_file(file_upload)
    else:
        extracted_text = complaint_text

    analysis = analyze_complaint_text(extracted_text, source=source)

    if analysis.get("productName"):
        complaint.product_name = analysis["productName"]
    if analysis.get("batchNumber"):
        complaint.batch_no = analysis["batchNumber"]
    if analysis.get("customerName"):
        complaint.customer_name = analysis["customerName"]
    if analysis.get("complaintType"):
        complaint.category = analysis["complaintType"]
    if analysis.get("severity"):
        complaint.severity = analysis["severity"]
    if analysis.get("status"):
        complaint.status = analysis["status"]
    if analysis.get("riskScore") is not None:
        complaint.risk_score = float(analysis["riskScore"])
    db.commit()

    response = {
        "status": analysis.get("status", complaint.status or "Pending Triage"),
        "description": analysis.get("description"),
        "customerName": analysis.get("customerName"),
        "productName": analysis.get("productName"),
        "productStrength": analysis.get("productStrength"),
        "batchNumber": analysis.get("batchNumber"),
        "manufacturingDate": analysis.get("manufacturingDate"),
        "expiryDate": analysis.get("expiryDate"),
        "quantityAffected": analysis.get("quantityAffected"),
        "complaintType": analysis.get("complaintType"),
        "complaintDate": analysis.get("complaintDate"),
        "severity": analysis.get("severity"),
        "priority": analysis.get("priority"),
        "riskScore": analysis.get("riskScore"),
        "riskSummary": analysis.get("riskSummary"),
        "nextAction": analysis.get("nextAction"),
        "capaSuggestion": analysis.get("capaSuggestion"),
        "debug": {"model": "llama-3.1-8b-instant / llama-3.3-70b-versatile"},
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