import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["internal"])

_DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
_DRIVE_LIST_URL = "https://www.googleapis.com/drive/v3/files"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


async def _get_drive_token() -> str:
    """Exchange refresh token for access token using Google OAuth2."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(_GOOGLE_TOKEN_URL, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": settings.google_drive_refresh_token,
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        return resp.json()["access_token"]


class DriveUploadRequest(BaseModel):
    filename: str
    content: str
    mime_type: Optional[str] = "text/plain"


class SendEmailRequest(BaseModel):
    to: Optional[str] = None
    subject: str
    body_html: Optional[str] = None
    body_text: Optional[str] = None


@router.post("/drive/upload")
async def drive_upload(req: DriveUploadRequest):
    try:
        token = await _get_drive_token()
    except Exception as exc:
        logger.error("Drive token fetch failed: %s", exc)
        return JSONResponse(status_code=500, content={"detail": f"Auth failed: {exc}"})

    metadata = {"name": req.filename}
    if settings.google_drive_folder_id:
        metadata["parents"] = [settings.google_drive_folder_id]

    import json
    body = (
        f'--boundary\r\nContent-Type: application/json\r\n\r\n{json.dumps(metadata)}\r\n'
        f'--boundary\r\nContent-Type: {req.mime_type}\r\n\r\n{req.content}\r\n'
        f'--boundary--'
    ).encode()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _DRIVE_UPLOAD_URL,
            content=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": 'multipart/related; boundary="boundary"',
            },
        )

    if resp.status_code not in (200, 201):
        logger.error("Drive upload failed: %s", resp.text[:200])
        return JSONResponse(status_code=500, content={"detail": resp.text[:200]})

    file_id = resp.json().get("id", "")
    logger.info("Drive upload ok filename=%s file_id=%s", req.filename, file_id)
    return {"status": "ok", "file_id": file_id}


@router.get("/drive/files")
async def drive_list_files():
    try:
        token = await _get_drive_token()
    except Exception as exc:
        logger.error("Drive token fetch failed: %s", exc)
        return JSONResponse(status_code=500, content={"detail": f"Auth failed: {exc}"})

    params = {"fields": "files(id,name,modifiedTime)", "orderBy": "modifiedTime desc"}
    if settings.google_drive_folder_id:
        params["q"] = f"'{settings.google_drive_folder_id}' in parents and trashed=false"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _DRIVE_LIST_URL,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )

    if resp.status_code != 200:
        logger.error("Drive list failed: %s", resp.text[:200])
        return JSONResponse(status_code=500, content={"detail": resp.text[:200]})

    files = [
        {"id": f["id"], "name": f["name"], "modified_at": f.get("modifiedTime", "")}
        for f in resp.json().get("files", [])
    ]
    return {"files": files}


_DOCS_EXPORT_URL = "https://docs.googleapis.com/v1/documents/{doc_id}"


async def _get_docs_token() -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(_GOOGLE_TOKEN_URL, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": settings.google_docs_refresh_token,
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        return resp.json()["access_token"]


def _extract_doc_text(doc: dict) -> str:
    """Walk the document body and extract plain text."""
    parts = []
    for elem in doc.get("body", {}).get("content", []):
        para = elem.get("paragraph")
        if not para:
            continue
        for pe in para.get("elements", []):
            text_run = pe.get("textRun")
            if text_run:
                parts.append(text_run.get("content", ""))
    return "".join(parts)


@router.get("/docs/{doc_id}")
async def read_doc(doc_id: str):
    try:
        token = await _get_docs_token()
    except Exception as exc:
        logger.error("Docs token fetch failed: %s", exc)
        return JSONResponse(status_code=500, content={"detail": f"Auth failed: {exc}"})

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _DOCS_EXPORT_URL.format(doc_id=doc_id),
            headers={"Authorization": f"Bearer {token}"},
        )

    if resp.status_code == 404:
        return JSONResponse(status_code=404, content={"detail": "Document not found"})
    if resp.status_code != 200:
        logger.error("Docs fetch failed doc_id=%s: %s", doc_id, resp.text[:200])
        return JSONResponse(status_code=500, content={"detail": resp.text[:200]})

    content = _extract_doc_text(resp.json())
    logger.info("Docs read ok doc_id=%s chars=%d", doc_id, len(content))
    return {"doc_id": doc_id, "content": content}


@router.post("/send-email")
def send_email(req: SendEmailRequest):
    recipient = req.to or settings.report_email_to

    msg = MIMEMultipart("alternative")
    msg["Subject"] = req.subject
    msg["From"] = settings.smtp_user
    msg["To"] = recipient

    if req.body_text:
        msg.attach(MIMEText(req.body_text, "plain"))
    if req.body_html:
        msg.attach(MIMEText(req.body_html, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, 587) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_user, recipient, msg.as_string())

        logger.info("Email sent to=%s subject=%s", recipient, req.subject)
        return {"status": "ok"}

    except Exception as exc:
        logger.error("Failed to send email to=%s: %s", recipient, exc)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(exc)},
        )
