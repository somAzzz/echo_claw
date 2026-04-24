import asyncio
from src.pipeline.llm import LLMClient

def test_llm_client_initializes():
    client = LLMClient(base_url="http://localhost:8080/v1", model="test")
    assert client.base_url == "http://localhost:8080/v1"
    assert client.model == "test"