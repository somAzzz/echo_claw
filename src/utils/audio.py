def validate_pcm_chunk(chunk: bytes, expected_samples: int) -> bool:
    """Validate PCM chunk size for 16-bit mono audio.

    Args:
        chunk: Raw PCM bytes
        expected_samples: Number of samples expected

    Returns:
        True if chunk size matches expected size (samples * 2 bytes for 16-bit mono)
    """
    expected_bytes = expected_samples * 2  # 16-bit mono = 2 bytes per sample
    return len(chunk) == expected_bytes


def generate_silence_chunk(sample_count: int) -> bytes:
    """Generate silent PCM chunk for 16-bit mono audio.

    Args:
        sample_count: Number of samples to generate

    Returns:
        Silent PCM bytes (all zeros)
    """
    return b"\x00" * (sample_count * 2)  # 16-bit mono = 2 bytes per sample