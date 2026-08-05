from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.complaint import Complaint
from app.schemas.complaint import ComplaintCreate, ComplaintOut
from app.services.complaint_ai import ComplaintAIService
from app.agents.graph import (
    analyze_complaint_text,
    detect_complaint_intent,
    parse_uploaded_file,
    update_complaint_fields,
)

router = APIRouter(prefix="/complaints", tags=["complaints"])
ai_service = ComplaintAIService()

class AnalyzeRequest(BaseModel):
    complaint_id: int
    complaint_text: str

class ChatRequest(BaseModel):
    message: str

class ProcessMessageRequest(BaseModel):
    message: str
    source: str | None = None
    # The current in-memory complaint object (from the frontend). When this is
    # non-empty the backend can decide whether the message is an update to it
    # or a brand-new complaint.
    existing_complaint: dict | None = None
    # When True the message is always treated as a new complaint (used for
    # file uploads / explicit "new complaint" actions).
    force_new: bool = False

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


@router.post("/process-message")
def process_message(payload: ProcessMessageRequest, db: Session = Depends(get_db)):
    """Unified entry point for the AI copilot.

    Detects the user's intent first, then either:
      * runs the full extraction pipeline for a NEW complaint, or
      * applies a field-level PATCH for an UPDATE to an existing complaint.

    The response always carries the ``intent`` so the frontend can decide how
    to merge the result into its in-memory state.
    """
    message = (payload.message or "").strip()
    existing = payload.existing_complaint or {}

    # A complaint "exists" once at least one extracted field has been
    # populated. An empty/blank form is treated as no existing complaint.
    has_existing = bool(
        existing
        and any(
            (value not in (None, "", []))
            for key, value in existing.items()
            if key != "status"
        )
    )

    # File uploads / explicit "new complaint" actions bypass intent detection.
    if payload.force_new:
        intent = "new_complaint"
    else:
        intent = detect_complaint_intent(message, has_existing_complaint=has_existing)

    print(f"=== PROCESS-MESSAGE intent={intent} has_existing={has_existing} ===")

    if intent == "new_complaint":
        # ---- New complaint: full extraction pipeline -----------------------
        complaint = Complaint(
            source=payload.source or "manual",
            complaint_text=message or "No text provided",
        )
        db.add(complaint)
        db.commit()
        db.refresh(complaint)

        analysis = analyze_complaint_text(message, source=payload.source)

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

        return {
            "intent": "new_complaint",
            "complaintId": complaint.id,
            "analysis": {
                "status": analysis.get("status", "Pending Triage"),
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
            },
        }

    # ---- Update existing complaint: field-level patch ----------------------
    patch = update_complaint_fields(message, existing)

    # Merge the patch onto the existing object so the caller receives the
    # full, up-to-date complaint (unchanged fields are preserved).
    merged = {**existing, **patch}

    return {
        "intent": "update_complaint",
        "complaintId": existing.get("complaintId"),
        "patch": patch,
        "analysis": merged,
    }
