"""FastAPI HTTP API for prompts and configuration."""

from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import Config
from src.memory.soul import load_soul_doc, save_soul_doc, clear_cache
from src.prompt_store import PromptStore


class PromptCreate(BaseModel):
    name: str
    content: str


class PromptUpdate(BaseModel):
    content: str


class ConfigUpdate(BaseModel):
    voice: str = None
    rate: str = None
    pitch: str = None
    volume: str = None


app = FastAPI(title="Voice Assistant Hub API")

# CORS middleware for React frontend (development only - use explicit origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
config = Config.get_config()
prompt_store = PromptStore(prompt_dir=config.prompt_dir)
prompt_store.create_default_prompts()


def get_prompt_store() -> PromptStore:
    return prompt_store


@app.get("/api/prompts")
def list_prompts() -> List[str]:
    """List all prompt names."""
    store = get_prompt_store()
    return store.list_prompts()


@app.post("/api/prompts")
def create_prompt(prompt: PromptCreate) -> dict:
    """Create a new prompt file."""
    store = get_prompt_store()
    store.save_prompt(prompt.name, prompt.content)
    return {"name": prompt.name, "status": "created"}


@app.get("/api/prompts/{name}")
def get_prompt(name: str) -> dict:
    """Get prompt content."""
    store = get_prompt_store()
    content = store.get_prompt(name)
    if content is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"name": name, "content": content}


@app.put("/api/prompts/{name}")
def update_prompt(name: str, prompt: PromptUpdate) -> dict:
    """Update prompt content."""
    store = get_prompt_store()
    if store.get_prompt(name) is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    store.save_prompt(name, prompt.content)
    return {"name": name, "status": "updated"}


@app.delete("/api/prompts/{name}")
def delete_prompt(name: str) -> dict:
    """Delete a prompt file."""
    store = get_prompt_store()
    if not store.delete_prompt(name):
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"name": name, "status": "deleted"}


@app.get("/api/config")
def get_config() -> dict:
    """Get current configuration."""
    return {
        "tts": {
            "voice": config.tts.voice,
            "rate": config.tts.rate,
            "pitch": config.tts.pitch,
            "volume": config.tts.volume,
        }
    }


@app.put("/api/config")
def update_config(cfg: ConfigUpdate) -> dict:
    """Update configuration (runtime only, not persisted)."""
    if cfg.voice is not None:
        config.tts.voice = cfg.voice
    if cfg.rate is not None:
        config.tts.rate = cfg.rate
    if cfg.pitch is not None:
        config.tts.pitch = cfg.pitch
    if cfg.volume is not None:
        config.tts.volume = cfg.volume
    return {"status": "updated"}


@app.get("/api/status")
def get_status() -> dict:
    """Get pipeline status."""
    return {
        "asr_url": config.asr.base_url,
        "llm_url": config.llm.base_url,
        "llm_model": config.llm.model,
    }


# SOUL.md API (local-first with OpenClaw fallback)
@app.get("/api/soul")
def get_soul() -> dict:
    """Get SOUL.md content.

    Returns:
        SOUL.md content from local-first priority:
        1. prompts/soul.md (python-hub managed)
        2. ~/.openclaw/workspace/SOUL.md (OpenClaw global)
        3. Default fallback
    """
    content = load_soul_doc()
    return {"content": content}


class SoulUpdate(BaseModel):
    content: str


@app.put("/api/soul")
def update_soul(soul: SoulUpdate) -> dict:
    """Update SOUL.md content.

    Saves to local prompts/soul.md (python-hub managed).
    Does NOT modify OpenClaw global SOUL.md.
    """
    save_soul_doc(soul.content)
    clear_cache()  # Invalidate cached SOUL prompt
    return {"status": "updated"}


if __name__ == "__main__":
    import uvicorn

    cfg = Config.get_config()
    uvicorn.run(app, host="0.0.0.0", port=cfg.server.http_port)
