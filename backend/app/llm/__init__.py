"""LLM access (ARCH-005; PRD-101, PRD-102).

Everything goes through `LLMGateway`. Model ids come from config
(`MODEL_ID` + `MODEL_ID_FALLBACKS`). No module in this package names a model.
PHI-bearing prompts are only ever sent to the configured self-hosted gateway.
"""
