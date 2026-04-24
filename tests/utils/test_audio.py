from src.utils.audio import validate_pcm_chunk, generate_silence_chunk


def test_validate_pcm_chunk_correct_size():
    chunk = b"\x00" * 1024  # 512 samples * 2 bytes
    assert validate_pcm_chunk(chunk, expected_samples=512) == True


def test_validate_pcm_chunk_wrong_size():
    chunk = b"\x00" * 100  # wrong size
    assert validate_pcm_chunk(chunk, expected_samples=512) == False


def test_generate_silence_chunk():
    chunk = generate_silence_chunk(sample_count=512)
    assert len(chunk) == 1024  # 512 samples * 2 bytes
    assert all(b == 0 for b in chunk)