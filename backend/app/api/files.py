"""
Secure File and Document Processing Router.
Handles magic bytes file validation, private storage, text extraction,
real PDF compression, and CSV/Excel statistical analysis.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
import os

from app.database import get_db
from app.models.user import User
from app.models.organization import OrganizationMembership
from app.models.conversation import UploadedFile
from app.api.deps import get_current_user, get_current_membership
from app.services.file_processor import FileProcessor
from app.config import settings

router = APIRouter(prefix="/files", tags=["File & Document Processing"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """
    Secure file upload with magic bytes validation and text extraction.
    """
    content = await file.read()
    filename = file.filename or "uploaded_file"
    ext = os.path.splitext(filename)[1]

    # Validate content magic bytes
    is_valid, mime_or_err = FileProcessor.validate_file_content(content, ext)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"File validation failed: {mime_or_err}")

    # Save safely to isolated storage
    saved_meta = FileProcessor.save_file_safely(content, filename)

    # Extract text if document format
    extracted_text = ""
    if ext.lower() == ".pdf":
        extracted_text = FileProcessor.extract_text_from_pdf(content)
    elif ext.lower() in [".csv", ".txt"]:
        extracted_text = content.decode("utf-8", errors="replace")[:20000]

    # Persist record in database
    uploaded_rec = UploadedFile(
        organization_id=membership.organization_id,
        user_id=user.id,
        filename=saved_meta["filename"],
        original_filename=filename,
        file_type=mime_or_err,
        size_bytes=saved_meta["size_bytes"],
        storage_path=saved_meta["storage_path"],
        sha256_hash=saved_meta["sha256"],
        processing_status="PROCESSED",
        extracted_text=extracted_text
    )
    db.add(uploaded_rec)
    db.commit()
    db.refresh(uploaded_rec)

    return {
        "id": uploaded_rec.id,
        "filename": uploaded_rec.original_filename,
        "file_type": uploaded_rec.file_type,
        "size_bytes": uploaded_rec.size_bytes,
        "extracted_preview": extracted_text[:300] if extracted_text else ""
    }


@router.get("/")
def list_files(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """Lists files uploaded within current organization."""
    files = db.query(UploadedFile).filter(
        UploadedFile.organization_id == membership.organization_id
    ).order_by(UploadedFile.created_at.desc()).all()
    return [
        {
            "id": f.id,
            "filename": f.original_filename,
            "file_type": f.file_type,
            "size_bytes": f.size_bytes,
            "created_at": f.created_at
        }
        for f in files
    ]


@router.post("/compress")
async def compress_pdf_file(
    file: UploadFile = File(...),
    membership: OrganizationMembership = Depends(get_current_membership)
):
    """
    Compresses PDF file using content stream optimization and returns real measured savings.
    """
    content = await file.read()
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF documents are supported for PDF compression")

    result = FileProcessor.compress_pdf(content)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=f"Compression failed: {result.get('error')}")

    return {
        "filename": file.filename,
        "original_size_bytes": result["original_size"],
        "compressed_size_bytes": result["compressed_size"],
        "bytes_saved": result["reduction_bytes"],
        "reduction_percentage": result["reduction_percent"]
    }


@router.post("/analyze")
async def analyze_spreadsheet(
    file: UploadFile = File(...),
    membership: OrganizationMembership = Depends(get_current_membership)
):
    """
    Parses CSV or Excel spreadsheet, computes column metrics, row counts, and summary statistics.
    """
    content = await file.read()
    ext = os.path.splitext(file.filename or "")[1].lower()
    is_excel = ext in [".xlsx", ".xls"]
    if ext not in [".csv", ".xlsx", ".xls", ".txt"]:
        raise HTTPException(status_code=400, detail="Please upload a valid CSV or Excel file for data analysis")

    analysis = FileProcessor.analyze_tabular_data(content, is_excel=is_excel)
    return analysis


@router.delete("/{file_id}")
def delete_file(
    file_id: str,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """Deletes uploaded file and cleans up disk storage."""
    rec = db.query(UploadedFile).filter(
        UploadedFile.id == file_id,
        UploadedFile.organization_id == membership.organization_id
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="File not found")

    if os.path.exists(rec.storage_path):
        try:
            os.remove(rec.storage_path)
        except OSError:
            pass

    db.delete(rec)
    db.commit()
    return {"message": "File removed successfully"}
