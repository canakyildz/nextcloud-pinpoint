"""A deterministic stand-in for an OpenAI-compatible text model, for the integration tests.

Nextcloud's "OpenAI and LocalAI integration" is pointed at this server, so Pinpoint's prompts travel the
real path (Pinpoint → TaskProcessing → integration_openai → HTTP) and come back with the ground truth of
the dataset document they contain. Only the model is fake; everything else is the real stack.

    python tests/integration/mock_llm.py   # listens on :8000
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request

DATASET = Path(__file__).resolve().parents[2] / "evals" / "dataset"
TRUTHS = {p.stem: json.loads(p.read_text()) for p in DATASET.glob("*.json") if p.stem != "manifest"}

app = FastAPI()


def _answer(prompt: str) -> str:
    # Pick the document whose identifying values all appear in the prompt.
    for _name, truth in sorted(TRUTHS.items()):
        fields = truth["fields"]
        keys = ("invoice_number", "supplier") if truth["template"] == "invoice" else ("merchant", "date")
        quotes = [fields[k]["quote"] for k in keys if fields.get(k, {}).get("quote")]
        if quotes and all(q in prompt for q in quotes):
            mapped = _map_keys(prompt, fields)
            return json.dumps({"fields": mapped}, ensure_ascii=False)
    return "I could not find a document in this prompt."


def _map_keys(prompt: str, fields: dict) -> dict:
    """Prompts built from a Tables table use keys derived from column titles ("total_amount");
    template prompts use the template keys ("total"). Answer with whichever the prompt asks for."""
    by_label = {
        "supplier": "supplier",
        "invoice_number": "invoice_number",
        "issue_date": "issue_date",
        "due_date": "due_date",
        "currency": "currency",
        "net_amount": "subtotal",
        "tax_amount": "tax",
        "total_amount": "total",
        "iban": "iban",
        "merchant": "merchant",
        "date": "date",
        "payment_method": "payment_method",
    }
    out = {}
    for key, source in by_label.items():
        if f'"{key}"' in prompt and source in fields:
            out[key] = fields[source]
    for key, value in fields.items():
        if f'"{key}"' in prompt and key not in out:
            out[key] = value
    return out


@app.get("/v1/models")
async def models() -> dict:
    return {"object": "list", "data": [{"id": "mock-model", "object": "model", "owned_by": "pinpoint-tests"}]}


@app.post("/v1/chat/completions")
async def chat(request: Request) -> dict:
    body = await request.json()
    prompt = "\n".join(str(m.get("content", "")) for m in body.get("messages", []))
    content = _answer(prompt)
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "mock-model"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": len(prompt) // 4, "completion_tokens": len(content) // 4, "total_tokens": 0},
    }


@app.post("/v1/completions")
async def completions(request: Request) -> dict:
    body = await request.json()
    content = _answer(str(body.get("prompt", "")))
    return {"id": "cmpl-mock", "object": "text_completion", "choices": [{"index": 0, "text": content}]}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
