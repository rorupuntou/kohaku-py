"""Custom exceptions for saga-sync."""


class SagaError(Exception):
    """Base exception for all saga-sync errors."""


class ManifestError(SagaError):
    """Raised when the manifest cannot be fetched or parsed."""


class ProtocolNotFoundError(SagaError):
    """Raised when a requested protocol is not present in the manifest."""


class ChecksumMismatchError(SagaError):
    """Raised when a chunk's uncompressed sha256 does not match the manifest digest."""

    def __init__(self, filename: str, expected: str, actual: str):
        super().__init__(
            f"Checksum mismatch for '{filename}': expected {expected}, computed {actual}"
        )
        self.filename = filename
        self.expected = expected
        self.actual = actual


class ChunkDownloadError(SagaError):
    """Raised when downloading a chunk fails."""
