import struct

import numpy as np
import pytest

from shazamlite.audio import pcm_to_sig_input
from shazamlite.errors import BadData
from shazamlite.signature import (
    DATA_URI_PREFIX,
    extract_signature,
    extract_signature_uri,
)


def make_audio(seconds=4.0, seed=None, sample_rate=16000):
    t = np.arange(int(sample_rate * seconds)) / sample_rate
    if seed is None:
        signal = (
            0.5 * np.sin(2 * np.pi * 440 * t) * (1 + 0.8 * np.sin(2 * np.pi * 3 * t))
            + 0.35 * np.sin(2 * np.pi * 880 * t) * (1 + 0.8 * np.sin(2 * np.pi * 5 * t))
            + 0.25 * np.sin(2 * np.pi * 2000 * t) * (1 + 0.8 * np.sin(2 * np.pi * 7 * t))
        )
    else:
        rng = np.random.default_rng(seed)
        signal = rng.normal(0, 0.3, len(t))
    return pcm_to_sig_input(signal, sample_rate)


def test_header_fields():
    signature = extract_signature(make_audio())
    assert len(signature) > 48
    assert struct.unpack_from("<I", signature, 0)[0] == 0xCAFE2580
    size_minus_header = struct.unpack_from("<I", signature, 8)[0]
    assert size_minus_header == len(signature) - 48
    assert struct.unpack_from("<I", signature, 12)[0] == 0x94119C00
    assert struct.unpack_from("<I", signature, 28)[0] == 3 << 27
    assert struct.unpack_from("<I", signature, 44)[0] == 0x7C0000
    assert struct.unpack_from("<I", signature, 48)[0] == 0x40000000
    assert struct.unpack_from("<I", signature, 52)[0] == size_minus_header


def test_crc32_valid():
    from binascii import crc32

    signature = extract_signature(make_audio())
    stored_crc = struct.unpack_from("<I", signature, 4)[0]
    assert crc32(signature[8:]) & 0xFFFFFFFF == stored_crc


def test_deterministic():
    audio = make_audio()
    assert extract_signature(audio) == extract_signature(audio)


def test_different_audio_different_signature():
    sig_a = extract_signature(make_audio(seconds=4.0))
    sig_b = extract_signature(make_audio(seconds=4.0, seed=1234))
    assert sig_a != sig_b


def test_too_short_raises_bad_data():
    with pytest.raises(BadData):
        extract_signature([0] * 16000)


def test_uri():
    uri = extract_signature_uri(make_audio().tolist())
    assert uri.startswith(DATA_URI_PREFIX)


def test_accepts_numpy_int16():
    audio = make_audio()
    assert extract_signature(audio) == extract_signature(audio.tolist())
