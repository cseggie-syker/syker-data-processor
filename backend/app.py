"""FastAPI application exposing the DTL processing pipeline."""

from __future__ import annotations

import io
from typing import List

from fastapi import FastAPI, File, HTTPException, UploadFile
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


@app.post(
    "/process",
    summary="Convert uploaded DTL files to Excel",
    response_description="ZIP archive containing the converted Excel files",
)
async def process_files(files: List[UploadFile] = File(...)) -> StreamingResponse:
    """Accept one or more uploads and return a ZIP archive of Excel output."""

    if not files:
        raise HTTPException(status_code=400, detail="At least one file must be provided.")

    uploads: List[UploadedItem] = []
    for upload in files:
        contents = await upload.read()
        uploads.append(UploadedItem(filename=upload.filename or "uploaded.dtl", content=contents))

    try:
        result = processor.process_uploads(uploads)
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


