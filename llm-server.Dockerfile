FROM vllm/vllm-openai:latest

# Upgrade transformers to support gemma4_assistant model architecture
# required by gg-hf-am/gemma-4-E4B-it-assistant for MTP speculative decoding
RUN pip install --no-cache-dir --upgrade transformers

ENTRYPOINT ["vllm", "serve"]
