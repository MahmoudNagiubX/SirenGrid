"""Approved Groq ASR adapter, isolated from report persistence."""

from __future__ import annotations

import os
from pathlib import Path

from app.ai import ProviderCallError


def configured_groq_transcriber(path: Path, model: str, timeout: float) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ProviderCallError("credential_unavailable")
    from feasibility.providers import transcribe_audio

    return transcribe_audio(
        path,
        model=model,
        api_key=api_key,
        timeout=timeout,
    )
