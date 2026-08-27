"""Capability-scope enforcement (ARCH-025; SCOPE-2.3, SCOPE-2.4, CDS-FUTURE.md).

The scope-classifier labels every incoming query. Queries classified as
SCOPE-2.3 / SCOPE-2.4 intent are NEVER answered — they route straight to
escalation (trigger_code = scope_boundary). This is a hard boundary.
"""
