"""Voice — text-to-speech via Microsoft Edge TTS (gratuito, sem key).

Backend: edge-tts (Microsoft Edge neural voices).
Vozes PT-PT: pt-PT-RaquelNeural, pt-PT-DuarteNeural.
Vozes EN: en-US-AriaNeural, en-US-GuyNeural.

Output: MP3 file no workspace.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from .config import DATA
from .util import now_iso

VOICE_PT = "pt-PT-RaquelNeural"
VOICE_EN = "en-US-AriaNeural"
VOICES = {
    "pt": VOICE_PT,
    "pt-PT": VOICE_PT,
    "pt-BR": "pt-BR-FranciscaNeural",
    "en": VOICE_EN,
    "en-US": VOICE_EN,
    "en-GB": "en-GB-SoniaNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
}

OUTPUT_DIR = DATA / "voice"


def _get_voice(lang: str = "pt") -> str:
    """Get voice for language."""
    return VOICES.get(lang, VOICE_PT)


def speak(text: str, lang: str = "pt", voice: str | None = None) -> dict:
    """Convert text to speech. Returns dict with file path and metadata."""
    if not text or not text.strip():
        return {"status": "error", "error": "texto vazio", "kind": "MEASURED"}

    voice_id = voice or _get_voice(lang)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Generate filename
    import hashlib
    ts = now_iso().replace(":", "").replace("-", "")[:15]
    h = hashlib.md5(text.encode()).hexdigest()[:8]
    filename = f"tts_{ts}_{h}.mp3"
    filepath = OUTPUT_DIR / filename

    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice_id)
        asyncio.run(communicate.save(str(filepath)))
    except Exception as e:
        return {"status": "error", "error": str(e)[:300], "kind": "MEASURED"}

    if not filepath.exists() or filepath.stat().st_size == 0:
        return {"status": "error", "error": "ficheiro vazio ou não criado", "kind": "MEASURED"}

    return {
        "status": "success",
        "kind": "MEASURED",
        "file": str(filepath),
        "filename": filename,
        "size_bytes": filepath.stat().st_size,
        "voice": voice_id,
        "lang": lang,
        "text_length": len(text),
        "ts": now_iso(),
    }


def list_voices(lang: str | None = None) -> dict:
    """List available voices."""
    try:
        import edge_tts
        voices = asyncio.run(edge_tts.list_voices())
        if lang:
            voices = [v for v in voices if v["Locale"].startswith(lang)]
        return {
            "kind": "MEASURED",
            "n": len(voices),
            "voices": [{"name": v["ShortName"], "lang": v["Locale"], "gender": v["Gender"]} for v in voices[:20]],
        }
    except Exception as e:
        return {"kind": "ERROR", "error": str(e)[:200]}


def health() -> dict:
    """Check if TTS is available."""
    try:
        import edge_tts
        return {
            "kind": "MEASURED",
            "available": True,
            "backend": "edge-tts (Microsoft Edge neural voices)",
            "default_voice": VOICE_PT,
            "supported_langs": list(VOICES.keys()),
            "ts": now_iso(),
        }
    except ImportError:
        return {
            "kind": "MEASURED",
            "available": False,
            "backend": "edge-tts not installed",
            "error": "pip install edge-tts",
            "ts": now_iso(),
        }
