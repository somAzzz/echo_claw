FROM vllm/vllm-openai:latest

RUN pip install --no-cache-dir soundfile av

ENTRYPOINT ["vllm", "serve"]
