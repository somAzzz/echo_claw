#!/usr/bin/env python3
"""FunASR API server for speech recognition."""

import io
import logging
import struct
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FunASR API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ASRRequest(BaseModel):
    audio: bytes


class ASRResult(BaseModel):
    text: str
    duration: float = 0.0


# Global recognizer instance
_recognizer = None


def get_recognizer():
    """Get or create the sherpa-onnx recognizer."""
    global _recognizer
    if _recognizer is None:
        import sherpa_onnx
        model_dir = os.environ.get("MODEL_DIR", "/app/models")

        # Check for paraformer model
        encoder = f"{model_dir}/asr/encoder.onnx"
        decoder = f"{model_dir}/asr/decoder.onnx"
        tokens = f"{model_dir}/asr/tokens.txt"

        if not os.path.exists(encoder):
            raise FileNotFoundError(f"Model not found: {encoder}")

        recognizer = sherpa_onnx.OfflineRecognizer.create(
            encoder=encoder,
            decoder=decoder,
            tokens=tokens,
        )
        _recognizer = recognizer
        logger.info("ASR recognizer initialized")
    return _recognizer


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/asr/json", response_model=ASRResult)
def recognize(audio_data: bytes):
    """Recognize speech from PCM audio data.

    Expects raw PCM audio (16-bit, 16kHz, mono).
    """
    try:
        import sherpa_onnx

        recognizer = get_recognizer()

        # Create audio stream from bytes
        audio = io.BytesIO(audio_data)

        # Get audio duration (assuming 16kHz, 16-bit mono)
        duration = len(audio_data) / (16000 * 2)  # bytes / (sample_rate * bytes_per_sample)

        # Process audio
        recognizer.accept_waveform(audio.read())
        result = recognizer.get_result()

        text = result if result else ""

        return ASRResult(text=text, duration=duration)

    except Exception as e:
        logger.error(f"ASR error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/asr/file")
def recognize_file():
    """Alternative endpoint accepting multipart file upload."""
    return {"status": "not implemented"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)