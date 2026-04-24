FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    sherpa-onnx \
    pydantic \
    fastapi \
    uvicorn \
    python-multipart \
    soundfile

COPY main.py .

EXPOSE 8001

CMD ["python", "main.py"]