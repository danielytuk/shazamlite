import numpy as np
import pytest

from shazamlite.signature import extract_signature

shazamio_algorithm = pytest.importorskip("shazamio.algorithm")
from shazamio.algorithm import SignatureGenerator as ReferenceGenerator


def reference_signature(samples):
    generator = ReferenceGenerator()
    generator.feed_input(samples)
    signature = generator.get_next_signature()
    for band in signature.frequency_band_to_sound_peaks:
        signature.frequency_band_to_sound_peaks[band] = sorted(
            signature.frequency_band_to_sound_peaks[band],
            key=lambda peak: peak.fft_pass_number,
        )
    return signature.encode_to_binary()


def _modulated(seconds, seed=None):
    sample_rate = 16000
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
    int16 = np.clip(np.rint(signal * 32767.0), -32768, 32767).astype(np.int16)
    return int16


@pytest.mark.parametrize(
    "seconds,seed",
    [
        (4.0, None),
        (6.0, None),
        (3.1, None),
        (4.0, 7),
        (12.0, 42),
        (10.0, 99),
    ],
)
def test_byte_parity_with_shazamio(seconds, seed):
    samples = _modulated(seconds, seed).tolist()
    assert reference_signature(samples) == extract_signature(samples)
