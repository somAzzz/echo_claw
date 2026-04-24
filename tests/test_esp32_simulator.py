"""
ESP32 Simulator for integration testing.

Simulates an ESP32 client connecting via WebSocket — sends PCM audio chunks,
receives TTS audio and state directives. Used for manual/automated testing
without real hardware.
"""

import asyncio
import json

import pytest
import websockets


class ESP32Simulator:
    """Simulates an ESP32 client connecting via WebSocket."""

    def __init__(self, uri: str = "ws://localhost:8765"):
        self.uri = uri
        self.websocket = None
        self.received_states = []
        self.received_audio_chunks = []
        self.connected = False

    async def connect(self):
        """Connect to the WebSocket server."""
        self.websocket = await websockets.connect(self.uri, ping_interval=None)
        self.connected = True

    async def send_audio(self, chunk: bytes):
        """Send a PCM audio chunk (binary)."""
        await self.websocket.send(chunk)

    async def receive(self):
        """Receive next message (state directive or audio chunk)."""
        msg = await self.websocket.recv()
        if isinstance(msg, str):
            self.received_states.append(json.loads(msg))
        elif isinstance(msg, bytes):
            self.received_audio_chunks.append(msg)
        return msg

    async def close(self):
        """Close the WebSocket connection."""
        await self.websocket.close()
        self.connected = False


_server_running = False


async def _check_server():
    """Check if the server is running by attempting a connection."""
    global _server_running
    try:
        async with asyncio.timeout(2):
            async with websockets.connect("ws://localhost:8765", ping_interval=None) as ws:
                _server_running = True
    except Exception:
        _server_running = False
    return _server_running


@pytest.mark.skipif(not _server_running, reason="Requires running python-hub server")
@pytest.mark.asyncio
async def test_simulator_connect_and_idle():
    """Test that the simulator can connect and receive idle state."""
    sim = ESP32Simulator()
    await sim.connect()
    try:
        # Server should send idle state on connect
        msg = await asyncio.wait_for(sim.receive(), timeout=5.0)
        assert isinstance(msg, str)
        data = json.loads(msg)
        assert data["state"] == "idle"
    finally:
        await sim.close()


@pytest.mark.skipif(not _server_running, reason="Requires running python-hub server")
@pytest.mark.asyncio
async def test_simulator_sends_pcm():
    """Test that the simulator can send PCM audio chunks."""
    sim = ESP32Simulator()
    await sim.connect()
    try:
        # Send a fake PCM chunk (1 second of silence)
        silence = b"\x00" * 32000  # 16kHz, 16-bit, 1 second
        await sim.send_audio(silence)
        # Should not raise
    finally:
        await sim.close()