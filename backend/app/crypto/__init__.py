"""Encryption at rest (ARCH-032, ARCH-033; PRD-083).

Envelope encryption (AES-256-GCM): a data-encryption key wrapped by a
key-encryption key from SECRETS_BACKEND (env | file | vault). Applied to the
PHI free-text/blob fields enumerated in ARCHITECTURE.md §17.2.
"""
