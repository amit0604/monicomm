"""ChatIAF REST API: POST /api/v1/chat."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.ai.llm_client import ExternalEndpointError, LLMUnavailable
from app.modules.chat import service
from app.modules.dashboard.router import SourceDep

MAX_BODY_BYTES = 512 * 1024
log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

# The body is read by hand because FastAPI would load all of it before any size check.
BODY_SCHEMA = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": service.ChatRequest.model_json_schema()}},
    }
}


@router.post("", openapi_extra=BODY_SCHEMA)
async def chat(request: Request, source: SourceDep) -> service.ChatReply:
    # A JSON content type forces a CORS preflight, so other sites cannot post here.
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise HTTPException(415, "json_required")
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_BODY_BYTES:
            raise HTTPException(413, "too_large")
    try:
        body = service.ChatRequest.model_validate_json(bytes(raw))
        return await service.answer(source, body.messages)
    except (ValidationError, service.InvalidConversation):
        raise HTTPException(400, "invalid_messages") from None
    except (service.ExternalModelRefused, ExternalEndpointError):
        log.error("chat: the configured model may not be used here")
        raise HTTPException(503, "not_allowed") from None
    except LLMUnavailable as e:
        log.warning("chat: %s", e)
        raise HTTPException(503, "llm_unavailable") from None
