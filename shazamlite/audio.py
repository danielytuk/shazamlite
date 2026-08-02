import io
import wave
from pathlib import Path

import numpy as np

from .errors import BadData

FLOAT_DTYPE = np.float32
INT16_DTYPE = np.int16


def _normalize_to_float(samples: np.ndarray) -> np.ndarray:
    samples = np.asarray(samples)
    if samples.dtype == np.float32 or samples.dtype == np.float64:
        return samples.astype(FLOAT_DTYPE)
    if samples.dtype == np.int16:
        return samples.astype(FLOAT_DTYPE) / 32768.0
    if samples.dtype == np.int32:
        return samples.astype(FLOAT_DTYPE) / 2147483648.0
    if samples.dtype == np.uint8:
        return (samples.astype(FLOAT_DTYPE) - 128.0) / 128.0
    if samples.dtype == np.int8:
        return samples.astype(FLOAT_DTYPE) / 128.0
    if samples.dtype.kind in "iu":
        max_value = float(np.iinfo(samples.dtype).max)
        return samples.astype(FLOAT_DTYPE) / max_value
    if samples.dtype == np.bool_:
        return samples.astype(FLOAT_DTYPE)
    return samples.astype(FLOAT_DTYPE)


def _to_mono(samples: np.ndarray) -> np.ndarray:
    if samples.ndim > 1:
        samples = samples.mean(axis=tuple(range(1, samples.ndim)))
    return samples


def _from_wave_bytes(data: bytes, sample_rate=None):
    with wave.open(io.BytesIO(data), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        if sample_rate and sample_rate != rate:
            raise BadData("sample rate mismatch")
        raw = wav.readframes(wav.getnframes())

    if width == 1:
        samples = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        samples = (samples - 128.0) / 128.0
    elif width == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 3:
        ints = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        samples = (ints[:, 0] | (ints[:, 1] << 8) | (ints[:, 2] << 16)).astype(np.float32)
        samples = np.where(samples >= 8388608, samples - 16777216, samples) / 8388608.0
    elif width == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise BadData("unsupported wav sample width: %s" % width)

    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def _load_with_soundfile(path):
    import soundfile as sf

    data, rate = sf.read(path, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=-1)
    return np.ascontiguousarray(data), int(rate)


def _load_with_miniaudio(source, rate=None):
    import miniaudio

    decoded = miniaudio.decode(source, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=rate or 0)
    samples = np.frombuffer(decoded.samples, dtype=np.int16).astype(FLOAT_DTYPE) / 32768.0
    return samples, decoded.sample_rate


def load_audio(source, sample_rate: int = None):
    """Load audio from a path, bytes, AudioSegment or numpy array.

    Returns a mono float32 array in [-1, 1] and the sample rate.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        raw = path.read_bytes()
        if path.suffix.lower() == ".wav":
            return _from_wave_bytes(raw, sample_rate)
        try:
            return _load_with_soundfile(source)
        except ImportError:
            pass
        try:
            return _load_with_miniaudio(source)
        except ImportError:
            pass
        try:
            return _from_wave_bytes(raw, sample_rate)
        except Exception:
            pass
        raise BadData("no audio decoder available for %s (install soundfile or miniaudio)" % source)

    if isinstance(source, (bytes, bytearray)):
        try:
            return _from_wave_bytes(bytes(source), sample_rate)
        except wave.Error:
            try:
                return _load_with_soundfile(io.BytesIO(bytes(source)))
            except ImportError:
                raise BadData("wav decoding failed and soundfile is not installed")

    if isinstance(source, np.ndarray):
        samples = _normalize_to_float(source)
        samples = _to_mono(samples)
        return samples, sample_rate or 16000

    if isinstance(source, (list, tuple)):
        samples = _normalize_to_float(np.asarray(source, dtype=FLOAT_DTYPE))
        samples = _to_mono(samples)
        return samples, sample_rate or 16000

    if hasattr(source, "get_array_of_samples"):
        audio = source.set_sample_width(2).set_frame_rate(16000).set_channels(1)
        samples = np.frombuffer(audio.get_array_of_samples().tobytes(), dtype=np.int16)
        return samples.astype(FLOAT_DTYPE) / 32768.0, 16000

    raise BadData("unsupported audio source type: %s" % type(source).__name__)


def resample(samples: np.ndarray, from_rate: int, to_rate: int = 16000) -> np.ndarray:
    if from_rate == to_rate:
        return np.ascontiguousarray(samples)
    duration = len(samples) / float(from_rate)
    target_len = max(1, int(round(duration * to_rate)))
    if target_len <= 1:
        return samples[:1]
    positions = np.linspace(0.0, len(samples) - 1.0, num=target_len)
    return np.interp(positions, np.arange(len(samples)), samples).astype(FLOAT_DTYPE)


def pcm_to_sig_input(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Return int16 mono 16 KHz samples ready for signature generation."""
    samples = _to_mono(_normalize_to_float(samples))
    if sample_rate is None:
        raise BadData("unknown sample rate")
    if sample_rate != 16000:
        samples = resample(samples, sample_rate, 16000)
    int16 = np.clip(np.rint(samples * 32767.0), -32768, 32767).astype(INT16_DTYPE)
    return int16
