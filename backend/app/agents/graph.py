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


def _extract_complaint_fields(state: GraphState, config: Any) -> dict[str, Any]:
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
- manufacturingDate
- expiryDate
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
        extracted_raw = _extract_json(result.content)
        return _normalize_fields(extracted_raw if isinstance(extracted_raw, dict) else {})
    except Exception:
        return {
            "description": text[:1200],
            "status": "Pending Triage",
        }


def _assess_risk(state: GraphState, config: Any) -> dict[str, Any]:
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
            reasoning_effort="high",
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
