"""CryptoProvider — envelope encryption abstraction (ARCH-032, ARCH-033).

`get_crypto()` returns a provider bound to the KEK from SECRETS_BACKEND. The
`file` backend (dev default) loads a local KEK and logs a prominent
"DEV KEY — not for real data" warning. Key rotation re-wraps DEKs (documented,
not automated in MVP).

`FileKEKProvider` implements AES-256-GCM envelope encryption: a random 32-byte
KEK is generated on first use and persisted at `crypto_kek_file` (0600), a
fresh random 12-byte nonce is generated per call and prepended to the
ciphertext (`nonce || ciphertext_with_tag`) so `encrypt` never needs external
state beyond the KEK itself. `aad` (e.g. a row's stable id) binds the
ciphertext to its row so blobs cannot be swapped between rows undetected.

`deterministic_hash` (DEVIATIONS.md #57) supports **lookup** on an otherwise
always-encrypted identifier (e.g. `patient.mrn_hash`, used to dedupe on MRN
without ever storing or comparing plaintext): HMAC-SHA256 with a key derived
from the KEK via HKDF (domain-separated from the AEAD key so a lookup hash
can never be used to help recover the encryption key), so equal inputs
produce equal, stable hashes without needing a nonce — the point of a lookup
index — while still requiring the KEK to compute or verify one.
"""

from __future__ import annotations

import hmac as hmac_module
import os
import stat
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

_KEY_LEN = 32  # AES-256
_NONCE_LEN = 12  # 96-bit GCM nonce, NIST-recommended
_HKDF_INFO_LOOKUP_HMAC = b"hospital-rag-platform:lookup-hmac:v1"


class CryptoProvider(Protocol):
    def encrypt(self, plaintext: bytes, *, aad: bytes | None = None) -> bytes: ...
    def decrypt(self, ciphertext: bytes, *, aad: bytes | None = None) -> bytes: ...
    def deterministic_hash(self, data: bytes) -> str: ...


class FileKEKProvider:
    def __init__(self, kek_path: str) -> None:
        self.kek_path = kek_path
        logger.warning(
            "SECRETS_BACKEND=file: using a local DEV KEY at %s. DEV KEY — not for real data. "
            "This deployment must not touch real PHI.",
            kek_path,
        )
        self._kek = self._load_or_create_kek(kek_path)
        self._aesgcm = AESGCM(self._kek)
        self._lookup_hmac_key = HKDF(
            algorithm=hashes.SHA256(), length=_KEY_LEN, salt=None, info=_HKDF_INFO_LOOKUP_HMAC
        ).derive(self._kek)

    @staticmethod
    def _load_or_create_kek(path: str) -> bytes:
        p = Path(path)
        if p.exists():
            key = p.read_bytes()
            if len(key) != _KEY_LEN:
                raise RuntimeError(
                    f"KEK file {path!r} is {len(key)} bytes, expected {_KEY_LEN} "
                    "(AES-256 key). Refusing to use a malformed dev key."
                )
            return key
        p.parent.mkdir(parents=True, exist_ok=True)
        key = os.urandom(_KEY_LEN)
        p.write_bytes(key)
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600 — owner read/write only
        logger.warning("Generated a new dev KEK at %s (0600). Not for real data.", path)
        return key

    def encrypt(self, plaintext: bytes, *, aad: bytes | None = None) -> bytes:
        nonce = os.urandom(_NONCE_LEN)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, aad)
        return nonce + ciphertext

    def decrypt(self, ciphertext: bytes, *, aad: bytes | None = None) -> bytes:
        if len(ciphertext) < _NONCE_LEN:
            raise ValueError("ciphertext too short to contain a nonce")
        nonce, body = ciphertext[:_NONCE_LEN], ciphertext[_NONCE_LEN:]
        return self._aesgcm.decrypt(nonce, body, aad)

    def deterministic_hash(self, data: bytes) -> str:
        return hmac_module.new(self._lookup_hmac_key, data, "sha256").hexdigest()


def get_crypto() -> CryptoProvider:
    s = get_settings()
    if s.secrets_backend == "file":
        return FileKEKProvider(s.crypto_kek_file)
    raise NotImplementedError(f"Phase 4: SECRETS_BACKEND={s.secrets_backend!r} (env | vault)")
