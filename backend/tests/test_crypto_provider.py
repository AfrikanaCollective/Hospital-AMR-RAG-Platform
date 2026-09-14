"""FileKEKProvider envelope encryption (ARCH-032, ARCH-033)."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from app.crypto.provider import FileKEKProvider


def test_roundtrip(tmp_path: Path) -> None:
    provider = FileKEKProvider(str(tmp_path / "kek.bin"))
    pt = b"structured patient record json"
    ct = provider.encrypt(pt)
    assert ct != pt
    assert provider.decrypt(ct) == pt


def test_kek_persists_across_instances(tmp_path: Path) -> None:
    kek_path = str(tmp_path / "kek.bin")
    p1 = FileKEKProvider(kek_path)
    ct = p1.encrypt(b"hello")
    p2 = FileKEKProvider(kek_path)
    assert p2.decrypt(ct) == b"hello"


def test_kek_file_created_with_owner_only_permissions(tmp_path: Path) -> None:
    kek_path = tmp_path / "kek.bin"
    FileKEKProvider(str(kek_path))
    mode = kek_path.stat().st_mode & 0o777
    assert mode == 0o600


def test_aad_binds_ciphertext_to_context(tmp_path: Path) -> None:
    provider = FileKEKProvider(str(tmp_path / "kek.bin"))
    ct = provider.encrypt(b"payload", aad=b"row-1")
    assert provider.decrypt(ct, aad=b"row-1") == b"payload"
    with pytest.raises(InvalidTag):
        provider.decrypt(ct, aad=b"row-2")


def test_nonce_differs_each_call(tmp_path: Path) -> None:
    provider = FileKEKProvider(str(tmp_path / "kek.bin"))
    ct1 = provider.encrypt(b"same plaintext")
    ct2 = provider.encrypt(b"same plaintext")
    assert ct1 != ct2  # random nonce per call, even for identical plaintext


def test_malformed_kek_file_rejected(tmp_path: Path) -> None:
    kek_path = tmp_path / "kek.bin"
    kek_path.write_bytes(b"too-short")
    with pytest.raises(RuntimeError):
        FileKEKProvider(str(kek_path))


def test_deterministic_hash_is_stable_for_the_same_input(tmp_path: Path) -> None:
    provider = FileKEKProvider(str(tmp_path / "kek.bin"))
    h1 = provider.deterministic_hash(b"DEID-12345")
    h2 = provider.deterministic_hash(b"DEID-12345")
    assert h1 == h2
    assert len(h1) == 64  # hex-encoded SHA-256


def test_deterministic_hash_differs_for_different_input(tmp_path: Path) -> None:
    provider = FileKEKProvider(str(tmp_path / "kek.bin"))
    assert provider.deterministic_hash(b"DEID-1") != provider.deterministic_hash(b"DEID-2")


def test_deterministic_hash_differs_across_keks(tmp_path: Path) -> None:
    p1 = FileKEKProvider(str(tmp_path / "kek1.bin"))
    p2 = FileKEKProvider(str(tmp_path / "kek2.bin"))
    assert p1.deterministic_hash(b"same-mrn") != p2.deterministic_hash(b"same-mrn")


def test_deterministic_hash_is_not_the_raw_kek_or_encrypt_output(tmp_path: Path) -> None:
    provider = FileKEKProvider(str(tmp_path / "kek.bin"))
    h = provider.deterministic_hash(b"DEID-12345")
    assert h != provider._kek.hex()  # domain-separated via HKDF, not the raw KEK
