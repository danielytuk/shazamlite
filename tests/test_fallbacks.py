import numpy as np
import pytest

from shazamlite.api import _track_from_discovery, _track_from_extension_match
from shazamlite.errors import HTTPStatusError, NoMatch
from shazamlite.http import HTTPClient
from shazamlite.models import Track


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, *args, **kwargs):
        self.requests.append((args, kwargs))
        return self.responses.pop(0)


EXTENSION_MATCH = {
    "results": {
        "matches": [
            {
                "trackId": "123",
                "attributes": {
                    "title": "Song",
                    "subtitle": "Band",
                    "webUrl": "https://www.shazam.com/track/123",
                    "adamid": "999",
                    "images": {"coverArtHq": "http://cover-hq", "coverArt": "http://cover"},
                    "genres": {"genres": [{"name": "Pop"}]},
                    "previews": [{"url": "http://preview"}],
                },
            }
        ]
    }
}

DISCOVERY_TRACK = {
    "key": "456",
    "title": "Other Song",
    "subtitle": "Other Band",
    "url": "https://www.shazam.com/track/456",
    "adamid": "777",
    "images": {"coverart": "http://cover"},
    "hub": {"actions": [{"name": "apple", "uri": "https://music.apple.com/x"}]},
    "genres": {"primary": "Rock"},
}

DISCOVERY_MATCH = {"matches": [{"track": DISCOVERY_TRACK}]}


def make_audio():
    sample_rate = 16000
    t = np.arange(sample_rate * 3) / sample_rate
    signal = (
        0.5 * np.sin(2 * np.pi * 440 * t) * (1 + 0.8 * np.sin(2 * np.pi * 3 * t))
        + 0.35 * np.sin(2 * np.pi * 880 * t) * (1 + 0.8 * np.sin(2 * np.pi * 5 * t))
    )
    return signal.astype(np.float32)


def test_extension_match_parsing():
    from shazamlite.api import Shazam

    client = Shazam(endpoint="extension", http_client=FakeHTTP([EXTENSION_MATCH]), enrich=False)
    track = client.recognize(make_audio())
    assert isinstance(track, Track)
    assert track.title == "Song"
    assert track.artist == "Band"
    assert track.apple_music_adamid == "999"
    assert track.metadata["backend"] == "extension"
    assert track.images[0].url == "http://cover-hq"


def test_discovery_used_by_default():
    from shazamlite.api import Shazam

    client = Shazam(http_client=FakeHTTP([DISCOVERY_MATCH]), enrich=False)
    track = client.recognize(make_audio())
    assert track.title == "Other Song"
    assert track.metadata["backend"] == "discovery"


def test_auto_uses_discovery_only():
    from shazamlite.api import Shazam

    fake = FakeHTTP([{"matches": []}, EXTENSION_MATCH])
    client = Shazam(http_client=fake, enrich=False)
    with pytest.raises(NoMatch):
        client.recognize(make_audio())
    assert len(fake.requests) == 1


def test_discovery_only_endpoint():
    from shazamlite.api import Shazam

    client = Shazam(endpoint="discovery", http_client=FakeHTTP([DISCOVERY_MATCH]), enrich=False)
    track = client.recognize(make_audio())
    assert track.metadata["backend"] == "discovery"


def test_extension_only_endpoint_raises_on_empty():
    from shazamlite.api import Shazam

    client = Shazam(endpoint="extension", http_client=FakeHTTP([{"results": {"matches": []}}]), enrich=False)
    with pytest.raises(NoMatch):
        client.recognize(make_audio())


def test_no_match_raises():
    from shazamlite.api import Shazam

    client = Shazam(http_client=FakeHTTP([{"results": {"matches": []}}, {"track": None}]), enrich=False)
    with pytest.raises(NoMatch):
        client.recognize(make_audio())


def test_raises_http_error_when_all_backends_fail():
    from shazamlite.api import Shazam

    class FailingHTTP:
        def request(self, *args, **kwargs):
            raise HTTPStatusError(403, "forbidden", "http://x")

    client = Shazam(http_client=FailingHTTP(), enrich=False)
    with pytest.raises(HTTPStatusError):
        client.recognize(make_audio())


def test_discovery_track_parsing():
    track = _track_from_discovery(DISCOVERY_TRACK)
    assert track.title == "Other Song"
    assert track.apple_music_url == "https://music.apple.com/x"


def test_extension_track_parsing():
    track = _track_from_extension_match(EXTENSION_MATCH["results"]["matches"][0])
    assert track.title == "Song"
    assert track.genres == ["Pop"]
    assert track.preview_url == "http://preview"


def test_discovery_track_top_level_parsing():
    payload = {
        "matches": [{"id": "456", "offset": 81.0, "timeskew": 0.0}],
        "track": {
            "key": "456",
            "title": "Won't Bite (feat. Smino)",
            "subtitle": "Doja Cat",
            "url": "https://www.shazam.com/track/456/wont-bite-feat-smino",
            "images": {"coverart": "http://cover"},
            "artists": [{"id": "42", "adamid": "830588310"}],
            "albumadamid": "12345",
            "sections": [
                {"type": "SONG", "metadata": [{"title": "Album", "text": "Hot Pink"}]}
            ],
            "hub": {
                "actions": [
                    {"name": "apple", "type": "applemusicplay", "id": "1486263170"},
                    {"name": "apple", "type": "uri", "uri": "http://preview.m4a"},
                ]
            },
            "genres": {"primary": "R&B/Soul"},
            "isrc": "USRC11903450",
        },
    }
    track = _track_from_discovery(payload["track"])
    assert track.title == "Won't Bite (feat. Smino)"
    assert track.artist == "Doja Cat"
    assert track.apple_music_adamid == "1486263170"
    assert track.preview_url == "http://preview.m4a"
    assert track.album.title == "Hot Pink"
    assert track.album.adamid == "12345"
    assert track.genres == ["R&B/Soul"]
    assert track.isrc == "USRC11903450"


def test_discovery_uses_top_level_track():
    from shazamlite.api import Shazam

    payload = {
        "matches": [{"id": "456"}],
        "track": {
            "key": "456",
            "title": "Won't Bite (feat. Smino)",
            "subtitle": "Doja Cat",
        },
    }
    client = Shazam(http_client=FakeHTTP([payload]), enrich=False)
    track = client.recognize(make_audio())
    assert track.title == "Won't Bite (feat. Smino)"
    assert track.metadata["backend"] == "discovery"
