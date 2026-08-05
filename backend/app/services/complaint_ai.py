import os
from typing import Dict, Any

from groq import Groq


class ComplaintAIService:
    def __init__(self) -> None:
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY")) if os.getenv("GROQ_API_KEY") else None

    def extract_fields(self, complaint_text: str) -> Dict[str, Any]:
        if not self.client:
            return self._fallback_fields(complaint_text)

        prompt = f"""
You are extracting structured fields from a pharmaceutical customer complaint.
Return JSON only with these keys:
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
{complaint_text}
"""

        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are a pharmaceutical quality assurance analyst extracting structured complaint fields."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=500,
            )
            content = response.choices[0].message.content or "{}"
            import json
            parsed = json.loads(content)
            return {
                **self._fallback_fields(complaint_text),
                **parsed,
            }
        except Exception:
            return self._fallback_fields(complaint_text)

    def _fallback_fields(self, complaint_text: str) -> Dict[str, Any]:
        lowered = (complaint_text or "").lower()
        source = "Email" if "email" in lowered else "Portal" if "portal" in lowered else "Phone"

        return {
            "source": source,
            "description": (complaint_text[:240] if complaint_text else None),
            "status": "Pending Triage",
            "customerName": None,
            "productName": None,
            "productStrength": None,
            "batchNumber": None,
            "manufacturingDate": None,
            "expiryDate": None,
            "quantityAffected": None,
            "complaintType": None,
            "complaintDate": None,
            "severity": None,
            "priority": None,
        }
