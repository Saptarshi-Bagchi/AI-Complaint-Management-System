from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.complaint import Complaint
from app.schemas.complaint import ComplaintCreate, ComplaintOut
from app.services.complaint_ai import ComplaintAIService
from app.agents.graph import (
    analyze_complaint_text,
    detect_complaint_intent,
    extract_text_from_file,
    parse_uploaded_file,
    answer_complaint_question,
    update_complaint_fields,
)

router = APIRouter(prefix="/complaints", tags=["complaints"])
ai_service = ComplaintAIService()

MAX_FILE_SIZE = 10 * 1024 * 1024

class AnalyzeRequest(BaseModel):
    complaint_id: int
    complaint_text: str

class ChatRequest(BaseModel):
    message: str

class ProcessMessageRequest(BaseModel):
    message: str
    source: str | None = None
    existing_complaint: dict | None = None
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
        "debug": {"model": "llama-3.3-70b-versatile"},
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


def _run_complaint_pipeline(message: str, source: str | None, existing: dict, force_new: bool, db: Session) -> dict:
    message = (message or "").strip()
    has_existing = bool(
        existing
        and any(
            (value not in (None, "", []))
            for key, value in existing.items()
            if key != "status"
        )
    )

    if force_new:
        intent = "new_complaint"
    else:
        intent = detect_complaint_intent(message, has_existing_complaint=has_existing)

    if intent == "new_complaint":
        complaint = Complaint(
            source=source or "manual",
            complaint_text=message or "No text provided",
        )
        db.add(complaint)
        db.commit()
        db.refresh(complaint)

        analysis = analyze_complaint_text(message, source=source)

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

    if intent == "out_of_scope":
        return {
            "intent": "out_of_scope",
            "complaintId": existing.get("complaintId"),
            "response": "I can only help with this complaint’s details, updates, triage, risk, status, or next actions.",
        }

    if intent == "complaint_question":
        return {
            "intent": "complaint_question",
            "complaintId": existing.get("complaintId"),
            "response": answer_complaint_question(message, existing),
        }

    patch = update_complaint_fields(message, existing)
    merged = {**existing, **patch}

    return {
        "intent": "update_complaint",
        "complaintId": existing.get("complaintId"),
        "patch": patch,
        "analysis": merged,
    }


@router.post("/process-message")
def process_message(payload: ProcessMessageRequest, db: Session = Depends(get_db)):
    return _run_complaint_pipeline(
        message=payload.message,
        source=payload.source,
        existing=payload.existing_complaint or {},
        force_new=payload.force_new,
        db=db,
    )


@router.post("/process-file")
async def process_file(
    file: UploadFile = File(...),
    source: str = "Portal",
    existing_complaint: str | None = None,
    force_new: bool = False,
    db: Session = Depends(get_db),
):
    import json

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file was uploaded.")

    lower_name = file.filename.lower()
    if not (lower_name.endswith(".pdf") or lower_name.endswith(".txt")):
        raise HTTPException(status_code=400, detail="Unsupported file type. Only PDF and TXT files are supported.")

    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File is too large. Maximum size is 10MB.")

    try:
        extracted_text = await extract_text_from_file(file)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Text extraction failed: {str(e)}")

    existing = {}
    if existing_complaint:
        try:
            existing = json.loads(existing_complaint)
        except json.JSONDecodeError:
            existing = {}

    return _run_complaint_pipeline(
        message=extracted_text,
        source=source,
        existing=existing,
        force_new=force_new,
        db=db,
    )
