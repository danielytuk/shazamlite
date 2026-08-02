from ._version import __version__
from .api import Shazam, ShazamAsync
from .enums import FrequencyBand, SampleRate
from .errors import (
    BadData,
    FailedDecodeJson,
    HTTPStatusError,
    MaxRetriesExceeded,
    NoMatch,
    ShazamError,
)
from .models import Album, Artist, Image, Track, TrackMatch
from .signature import (
    DATA_URI_PREFIX,
    DecodedMessage,
    FrequencyPeak,
    SignatureGenerator,
    extract_signature,
    extract_signature_uri,
)

__all__ = [
    "Shazam",
    "ShazamAsync",
    "Track",
    "TrackMatch",
    "Artist",
    "Album",
    "Image",
    "FrequencyBand",
    "SampleRate",
    "SignatureGenerator",
    "DecodedMessage",
    "FrequencyPeak",
    "extract_signature",
    "extract_signature_uri",
    "DATA_URI_PREFIX",
    "ShazamError",
    "NoMatch",
    "BadData",
    "HTTPStatusError",
    "FailedDecodeJson",
    "MaxRetriesExceeded",
    "__version__",
]
