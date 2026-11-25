"""Chatchup REST API. Mounted by the app under /api/v1/pcap (plan assumption A2)."""

import ipaddress
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from . import parser, service

router = APIRouter(tags=["pcap"])
CHUNK = 1024 * 1024
MULTIPART_OVERHEAD = 64 * 1024  # boundaries + part headers around the file

UPLOAD_SCHEMA = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {"file": {"type": "string", "format": "binary"}},
                }
            }
        },
    }
}


def _found(fn, *args):
    try:
        return fn(*args)
    except service.NotFound:
        raise HTTPException(404, "capture not found") from None


def _too_big():
    mb = service.MAX_UPLOAD_BYTES // (1024 * 1024)
    return HTTPException(413, f"file larger than {mb} MB")


@router.post("/captures", status_code=202, openapi_extra=UPLOAD_SCHEMA)
async def upload(request: Request, background: BackgroundTasks):
    # Starlette spools the whole multipart body to disk before a handler sees it, so the
    # size check must happen here, on the header, before parsing. nginx should enforce it too.
    length = request.headers.get("content-length")
    if length is None:
        raise HTTPException(411, "Content-Length required")
    if (
        not length.isdigit()
        or int(length) > service.MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD
    ):
        raise _too_big()

    form = await request.form()
    file = form.get("file")
    if not isinstance(file, UploadFile):
        raise HTTPException(400, "multipart field 'file' required")
    name = file.filename or "capture"
    if not name.lower().endswith(service.ALLOWED_SUFFIXES):
        raise HTTPException(400, f"only {', '.join(service.ALLOWED_SUFFIXES)} files")
    head = await file.read(4)
    if not parser.is_capture(head):
        raise HTTPException(400, "not a pcap/pcapng file")

    capture_id, path = service.new_capture(name)
    size = len(head)
    try:
        out = await run_in_threadpool(open, path, "wb")  # file I/O off the event loop
        try:
            await run_in_threadpool(out.write, head)
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > service.MAX_UPLOAD_BYTES:
                    raise _too_big()
                await run_in_threadpool(out.write, chunk)
        finally:
            out.close()
    except (
        BaseException
    ):  # too big, disconnect, disk full: never leave a half capture behind
        service.delete_capture(capture_id)
        raise

    meta = service.set_meta(capture_id, status="queued", size=size)
    background.add_task(service.process, capture_id)
    return meta


@router.get("/captures")
def list_captures():
    return service.list_captures()


@router.get("/captures/{capture_id}")
def get_capture(capture_id: str):
    return _found(service.get_capture, capture_id)


@router.get("/captures/{capture_id}/conversations")
def conversations(
    capture_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=5000),
):
    return _found(service.conversations, capture_id, offset, limit)


# ---- network views (graph tab). t_start/t_end: seconds from the first packet ----------------------


@router.get("/captures/{capture_id}/graph")
def graph(
    capture_id: str,
    protocol: Literal["", "TCP", "UDP", "ICMP"] = "",
    min_packets: int = Query(1, ge=1),
    t_start: float | None = Query(None, ge=0),
    t_end: float | None = Query(None, ge=0),
):
    return _found(service.graph, capture_id, protocol, min_packets, t_start, t_end)


@router.get("/captures/{capture_id}/overview")
def overview(
    capture_id: str,
    t_start: float | None = Query(None, ge=0),
    t_end: float | None = Query(None, ge=0),
):
    return _found(service.overview, capture_id, t_start, t_end)


@router.get("/captures/{capture_id}/timeline")
def timeline(capture_id: str):
    return _found(service.timeline, capture_id)


@router.get("/captures/{capture_id}/hosts/{ip}")
def host(capture_id: str, ip: str):
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise HTTPException(400, "not an IP address") from None
    return _found(service.host, capture_id, ip)


@router.get("/captures/{capture_id}/streams/{conv_id}")
def follow_stream(capture_id: str, conv_id: int):
    return _found(service.stream, capture_id, conv_id)


@router.delete("/captures/{capture_id}", status_code=204)
def delete_capture(capture_id: str):
    _found(service.delete_capture, capture_id)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


async def _ai(coro):
    try:
        return await coro
    except service.NotFound:
        raise HTTPException(404, "capture not found or not analyzed yet") from None
    except service.LLMUnavailable:
        raise HTTPException(
            503, "the local AI model is not available right now; try again"
        ) from None


@router.post("/captures/{capture_id}/summary")
async def summary(capture_id: str, refresh: bool = False):
    return await _ai(service.summary(capture_id, refresh))


@router.get("/captures/{capture_id}/chat")
def chat_history(capture_id: str):
    return _found(service.chat_history, capture_id)


@router.post("/captures/{capture_id}/chat")
async def chat(capture_id: str, body: Question):
    return await _ai(service.chat(capture_id, body.question))
