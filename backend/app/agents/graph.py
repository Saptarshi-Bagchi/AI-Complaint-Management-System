import json
import os
import re
from email import policy
from email.parser import BytesParser
from io import BytesIO
from typing import Any, TypedDict

import pdfplumber
from fastapi import UploadFile
from langchain_groq import ChatGroq
from langgraph.graph import START
from langgraph.graph.state import StateGraph

MODEL_NAME = "llama-3.3-70b-versatile"


class GraphState(TypedDict, total=False):
    input_text: str
    source: str
    customerName: str
    productName: str
    productStrength: str
    batchNumber: str
    manufacturingDate: str
    expiryDate: str
    quantityAffected: str
    complaintType: str
    complaintDate: str
    description: str
    severity: str
    priority: str
    status: str
    riskScore: float
    riskSummary: str
    nextAction: str
    capaSuggestion: str


def _load_groq_api_key() -> str | None:
    return os.getenv("GROQ_API_KEY")


def _find_json_slice(text: str, open_char: str, close_char: str) -> str | None:
    depth = 0
    start = None
    for index, char in enumerate(text):
        if char == open_char:
            if start is None:
                start = index
            depth += 1
        elif char == close_char and start is not None:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _extract_json(text: str) -> Any:
    if not text:
        raise ValueError("Empty response from Groq")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for open_char, close_char in (("{", "}"), ("[", "]")):
            candidate = _find_json_slice(text, open_char, close_char)
            if candidate is not None:
                return json.loads(candidate)
        raise


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (int, float)):
        return value
    return str(value).strip() or None


def _normalize_fields(extracted: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in extracted.items():
        if value is None:
            continue
        if key == "riskScore":
            try:
                normalized[key] = float(value)
            except (TypeError, ValueError):
                normalized[key] = None
            continue
        normalized[key] = _normalize_value(value)
    return normalized


def _build_chat_model(
    model_name: str,
    temperature: float,
    max_tokens: int,
    reasoning_effort: str | None = None,
    timeout: float = 30.0,
) -> ChatGroq:
    api_key = _load_groq_api_key()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")

    kwargs: dict[str, Any] = {
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
        "api_key": api_key,
    }
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
        kwargs["reasoning_format"] = "hidden"

    return ChatGroq(**kwargs)


def _short_text(text: str, max_length: int = 4000) -> str:
    content = text.strip()
    return content if len(content) <= max_length else content[:max_length] + "\n\n[Text truncated for extraction]"


def _parse_uploaded_bytes(raw_bytes: bytes, filename: str, content_type: str) -> str:
    lower_name = filename.lower() if filename else ""
    if content_type == "application/pdf" or lower_name.endswith(".pdf"):
        try:
            with pdfplumber.open(BytesIO(raw_bytes)) as pdf:
                return "\n\n".join(page.extract_text() or "" for page in pdf.pages).strip()
        except Exception:
            return raw_bytes.decode("utf-8", errors="replace")

    if lower_name.endswith(".eml") or content_type in {"message/rfc822", "application/octet-stream"}:
        try:
            message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
            if message.is_multipart():
                body = message.get_body(preferencelist=("plain", "html"))
            else:
                body = message
            return (body.get_content() or "").strip()
        except Exception:
            return raw_bytes.decode("utf-8", errors="replace")

    return raw_bytes.decode("utf-8", errors="replace").strip()


async def parse_uploaded_file(upload_file: UploadFile) -> str:
    raw_bytes = await upload_file.read()
    return _parse_uploaded_bytes(raw_bytes, upload_file.filename or "upload", upload_file.content_type or "")


async def extract_text_from_file(upload_file: UploadFile) -> str:
    raw_bytes = await upload_file.read()
    if not raw_bytes:
        raise ValueError("File is empty")

    lower_name = (upload_file.filename or "").lower()
    content_type = upload_file.content_type or ""

    if lower_name.endswith(".pdf") or content_type == "application/pdf":
        try:
            with pdfplumber.open(BytesIO(raw_bytes)) as pdf:
                text = "\n\n".join(page.extract_text() or "" for page in pdf.pages).strip()
                if not text:
                    raise ValueError("No text could be extracted from the PDF. It may be empty or contain only images.")
                return text
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to parse PDF: {str(e)}")

    if lower_name.endswith(".txt") or content_type.startswith("text/"):
        text = raw_bytes.decode("utf-8", errors="replace").strip()
        if not text:
            raise ValueError("The text file is empty.")
        return text

    raise ValueError("Unsupported file type. Only PDF and TXT files are supported.")

def _extract_complaint_fields(state: GraphState, config: Any = None) -> dict[str, Any]:
    text = _short_text(state.get("input_text", "") or "")
    if not text:
        return {"status": "Pending Triage"}

    prompt = f"""
Extract structured complaint fields from the customer complaint text below.
Return JSON only with the exact keys:
- source
- customerName
- productName
- productStrength
- batchNumber
- manufacturingDate (format as YYYY-MM-DD; if only month/year is known, use the 1st of that month, e.g. "2026-03-01")
- expiryDate (format as YYYY-MM-DD; if only month/year is known, use the 1st of that month, e.g. "2028-02-01")
- quantityAffected
- complaintType
- complaintDate
- description
- severity
- priority
- status

Complaint text:
{text}
"""

    messages = [
        ("system", "You are a pharmaceutical quality assurance analyst extracting structured complaint fields from customer complaint text."),
        ("human", prompt),
    ]

    try:
        model = _build_chat_model(
            model_name=MODEL_NAME,
            temperature=0.0,
            max_tokens=900,
            timeout=30.0,
        )
        result = model.invoke(messages)
        extracted_raw = _extract_json(result.content)
        normalized = _normalize_fields(extracted_raw if isinstance(extracted_raw, dict) else {})
        return normalized
    except Exception:
        return {
            "description": text[:1200],
            "status": "Pending Triage",
        }


def _assess_risk(state: GraphState, config: Any = None) -> dict[str, Any]:
    text = _short_text(state.get("input_text", "") or "")
    if not text:
        return {
            "riskScore": 0.0,
            "riskSummary": "No complaint text was provided.",
            "nextAction": "Review the uploaded complaint and try again.",
            "status": state.get("status", "Pending Triage"),
        }

    extracted_fields = {key: state.get(key) for key in [
        "source",
        "customerName",
        "productName",
        "productStrength",
        "batchNumber",
        "manufacturingDate",
        "expiryDate",
        "quantityAffected",
        "complaintType",
        "complaintDate",
        "description",
        "severity",
        "priority",
        "status",
    ]}

    prompt = f"""
You are an expert QA risk analyst. Based on the extracted complaint fields and the original complaint text, assign the appropriate severity, priority, status, and initial risk score.
Also provide a short risk assessment summary, a recommended next action of no more than 8 words, and a CAPA suggestion.
Return JSON only with the exact keys:
- severity
- priority
- status
- riskScore
- riskSummary
- nextAction
- capaSuggestion

Complaint fields:
{json.dumps(extracted_fields, indent=2)}

Complaint text:
{text}
"""

    messages = [
        ("system", "You are a pharmaceutical quality assurance risk analyst. Provide a reasoned classification and CAPA suggestion from complaint details."),
        ("human", prompt),
    ]

    try:
        model = _build_chat_model(
            model_name=MODEL_NAME,
            temperature=0.25,
            max_tokens=900,
            timeout=60.0,
        )
        result = model.invoke(messages)
        extracted_raw = _extract_json(result.content)
        normalized = _normalize_fields(extracted_raw if isinstance(extracted_raw, dict) else {})

        if "riskScore" in normalized and normalized["riskScore"] is not None:
            try:
                normalized["riskScore"] = min(max(float(normalized["riskScore"]), 0.0), 1.0)
            except (TypeError, ValueError):
                normalized["riskScore"] = None

        normalized.setdefault("status", state.get("status", "Pending Triage"))
        normalized.setdefault("severity", state.get("severity"))
        normalized.setdefault("priority", state.get("priority"))
        if normalized.get("nextAction"):
            normalized["nextAction"] = " ".join(str(normalized["nextAction"]).split()[:8])
        return normalized
    except Exception:
        return {
            "riskScore": 0.0,
            "riskSummary": "Initial risk assessment could not be completed.",
            "nextAction": "Review the complaint manually.",
            "status": state.get("status", "Pending Triage"),
        }


_graph_builder = (
    StateGraph(state_schema=GraphState)
    .add_node("extract_fields", _extract_complaint_fields)
    .add_node("assess_risk", _assess_risk)
    .add_edge(START, "extract_fields")
    .add_edge("extract_fields", "assess_risk")
    .set_entry_point("extract_fields")
    .set_finish_point("assess_risk")
)
_compiled_graph = _graph_builder.compile()


def analyze_complaint_text(complaint_text: str, source: str | None = None) -> dict[str, Any]:
    state: GraphState = {"input_text": complaint_text}
    if source:
        state["source"] = source

    try:
        result = _compiled_graph.invoke(state)
        return {k: v for k, v in result.items() if v is not None}
    except Exception:
        return {
            "description": complaint_text[:1200],
            "status": "Pending Triage",
        }


_UPDATABLE_FIELD_KEYS = {
    "source",
    "customerName",
    "productName",
    "productStrength",
    "batchNumber",
    "manufacturingDate",
    "expiryDate",
    "quantityAffected",
    "complaintType",
    "complaintDate",
    "description",
    "severity",
    "priority",
    "status",
}

_UPDATE_SIGNALS = [
    "change", "update", "correct", "modify", "replace",
    "set the", "set it", "should be", "needs to be", "is actually",
    "fix the", "edit", "revise", "adjust", "make it", "make the",
    "change the", "update the", "correct the",
]

_NEW_COMPLAINT_SIGNALS = [
    "new complaint", "received a complaint", "complaint regarding",
    "complaint about", "reported that", "we received",
    "customer reported", "customer called", "customer emailed",
    "a customer reported", "log a complaint", "log a new complaint",
]

_QUESTION_SIGNALS = [
    "what", "when", "where", "why", "how", "can you", "could you",
    "show me", "tell me", "explain", "summarize", "next step", "risk",
]

_COMPLAINT_SIGNALS = [
    "complaint", "product", "medicine", "medication", "tablet", "capsule",
    "batch", "lot", "defect", "damaged", "adverse", "reaction", "side effect",
    "quality", "patient", "customer",
]


def detect_complaint_intent(message: str, has_existing_complaint: bool) -> str:
    text = (message or "").strip()
    if not text:
        return "out_of_scope"

    lowered = text.lower()

    try:
        prompt = f"""Classify the user's message into exactly one of four intents:

1. new_complaint - The user is describing a brand new customer complaint (reporting a product defect, describing an incident, pasting a complaint email or report).
2. update_complaint - The user is requesting a modification to an already-extracted complaint (examples: "change the batch number to B12345", "update the customer's name", "the manufacturing date should be June 2026", "correct the lot number", "set the quantity to 5 boxes").
3. complaint_question - The user is asking for information, a summary, an explanation, or the next action about the existing complaint without asking to change a field.
4. out_of_scope - The message is unrelated to pharmaceutical complaint intake, updates, triage, investigation, risk, status, or follow-up actions.

Keep the conversation strictly about pharmaceutical complaint intake, triage, investigation, risk, fields, status, and follow-up actions. Do not treat general chatbot requests as complaint questions.
{('An existing complaint has already been extracted, so ambiguous field-related messages should be classified as update_complaint.' if has_existing_complaint else 'No complaint has been recorded yet. The first in-scope message must contain a customer complaint; otherwise classify it as out_of_scope.')}

User message:
\"{text}\"

Respond with ONLY one label: new_complaint, update_complaint, complaint_question, or out_of_scope"""

        model = _build_chat_model(
            model_name=MODEL_NAME,
            temperature=0.0,
            max_tokens=20,
            timeout=15.0,
        )
        result = model.invoke(
            [
                ("system", "You classify messages for a pharmaceutical complaint management system. Output exactly one label and nothing else."),
                ("human", prompt),
            ]
        )
        content = (result.content or "").strip().lower()
        if "out_of_scope" in content:
            return "out_of_scope"
        if "complaint_question" in content:
            return "complaint_question"
        if "update_complaint" in content:
            return "update_complaint"
        if "new_complaint" in content:
            return "new_complaint"
        if "update" in content and "new" not in content:
            return "update_complaint"
        if "new" in content and "update" not in content:
            return "new_complaint"
    except Exception:
        pass

    update_score = sum(1 for signal in _UPDATE_SIGNALS if signal in lowered)
    new_score = sum(1 for signal in _NEW_COMPLAINT_SIGNALS if signal in lowered)
    question_score = sum(1 for signal in _QUESTION_SIGNALS if lowered.startswith(signal) or f" {signal} " in lowered)
    complaint_score = sum(1 for signal in _COMPLAINT_SIGNALS if signal in lowered)

    if new_score > update_score:
        return "new_complaint"
    if question_score > 0 and update_score == 0:
        return "complaint_question"
    if not has_existing_complaint and complaint_score > 0:
        return "new_complaint"
    if update_score > 0 and new_score == 0:
        return "update_complaint"
    if update_score >= new_score and update_score > 0:
        return "update_complaint"

    return "update_complaint" if has_existing_complaint else "out_of_scope"


def answer_complaint_question(message: str, existing_fields: dict[str, Any]) -> str:
    fields_json = json.dumps(existing_fields, indent=2, default=str)
    prompt = f"""Answer the user's question using only the existing pharmaceutical complaint record below.
Stay strictly within complaint management: intake details, field values, triage, risk, investigation, status, and next actions.
Do not act as a general chatbot, provide unrelated information, invent facts, or change any complaint field.
If the question is outside complaint management, say that you can only help with this complaint record.

Existing complaint:
{fields_json}

User question:
{message}
"""
    try:
        model = _build_chat_model(model_name=MODEL_NAME, temperature=0.0, max_tokens=300, timeout=30.0)
        result = model.invoke([
            ("system", "You are a pharmaceutical complaint management analyst. Answer only in scope."),
            ("human", prompt),
        ])
        return (result.content or "I can help with the complaint details, triage, risk, status, or next action.").strip()
    except Exception:
        return "I can help with the complaint details, triage, risk, status, or next action."


def update_complaint_fields(message: str, existing_fields: dict[str, Any]) -> dict[str, Any]:
    text = (message or "").strip()
    if not text:
        return {}

    fields_json = json.dumps(existing_fields, indent=2, default=str)

    prompt = f"""You are updating an existing pharmaceutical customer complaint record.
The user is requesting specific modifications. Extract ONLY the fields the user explicitly asks to change.

CRITICAL RULES:
- Do NOT re-extract or regenerate any field the user did not mention.
- Do NOT include productDescription, complaintType, severity, priority, status, riskScore, riskSummary, nextAction, capaSuggestion, or any other field unless the user explicitly references it.
- Return ONLY the fields to update, using the exact key names listed below.
- If the user mentions a date, format it as YYYY-MM-DD (if only month/year is known, use the 1st of that month, e.g. "2026-06-01").
- If the user does not request any field change, return an empty JSON object {{}}.

Available field keys:
- source
- customerName
- productName
- productStrength
- batchNumber
- manufacturingDate
- expiryDate
- quantityAffected
- complaintType
- complaintDate
- description
- severity
- priority
- status

Existing complaint:
{fields_json}

User's update instruction:
{text}

Return JSON only with the fields to update. Do not include any field the user did not explicitly mention."""

    messages = [
        (
            "system",
            "You are a pharmaceutical QA assistant that applies targeted field updates to an existing complaint record. You never regenerate fields that were not explicitly requested.",
        ),
        ("human", prompt),
    ]

    try:
        model = _build_chat_model(
            model_name=MODEL_NAME,
            temperature=0.0,
            max_tokens=500,
            timeout=30.0,
        )
        result = model.invoke(messages)
        extracted_raw = _extract_json(result.content)
        normalized = _normalize_fields(extracted_raw if isinstance(extracted_raw, dict) else {})

        patch = {key: value for key, value in normalized.items() if key in _UPDATABLE_FIELD_KEYS}
        return patch
    except Exception:
        return {}
