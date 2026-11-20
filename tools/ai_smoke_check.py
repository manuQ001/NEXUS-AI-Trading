"""One-shot OpenAI connectivity diagnostic for NEXUS 4.4.

Manual opt-in ONLY. Sends a fixed, non-market test prompt, makes at most one
OpenAI API request, does not touch SQLite, scanner, trading or risk settings.
Does not print credentials, response bodies or untrusted error messages.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from v4_ai_shadow import MODEL, ENDPOINT, NoRedirect, _safe_api_error

def check():
    key = os.environ.get("NEXUS_OPENAI_API_KEY", "").strip()
    if not key.startswith("sk-") or len(key) < 30:
        return "KEY_MISSING_OR_INCOMPLETE"
    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["OK"]},
            "note": {"type": "string"}
        },
        "required": ["status", "note"],
        "additionalProperties": False
    }
    body = {
        "model": MODEL, "store": False,
        "instructions": "Test di connettivita API. Non fornire consigli finanziari. "
                        "Rispondi con status OK e note breve.",
        "input": "Verifica il formato JSON. Non ci sono dati di mercato.",
        "max_output_tokens": 900,
        "text": {"format": {"type": "json_schema", "name": "nexus_smoke",
                             "strict": True, "schema": schema}}
    }
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=25) as response:
            data = response.read(50001)
        if len(data) > 50000:
            return "RESPONSE_TOO_LARGE"
        obj = json.loads(data)
        if obj.get("status") != "completed":
            detail = obj.get("incomplete_details") or {}
            if (isinstance(detail, dict)
                    and detail.get("reason") == "max_output_tokens"):
                return "INCOMPLETE_MAX_OUTPUT_TOKENS"
            return "RESPONSE_NOT_COMPLETED"
        parts = []
        for entry in obj.get("output", []):
            for item in entry.get("content", []):
                if item.get("type") == "output_text":
                    parts.append(item.get("text", ""))
        if not parts:
            return "NO_OUTPUT_TEXT"
        parsed = json.loads("".join(parts))
        if isinstance(parsed, dict) and parsed.get("status") == "OK":
            return "COMPLETED_OK"
        return "UNEXPECTED_SCHEMA"
    except Exception as exc:
        return _safe_api_error(exc)

if __name__ == "__main__":
    print("MODELLO:", MODEL)
    print("TEST SOLO CONNESSIONE; NESSUN TRADE; UNA POSSIBILE CHIAMATA API A PAGAMENTO")
    print("RISULTATO:", check())
