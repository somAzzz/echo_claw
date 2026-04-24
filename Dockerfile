FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    edge-tts \
    websockets \
    pyyaml \
    aiohttp \
    pydantic \
    httpx \
    pytest \
    pytest-asyncio \
    fastapi \
    "uvicorn[standard]" \
    python-multipart

COPY src/ ./src/
COPY config.yaml .

EXPOSE 8765 8766

CMD ["python", "-m", "src.main"]
