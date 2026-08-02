from base64 import b64encode
from binascii import crc32
from copy import copy
from io import BytesIO
from struct import pack
from typing import Dict, List, Optional, Union

import numpy as np

from .enums import FrequencyBand, SampleRate
from .errors import BadData

DATA_URI_PREFIX = "data:audio/vnd.shazam.sig;base64,"

MAX_TIME_SECONDS = 3.1
MAX_PEAKS = 255

# Window function used before each FFT: a rounded Hanning window (no zeros at
# the edges), computed once at import time.
HANNING_MATRIX = np.hanning(2050)[1:-1]


class RingBuffer(list):
    def __init__(self, buffer_size: int, default_value=None):
        if default_value is not None:
            list.__init__(self, [copy(default_value) for _ in range(buffer_size)])
        else:
            list.__init__(self, [None] * buffer_size)
        self.position: int = 0
        self.buffer_size: int = buffer_size
        self.num_written: int = 0

    def append(self, value):
        self[self.position] = value
        self.position += 1
        self.position %= self.buffer_size
        self.num_written += 1


class FrequencyPeak:
    __slots__ = (
        "fft_pass_number",
        "peak_magnitude",
        "corrected_peak_frequency_bin",
        "sample_rate_hz",
    )

    def __init__(
        self,
        fft_pass_number: int,
        peak_magnitude: int,
        corrected_peak_frequency_bin: int,
        sample_rate_hz: int,
    ):
        self.fft_pass_number = fft_pass_number
        self.peak_magnitude = peak_magnitude
        self.corrected_peak_frequency_bin = corrected_peak_frequency_bin
        self.sample_rate_hz = sample_rate_hz

    def get_frequency_hz(self) -> float:
        return self.corrected_peak_frequency_bin * (self.sample_rate_hz / 2 / 1024 / 64)

    def get_seconds(self) -> float:
        return (self.fft_pass_number * 128) / self.sample_rate_hz


class DecodedMessage:
    sample_rate_hz: int = None
    number_samples: int = None
    frequency_band_to_sound_peaks: Dict[FrequencyBand, List[FrequencyPeak]] = None

    def encode_to_binary(self) -> bytes:
        body_buf = BytesIO()

        for frequency_band in sorted(self.frequency_band_to_sound_peaks):
            frequency_peaks = self.frequency_band_to_sound_peaks[frequency_band]
            peaks_buf = BytesIO()
            fft_pass_number = 0

            for frequency_peak in frequency_peaks:
                assert frequency_peak.fft_pass_number >= fft_pass_number

                if frequency_peak.fft_pass_number - fft_pass_number >= 255:
                    peaks_buf.write(b"\xff")
                    peaks_buf.write(pack("<I", frequency_peak.fft_pass_number))
                    fft_pass_number = frequency_peak.fft_pass_number

                peaks_buf.write(bytes([frequency_peak.fft_pass_number - fft_pass_number]))
                peaks_buf.write(pack("<H", frequency_peak.peak_magnitude))
                peaks_buf.write(pack("<H", frequency_peak.corrected_peak_frequency_bin))
                fft_pass_number = frequency_peak.fft_pass_number

            peaks = peaks_buf.getvalue()
            body_buf.write(pack("<II", 0x60030040 + int(frequency_band), len(peaks)))
            body_buf.write(peaks)
            body_buf.write(b"\x00" * (-len(peaks) % 4))

        body = body_buf.getvalue()
        size_minus_header = len(body) + 8

        # Fields following magic1/crc32/size_minus_header (36 bytes):
        # magic2, void1*3, shifted_sample_rate_id, void2*2,
        # number_samples_plus_divided_sample_rate, fixed_value
        shifted_sample_rate_id = int(SampleRate._16000) << 27
        number_samples_plus_divided_sample_rate = int(
            self.number_samples + self.sample_rate_hz * 0.24
        )

        fields = pack(
            "<9I",
            0x94119C00,
            0,
            0,
            0,
            shifted_sample_rate_id,
            0,
            0,
            number_samples_plus_divided_sample_rate,
            (15 << 19) + 0x40000,
        )
        prefix = pack("<II", 0x40000000, size_minus_header)

        # CRC-32 covers everything after the first 8 bytes (magic1/crc32).
        crc = crc32(pack("<I", size_minus_header) + fields + prefix + body) & 0xFFFFFFFF

        header = pack("<3I", 0xCAFE2580, crc, size_minus_header) + fields
        return header + prefix + body

    def encode_to_uri(self) -> str:
        return DATA_URI_PREFIX + b64encode(self.encode_to_binary()).decode("ascii")


class SignatureGenerator:
    def __init__(
        self,
        sample_rate_hz: int = 16000,
        max_time_seconds: float = MAX_TIME_SECONDS,
        max_peaks: int = MAX_PEAKS,
    ):
        if sample_rate_hz != 16000:
            raise ValueError("signature generation supports a 16 KHz sample rate only")

        self.sample_rate_hz = sample_rate_hz
        self.MAX_TIME_SECONDS = max_time_seconds
        self.MAX_PEAKS = max_peaks

        self.input_pending_processing: List[int] = []
        self.samples_processed: int = 0

        self.ring_buffer_of_samples: RingBuffer[int] = RingBuffer(2048, default_value=0)
        self.fft_outputs: RingBuffer[List[float]] = RingBuffer(256, default_value=[0.0] * 1025)
        self.spread_fft_output: RingBuffer[List[float]] = RingBuffer(256, default_value=[0] * 1025)

        self.next_signature = DecodedMessage()
        self.next_signature.sample_rate_hz = sample_rate_hz
        self.next_signature.number_samples = 0
        self.next_signature.frequency_band_to_sound_peaks = {}

    def feed_input(self, s16le_mono_samples):
        self.input_pending_processing += list(s16le_mono_samples)

    def get_next_signature(self) -> Optional[DecodedMessage]:
        if len(self.input_pending_processing) - self.samples_processed < 128:
            return None

        while len(self.input_pending_processing) - self.samples_processed >= 128 and (
            self.next_signature.number_samples / self.sample_rate_hz < self.MAX_TIME_SECONDS
            or sum(
                len(peaks)
                for peaks in self.next_signature.frequency_band_to_sound_peaks.values()
            )
            < self.MAX_PEAKS
        ):
            self.process_input(
                self.input_pending_processing[
                    self.samples_processed : self.samples_processed + 128
                ]
            )
            self.samples_processed += 128

        self.ring_buffer_of_samples = RingBuffer(2048, default_value=0)
        self.fft_outputs = RingBuffer(256, default_value=[0.0] * 1025)
        self.spread_fft_output = RingBuffer(256, default_value=[0] * 1025)

        return self.next_signature

    def process_input(self, s16le_mono_samples):
        self.next_signature.number_samples += len(s16le_mono_samples)
        for position_of_chunk in range(0, len(s16le_mono_samples), 128):
            self.do_fft(s16le_mono_samples[position_of_chunk : position_of_chunk + 128])
            self.do_peak_spreading_and_recognition()

    def do_fft(self, batch_of_128_s16le_mono_samples):
        type_ring = self.ring_buffer_of_samples.position + len(batch_of_128_s16le_mono_samples)
        self.ring_buffer_of_samples[
            self.ring_buffer_of_samples.position : type_ring
        ] = batch_of_128_s16le_mono_samples
        self.ring_buffer_of_samples.position += len(batch_of_128_s16le_mono_samples)
        self.ring_buffer_of_samples.position %= 2048
        self.ring_buffer_of_samples.num_written += len(batch_of_128_s16le_mono_samples)

        excerpt_from_ring_buffer = (
            self.ring_buffer_of_samples[self.ring_buffer_of_samples.position :]
            + self.ring_buffer_of_samples[: self.ring_buffer_of_samples.position]
        )

        fft_results: np.ndarray = np.fft.rfft(HANNING_MATRIX * excerpt_from_ring_buffer)
        fft_results = (fft_results.real ** 2 + fft_results.imag ** 2) / (1 << 17)
        fft_results = np.maximum(fft_results, 0.0000000001)

        self.fft_outputs.append(fft_results)

    def do_peak_spreading_and_recognition(self):
        self.do_peak_spreading()
        if self.spread_fft_output.num_written >= 46:
            self.do_peak_recognition()

    def do_peak_spreading(self):
        origin_last_fft: List[float] = self.fft_outputs[self.fft_outputs.position - 1]

        temporary_array_1 = np.tile(origin_last_fft, 3).reshape((3, -1))
        temporary_array_1[1] = np.roll(temporary_array_1[1], -1)
        temporary_array_1[2] = np.roll(temporary_array_1[2], -2)

        origin_last_fft_np = np.hstack(
            [temporary_array_1.max(axis=0)[:-3], origin_last_fft[-3:]]
        )

        i1, i2, i3 = [
            (self.spread_fft_output.position + former_fft_num)
            % self.spread_fft_output.buffer_size
            for former_fft_num in [-1, -3, -6]
        ]

        temporary_array_2 = np.vstack(
            [
                origin_last_fft_np,
                self.spread_fft_output[i1],
                self.spread_fft_output[i2],
                self.spread_fft_output[i3],
            ]
        )

        temporary_array_2[1] = np.max(temporary_array_2[:2, :], axis=0)
        temporary_array_2[2] = np.max(temporary_array_2[:3, :], axis=0)
        temporary_array_2[3] = np.max(temporary_array_2[:4, :], axis=0)

        self.spread_fft_output[i1] = temporary_array_2[1].tolist()
        self.spread_fft_output[i2] = temporary_array_2[2].tolist()
        self.spread_fft_output[i3] = temporary_array_2[3].tolist()

        self.spread_fft_output.append(list(origin_last_fft_np))

    def do_peak_recognition(self):
        fft_minus_46 = self.fft_outputs[
            (self.fft_outputs.position - 46) % self.fft_outputs.buffer_size
        ]
        fft_minus_49 = self.spread_fft_output[
            (self.spread_fft_output.position - 49) % self.spread_fft_output.buffer_size
        ]

        for bin_position in range(10, 1015):
            if fft_minus_46[bin_position] >= 1 / 64 and (
                fft_minus_46[bin_position] >= fft_minus_49[bin_position - 1]
            ):
                max_neighbor_in_fft_minus_49 = 0
                for neighbor_offset in [
                    *range(-10, -3, 3),
                    -3,
                    1,
                    *range(2, 9, 3),
                ]:
                    max_neighbor_in_fft_minus_49 = max(
                        fft_minus_49[bin_position + neighbor_offset],
                        max_neighbor_in_fft_minus_49,
                    )

                if fft_minus_46[bin_position] > max_neighbor_in_fft_minus_49:
                    max_neighbor_in_other_adjacent_ffts = max_neighbor_in_fft_minus_49

                    for other_offset in [
                        -53,
                        -45,
                        *range(165, 201, 7),
                        *range(214, 250, 7),
                    ]:
                        max_neighbor_in_other_adjacent_ffts = max(
                            self.spread_fft_output[
                                (self.spread_fft_output.position + other_offset)
                                % self.spread_fft_output.buffer_size
                            ][bin_position - 1],
                            max_neighbor_in_other_adjacent_ffts,
                        )

                    if fft_minus_46[bin_position] > max_neighbor_in_other_adjacent_ffts:
                        fft_number = self.spread_fft_output.num_written - 46

                        peak_magnitude = (
                            np.log(max(1 / 64, fft_minus_46[bin_position])) * 1477.3 + 6144
                        )
                        peak_magnitude_before = (
                            np.log(max(1 / 64, fft_minus_46[bin_position - 1])) * 1477.3 + 6144
                        )
                        peak_magnitude_after = (
                            np.log(max(1 / 64, fft_minus_46[bin_position + 1])) * 1477.3 + 6144
                        )

                        peak_variation_1 = (
                            peak_magnitude * 2 - peak_magnitude_before - peak_magnitude_after
                        )
                        peak_variation_2 = (
                            (peak_magnitude_after - peak_magnitude_before) * 32 / peak_variation_1
                        )

                        corrected_peak_frequency_bin = (
                            bin_position * 64 + peak_variation_2
                        )

                        assert peak_variation_1 > 0

                        frequency_hz = corrected_peak_frequency_bin * (
                            self.sample_rate_hz / 2 / 1024 / 64
                        )

                        if 250 < frequency_hz < 520:
                            band = FrequencyBand.hz_250_520
                        elif 520 < frequency_hz < 1450:
                            band = FrequencyBand.hz_520_1450
                        elif 1450 < frequency_hz < 3500:
                            band = FrequencyBand.hz_1450_3500
                        elif 5500 < frequency_hz <= 5500:
                            band = FrequencyBand.hz_3500_5500
                        else:
                            continue

                        if band not in self.next_signature.frequency_band_to_sound_peaks:
                            self.next_signature.frequency_band_to_sound_peaks[band] = []

                        self.next_signature.frequency_band_to_sound_peaks[band].append(
                            FrequencyPeak(
                                fft_number,
                                int(peak_magnitude),
                                int(corrected_peak_frequency_bin),
                                self.sample_rate_hz,
                            )
                        )


def extract_signature(
    s16le_mono_samples,
    sample_rate_hz: int = 16000,
    max_time_seconds: float = MAX_TIME_SECONDS,
    max_peaks: int = MAX_PEAKS,
) -> bytes:
    """Build a binary Shazam signature from signed 16-bit 16 KHz mono samples."""
    generator = SignatureGenerator(
        sample_rate_hz=sample_rate_hz,
        max_time_seconds=max_time_seconds,
        max_peaks=max_peaks,
    )
    generator.feed_input(s16le_mono_samples)
    signature = generator.get_next_signature()

    if signature is None or not any(
        len(peaks) for peaks in signature.frequency_band_to_sound_peaks.values()
    ):
        raise BadData("Not enough audio to build a signature")

    for frequency_band in signature.frequency_band_to_sound_peaks:
        signature.frequency_band_to_sound_peaks[frequency_band] = sorted(
            signature.frequency_band_to_sound_peaks[frequency_band],
            key=lambda peak: peak.fft_pass_number,
        )

    return signature.encode_to_binary()


def extract_signature_uri(
    s16le_mono_samples,
    sample_rate_hz: int = 16000,
    max_time_seconds: float = MAX_TIME_SECONDS,
    max_peaks: int = MAX_PEAKS,
) -> str:
    return DATA_URI_PREFIX + b64encode(
        extract_signature(
            s16le_mono_samples,
            sample_rate_hz=sample_rate_hz,
            max_time_seconds=max_time_seconds,
            max_peaks=max_peaks,
        )
    ).decode("ascii")
