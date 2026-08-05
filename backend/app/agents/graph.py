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

def _extract_complaint_fields(state: GraphState, config: Any = None) -> dict[str, Any]:
    print("=== STATE RECEIVED BY EXTRACT NODE ===")
    print(state)
    text = _short_text(state.get("input_text", "") or "")
    print(f"=== TEXT LENGTH: {len(text)} ===")
    if not text:
        print("=== TEXT IS EMPTY, RETURNING EARLY ===")
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
            model_name="llama-3.1-8b-instant",
            temperature=0.0,
            max_tokens=900,
            timeout=30.0,
        )
        result = model.invoke(messages)
        print("=== RAW GROQ RESPONSE (extract) ===")
        print(result.content)
        extracted_raw = _extract_json(result.content)
        print("=== PARSED JSON (extract) ===")
        print(extracted_raw)
        normalized = _normalize_fields(extracted_raw if isinstance(extracted_raw, dict) else {})
        print("=== NORMALIZED (extract) ===")
        print(normalized)
        return normalized
    except Exception as e:
        import traceback
        print("=== EXTRACTION ERROR ===")
        traceback.print_exc()
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
Also provide a short risk assessment summary, a recommended next action, and a CAPA suggestion.
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
            model_name="llama-3.3-70b-versatile",
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
        return normalized
    except Exception as e:
        import traceback
        print("=== RISK ASSESSMENT ERROR ===")
        traceback.print_exc()
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
    print("=== analyze_complaint_text CALLED ===")
    print(f"complaint_text: {complaint_text!r}")
    state: GraphState = {"input_text": complaint_text}
    if source:
        state["source"] = source

    try:
        result = _compiled_graph.invoke(state)
        print("=== GRAPH INVOKE SUCCEEDED ===")
        print(result)
        return {k: v for k, v in result.items() if v is not None}
    except Exception as e:
        import traceback
        print("=== GRAPH INVOKE FAILED ===")
        traceback.print_exc()
        return {
            "description": complaint_text[:1200],
            "status": "Pending Triage",
        }


# ---------------------------------------------------------------------------
# Intent detection + field-level update support
# ---------------------------------------------------------------------------

# Fields that may be updated via a natural-language instruction. The
# AI-generated assessment fields are intentionally excluded so that an
# update such as "change the batch number" can never silently overwrite
# the risk assessment, severity, or CAPA suggestion.
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

# Imperative verbs/phrases that strongly indicate an update request.
_UPDATE_SIGNALS = [
    "change", "update", "correct", "modify", "replace",
    "set the", "set it", "should be", "needs to be", "is actually",
    "fix the", "edit", "revise", "adjust", "make it", "make the",
    "change the", "update the", "correct the",
]

# Narrative phrases that strongly indicate a brand-new complaint.
_NEW_COMPLAINT_SIGNALS = [
    "new complaint", "received a complaint", "complaint regarding",
    "complaint about", "reported that", "we received",
    "customer reported", "customer called", "customer emailed",
    "a customer reported", "log a complaint", "log a new complaint",
]


def detect_complaint_intent(message: str, has_existing_complaint: bool) -> str:
    """Classify a user message as ``new_complaint`` or ``update_complaint``.

    When no complaint has been extracted yet the message is always treated as
    a new complaint. When a complaint already exists the LLM is asked to
    classify the intent; a keyword heuristic is used as a fallback. Ambiguous
    messages default to ``update_complaint`` per the product requirements.
    """
    if not has_existing_complaint:
        return "new_complaint"

    text = (message or "").strip()
    if not text:
        return "new_complaint"

    lowered = text.lower()

    # ---- LLM-based detection (primary) -------------------------------------
    try:
        prompt = f"""Classify the user's message into exactly one of two intents:

1. new_complaint - The user is describing a brand new customer complaint (reporting a product defect, describing an incident, pasting a complaint email or report).
2. update_complaint - The user is requesting a modification to an already-extracted complaint (examples: "change the batch number to B12345", "update the customer's name", "the manufacturing date should be June 2026", "correct the lot number", "set the quantity to 5 boxes").

An existing complaint has already been extracted, so ambiguous messages should be classified as update_complaint unless the message clearly describes a new complaint.

User message:
\"{text}\"

Respond with ONLY one label: new_complaint or update_complaint"""

        model = _build_chat_model(
            model_name="llama-3.1-8b-instant",
            temperature=0.0,
            max_tokens=20,
            timeout=15.0,
        )
        result = model.invoke(
            [
                ("system", "You are an intent classifier. Output exactly one label and nothing else."),
                ("human", prompt),
            ]
        )
        content = (result.content or "").strip().lower()
        print("=== INTENT DETECTION (LLM) ===")
        print(f"message: {text!r}")
        print(f"response: {content!r}")
        if "update_complaint" in content:
            return "update_complaint"
        if "new_complaint" in content:
            return "new_complaint"
        # Lenient parsing of a single-word response.
        if "update" in content and "new" not in content:
            return "update_complaint"
        if "new" in content and "update" not in content:
            return "new_complaint"
    except Exception:
        import traceback
        print("=== INTENT DETECTION (LLM) FAILED, FALLING BACK TO HEURISTIC ===")
        traceback.print_exc()

    # ---- Heuristic fallback -------------------------------------------------
    update_score = sum(1 for signal in _UPDATE_SIGNALS if signal in lowered)
    new_score = sum(1 for signal in _NEW_COMPLAINT_SIGNALS if signal in lowered)

    print(f"=== INTENT DETECTION (HEURISTIC) update_score={update_score} new_score={new_score} ===")

    if new_score > update_score:
        return "new_complaint"
    if update_score > 0 and new_score == 0:
        return "update_complaint"
    if update_score >= new_score and update_score > 0:
        return "update_complaint"

    # Ambiguous with an existing complaint -> prefer update (requirement #4).
    return "update_complaint"


def update_complaint_fields(message: str, existing_fields: dict[str, Any]) -> dict[str, Any]:
    """Extract ONLY the fields the user explicitly requests to change.

    Returns a partial patch (subset of ``_UPDATABLE_FIELD_KEYS``) that can be
    merged into the existing complaint object. Fields the user did not mention
    are never included, so the existing values are preserved by the caller.
    """
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
            model_name="llama-3.1-8b-instant",
            temperature=0.0,
            max_tokens=500,
            timeout=30.0,
        )
        result = model.invoke(messages)
        print("=== UPDATE EXTRACTION (RAW) ===")
        print(result.content)
        extracted_raw = _extract_json(result.content)
        normalized = _normalize_fields(extracted_raw if isinstance(extracted_raw, dict) else {})
        print("=== UPDATE EXTRACTION (NORMALIZED) ===")
        print(normalized)

        # Keep only updatable keys so the AI can never silently patch
        # risk-assessment fields or introduce unknown keys.
        patch = {key: value for key, value in normalized.items() if key in _UPDATABLE_FIELD_KEYS}
        print("=== UPDATE PATCH (FINAL) ===")
        print(patch)
        return patch
    except Exception:
        import traceback
        print("=== UPDATE EXTRACTION ERROR ===")
        traceback.print_exc()
        return {}
