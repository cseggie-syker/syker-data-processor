"""FastAPI application exposing the DTL processing pipeline."""

from __future__ import annotations

import io
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .dtl_processor_web import DTLProcessingError, DTLWebProcessor, UploadedItem


app = FastAPI(
    title="Syker DTL Processor API",
    description="Serverless API for converting Syker .dtl files into Excel workbooks.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

processor = DTLWebProcessor()


@app.get("/health", summary="Health check")
async def health_check() -> dict[str, str]:
    """Simple endpoint for uptime monitoring."""

    return {"status": "ok"}


async def _handle_conversion(files: List[UploadFile], archive_label: Optional[str] = None) -> StreamingResponse:
    if not files:
        raise HTTPException(status_code=400, detail="At least one file must be provided.")

    uploads: List[UploadedItem] = []
    for upload in files:
        contents = await upload.read()
        uploads.append(UploadedItem(filename=upload.filename or "uploaded.dtl", content=contents))

    try:
        result = processor.process_uploads(uploads, archive_label=archive_label)
    except DTLProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stream = io.BytesIO(result.zip_bytes)
    headers = {
        "Content-Disposition": f"attachment; filename={result.zip_filename}",
        "X-Recognized-Files": str(result.summary.recognized_files),
        "X-Unrecognized-Files": str(result.summary.unrecognized_files),
    }

    return StreamingResponse(
        stream,
        media_type="application/zip",
        headers=headers,
    )


@app.post(
    "/process",
    summary="Convert uploaded DTL files to Excel",
    response_description="ZIP archive containing the converted Excel files",
)
async def process_files(files: List[UploadFile] = File(...), archive_label: Optional[str] = Form(None)) -> StreamingResponse:
    """Accept one or more uploads and return a ZIP archive of Excel output."""

    return await _handle_conversion(files, archive_label)


@app.post("/")
async def process_files_root(files: List[UploadFile] = File(...), archive_label: Optional[str] = Form(None)) -> StreamingResponse:
    """Alias route for deployments where the function is mounted at /api/process."""

    return await _handle_conversion(files, archive_label)


@app.post("/api/process")
async def process_files_api(files: List[UploadFile] = File(...), archive_label: Optional[str] = Form(None)) -> StreamingResponse:
    """Additional alias for platforms that forward the full path."""

    return await _handle_conversion(files, archive_label)


