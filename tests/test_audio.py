import io
import wave

import numpy as np
import pytest

from shazamlite.audio import load_audio, pcm_to_sig_input, resample
from shazamlite.errors import BadData


def write_wav(samples_int16, sample_rate=16000, channels=1):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples_int16.tobytes())
    return buffer.getvalue()


def test_load_wav_bytes():
    samples = (np.sin(2 * np.pi * 440 * np.arange(16000) / 16000) * 10000).astype(np.int16)
    data = write_wav(samples)
    audio, rate = load_audio(data)
    assert rate == 16000
    assert audio.dtype == np.float32
    assert len(audio) == 16000
    assert audio.max() <= 1.0 and audio.min() >= -1.0


def test_load_wav_path(tmp_path):
    samples = (np.sin(2 * np.pi * 440 * np.arange(16000) / 16000) * 10000).astype(np.int16)
    path = tmp_path / "test.wav"
    path.write_bytes(write_wav(samples))
    audio, rate = load_audio(path)
    assert rate == 16000
    assert len(audio) == 16000


def test_load_24bit_wav_preserves_levels():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(3)
        wav.setframerate(16000)
        signal = (np.sin(2 * np.pi * 440 * np.arange(16000) / 16000) * 0.5)
        int24 = np.clip(np.rint(signal * 8388607.0), -(1 << 23), (1 << 23) - 1).astype(np.int32)
        raw = np.empty(int24.size * 3, dtype=np.uint8)
        raw[0::3] = (int24 & 0xFF).astype(np.uint8)
        raw[1::3] = ((int24 >> 8) & 0xFF).astype(np.uint8)
        raw[2::3] = ((int24 >> 16) & 0xFF).astype(np.uint8)
        wav.writeframes(raw.tobytes())
    audio, rate = load_audio(buffer.getvalue())
    assert rate == 16000
    assert len(audio) == 16000
    assert float(np.sqrt((audio ** 2).mean())) > 0.1


def test_load_numpy_defaults_to_16k():
    audio = np.zeros(8000, dtype=np.float32)
    samples, rate = load_audio(audio)
    assert rate == 16000


def test_stereo_to_mono():
    left = np.linspace(-1, 1, 1000).astype(np.float32)
    right = np.linspace(1, -1, 1000).astype(np.float32)
    stereo = np.vstack([left, right]).T
    mono, _ = load_audio(stereo, 44100)
    assert mono.ndim == 1
    assert np.allclose(mono, (left + right) / 2)


def test_unsupported_source():
    with pytest.raises(BadData):
        load_audio(object())


def test_resample_length():
    samples = np.sin(np.arange(8000) / 100).astype(np.float32)
    out = resample(samples, 8000, 16000)
    assert len(out) == 16000
    out2 = resample(samples, 8000, 16000)
    assert np.allclose(out, out2)


def test_pcm_to_sig_input_16k_passthrough():
    signal = np.sin(np.arange(16000) / 100).astype(np.float32)
    out = pcm_to_sig_input(signal, 16000)
    assert out.dtype == np.int16
    assert len(out) == 16000


def test_unsupported_float_wav_bytes():
    # 4-byte float wav should still decode via the width==4 branch
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(4)
        wav.setframerate(16000)
        wav.writeframes(np.zeros(1000, dtype=np.float32).tobytes())
    audio, rate = load_audio(buffer.getvalue())
    assert rate == 16000
    assert len(audio) == 1000
