"""
Secure File Processor and Document Analysis Engine.
Implements:
1. Magic bytes signature validation (never trusts file extensions).
2. Size restrictions and path traversal prevention using random UUID keys.
3. Real PDF text extraction, document compression with measured size reduction.
4. CSV / Excel statistical data analysis.
"""

import os
import io
import csv
import uuid
import hashlib
from typing import Dict, Any, Tuple
from pypdf import PdfReader, PdfWriter
import openpyxl

from app.config import settings

# Magic byte signatures
MAGIC_SIGNATURES = {
    "pdf": b"%PDF",
    "png": b"\x89PNG\r\n\x1a\n",
    "jpeg": b"\xff\xd8\xff",
    "xlsx": b"PK\x03\x04",
}


class FileProcessor:
    @staticmethod
    def validate_file_content(content: bytes, declared_extension: str) -> Tuple[bool, str]:
        """
        Validates content using magic bytes signature inspection.
        Returns (is_valid, normalized_file_type).
        """
        if len(content) > settings.MAX_FILE_SIZE_BYTES:
            return False, "File exceeds maximum permitted size limit"

        ext = declared_extension.lower().lstrip(".")

        if ext == "pdf":
            if content.startswith(MAGIC_SIGNATURES["pdf"]):
                return True, "application/pdf"
            return False, "Invalid PDF magic bytes signature"

        elif ext in ["png"]:
            if content.startswith(MAGIC_SIGNATURES["png"]):
                return True, "image/png"
            return False, "Invalid PNG magic bytes signature"

        elif ext in ["jpg", "jpeg"]:
            if content.startswith(MAGIC_SIGNATURES["jpeg"]):
                return True, "image/jpeg"
            return False, "Invalid JPEG magic bytes signature"

        elif ext == "xlsx":
            if content.startswith(MAGIC_SIGNATURES["xlsx"]):
                return True, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            return False, "Invalid XLSX signature"

        elif ext in ["csv", "txt"]:
            # Check for non-binary content (no zero bytes in first 1024 bytes)
            sample = content[:1024]
            if b"\x00" in sample:
                return False, "Binary characters detected in plaintext file"
            return True, "text/csv" if ext == "csv" else "text/plain"

        return False, f"Unsupported file format: {ext}"

    @staticmethod
    def save_file_safely(content: bytes, original_filename: str) -> Dict[str, Any]:
        """
        Saves file to isolated storage using random UUID filename.
        Calculates SHA-256 integrity hash.
        """
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        ext = os.path.splitext(original_filename)[1].lower()
        storage_filename = f"{uuid.uuid4().hex}{ext}"
        storage_path = os.path.join(settings.UPLOAD_DIR, storage_filename)

        with open(storage_path, "wb") as f:
            f.write(content)

        sha256 = hashlib.sha256(content).hexdigest()

        return {
            "storage_path": storage_path,
            "filename": storage_filename,
            "sha256": sha256,
            "size_bytes": len(content)
        }

    @staticmethod
    def extract_text_from_pdf(content: bytes) -> str:
        """Extracts text content from PDF file."""
        try:
            stream = io.BytesIO(content)
            reader = PdfReader(stream)
            extracted = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    extracted.append(f"--- Page {i+1} ---\n{text.strip()}")
            return "\n\n".join(extracted) if extracted else "No extractable text found in PDF document."
        except Exception as e:
            return f"Error extracting text from PDF: {str(e)}"

    @staticmethod
    def compress_pdf(content: bytes) -> Dict[str, Any]:
        """
        Performs PDF compression by optimizing content streams and removing duplicate objects.
        Returns original size, new size, and reduction percentage.
        """
        try:
            original_size = len(content)
            reader = PdfReader(io.BytesIO(content))
            writer = PdfWriter()

            for page in reader.pages:
                page.compress_content_streams()
                writer.add_page(page)

            out_stream = io.BytesIO()
            writer.write(out_stream)
            compressed_bytes = out_stream.getvalue()
            compressed_size = len(compressed_bytes)

            reduction_bytes = max(0, original_size - compressed_size)
            reduction_percent = round((reduction_bytes / original_size) * 100, 2) if original_size > 0 else 0.0

            return {
                "success": True,
                "original_size": original_size,
                "compressed_size": compressed_size,
                "reduction_bytes": reduction_bytes,
                "reduction_percent": reduction_percent,
                "compressed_data": compressed_bytes
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "original_size": len(content),
                "compressed_size": len(content),
                "reduction_percent": 0.0
            }

    @staticmethod
    def analyze_tabular_data(content: bytes, is_excel: bool = False) -> Dict[str, Any]:
        """
        Analyzes CSV or Excel spreadsheets and computes statistical summaries.
        """
        try:
            headers = []
            rows = []
            if is_excel:
                wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
                sheet = wb.active
                data_gen = sheet.iter_rows(values_only=True)
                headers = [str(h) for h in next(data_gen, []) if h is not None]
                for row in data_gen:
                    if any(c is not None for c in row):
                        rows.append([str(c) if c is not None else "" for c in row[:len(headers)]])
            else:
                text_stream = io.StringIO(content.decode("utf-8", errors="replace"))
                reader = csv.reader(text_stream)
                headers = next(reader, [])
                for row in reader:
                    if row:
                        rows.append(row)

            row_count = len(rows)
            col_count = len(headers)

            # Analyze numeric columns
            numeric_stats = {}
            for col_idx, col_name in enumerate(headers):
                values = []
                for row in rows:
                    if col_idx < len(row):
                        try:
                            v = float(row[col_idx].strip().replace(",", ""))
                            values.append(v)
                        except ValueError:
                            pass
                if len(values) >= max(3, int(row_count * 0.5)):
                    numeric_stats[col_name] = {
                        "count": len(values),
                        "mean": round(sum(values) / len(values), 2),
                        "min": min(values),
                        "max": max(values),
                    }

            summary_md = (
                f"### Spreadsheet Analysis Summary\n"
                f"- **Rows:** {row_count:,}\n"
                f"- **Columns ({col_count}):** {', '.join(headers[:10])}{'...' if col_count > 10 else ''}\n\n"
            )
            if numeric_stats:
                summary_md += "#### Key Column Statistics:\n"
                for col, stats in numeric_stats.items():
                    summary_md += f"- **{col}:** Min = {stats['min']}, Mean = {stats['mean']}, Max = {stats['max']} (Sample: {stats['count']})\n"

            return {
                "success": True,
                "row_count": row_count,
                "col_count": col_count,
                "headers": headers,
                "preview_rows": rows[:5],
                "numeric_stats": numeric_stats,
                "summary_markdown": summary_md
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "summary_markdown": f"Failed to analyze data: {str(e)}"
            }
