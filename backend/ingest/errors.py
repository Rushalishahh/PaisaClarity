"""
Structured errors raised by the ingestion pipeline.

Each carries a machine-readable `code`, an HTTP status, and a human-readable
message so the API layer can translate them 1:1 into JSON error responses
(see main.py) and the frontend can show exactly the right UI (password
prompt, column-mapping modal, scanned-PDF message...).
"""


class IngestError(Exception):
    """Base class - always has an HTTP status, a code and a message."""

    http_status = 422
    code = "ingest_error"

    def __init__(self, message, **extra):
        super().__init__(message)
        self.message = message
        # Extra payload keys (e.g. headers/sample_rows for mapping_required).
        self.extra = extra

    def to_payload(self):
        return {"code": self.code, "message": self.message, **self.extra}


class UnsupportedFormat(IngestError):
    """Content doesn't match the extension, or the type is not supported at all."""

    http_status = 415
    code = "unsupported_format"


class FileTooLarge(IngestError):
    http_status = 413
    code = "file_too_large"


class CorruptFile(IngestError):
    """The file exists but cannot be opened/read (truncated, not really a PDF...)."""

    http_status = 422
    code = "corrupt_file"


class PasswordRequired(IngestError):
    """The PDF is encrypted and no password was supplied."""

    http_status = 422
    code = "password_required"


class WrongPassword(IngestError):
    """A password was supplied but it does not decrypt the PDF."""

    http_status = 422
    code = "wrong_password"


class ScannedPdfUnsupported(IngestError):
    """No extractable text - the PDF is a scan/image. OCR is out of scope."""

    http_status = 422
    code = "scanned_pdf"


class MappingRequired(IngestError):
    """
    The transaction table was found but its columns could not be identified
    with confidence. Carries the raw headers and a few sample rows so the
    frontend can render the manual column-mapping modal.
    """

    http_status = 422
    code = "mapping_required"

    def __init__(self, message, headers=None, sample_rows=None):
        super().__init__(message, headers=headers or [], sample_rows=sample_rows or [])


class NoTransactions(IngestError):
    """The file parsed, but zero rows qualified as transactions."""

    http_status = 422
    code = "no_transactions"

    def __init__(self, message, report=None):
        super().__init__(message, report=report or {})
