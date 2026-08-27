"""CryptoProvider — envelope encryption abstraction (ARCH-032, ARCH-033).

`get_crypto()` returns a provider bound to the KEK from SECRETS_BACKEND. The
`file` backend (dev default) loads a local KEK and logs a prominent
"DEV KEY — not for real data" warning. Key rotation re-wraps DEKs (documented,
not automated in MVP).

Phase 2/4 implement encrypt/decrypt with the `cryptography` package. The
interface is fixed now.
"""

from __future__ import annotations

from typing import Protocol

from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)


class CryptoProvider(Protocol):
    def encrypt(self, plaintext: bytes, *, aad: bytes | None = None) -> bytes: ...
    def decrypt(self, ciphertext: bytes, *, aad: bytes | None = None) -> bytes: ...


class FileKEKProvider:
    def __init__(self, kek_path: str) -> None:
        self.kek_path = kek_path
        logger.warning(
            "SECRETS_BACKEND=file: using a local DEV KEY at %s. DEV KEY — not for real data. "
            "This deployment must not touch real PHI.",
            kek_path,
        )

    def encrypt(self, plaintext: bytes, *, aad: bytes | None = None) -> bytes:
        raise NotImplementedError("Phase 2 (AES-256-GCM envelope encryption)")

    def decrypt(self, ciphertext: bytes, *, aad: bytes | None = None) -> bytes:
        raise NotImplementedError("Phase 2")


def get_crypto() -> CryptoProvider:
    s = get_settings()
    if s.secrets_backend == "file":
        return FileKEKProvider(s.crypto_kek_file)
    raise NotImplementedError(f"Phase 4: SECRETS_BACKEND={s.secrets_backend!r} (env | vault)")
