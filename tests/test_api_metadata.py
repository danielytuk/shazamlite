import pytest

from shazamlite.api import Shazam
from shazamlite.models import Track


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, *args, **kwargs):
        self.requests.append((args, kwargs))
        return self.responses.pop(0)


CSV_ROWS = [
    ["Rank", "Artist", "Title"],
    ["1", "Alpha", "Song A"],
    ["2", "Beta", "Song B"],
    ["3", "Gamma", "Song C"],
]

ITUNES_SEARCH = {
    "results": [
        {
            "trackId": 100,
            "trackName": "Found",
            "artistName": "Artist",
            "artistId": 1,
            "collectionName": "LP",
            "trackViewUrl": "https://music.apple.com/us/album/100",
            "artworkUrl100": "http://art/100x100bb.jpg",
            "previewUrl": "http://preview",
            "isrc": "USABC",
            "primaryGenreName": "Pop",
        }
    ]
}


def test_top_world_charts_parse():
    client = Shazam(http_client=FakeHTTP([CSV_ROWS]))
    tracks = client.top_world_charts(limit=2)
    assert len(tracks) == 2
    assert tracks[0].title == "Song A"
    assert tracks[0].artist == "Alpha"
    assert tracks[0].metadata["chart_rank"] == "1"
    assert isinstance(tracks[0], Track)


def test_charts_offset_limit():
    client = Shazam(http_client=FakeHTTP([CSV_ROWS]))
    tracks = client.top_world_charts(limit=1, offset=1)
    assert len(tracks) == 1
    assert tracks[0].title == "Song B"


def test_charts_csv_with_leading_rows():
    rows = [
        ["Sunday, 2 August 2026 [performance over the past 7 days]"],
        ["Rank", "Artist", "Title"],
        ["1", "Alpha", "Song A"],
        ["2", "Beta", "Song B"],
    ]
    client = Shazam(http_client=FakeHTTP([rows]))
    tracks = client.top_world_charts(limit=10)
    assert [t.title for t in tracks] == ["Song A", "Song B"]
    assert tracks[0].metadata["chart_rank"] == "1"


def test_top_country_charts_url():
    client = Shazam(http_client=FakeHTTP([CSV_ROWS]))
    client.top_country_charts("FR")
    url = client.http.requests[0][0][1]
    assert url.endswith("/top-200/FR")


def test_top_genre_charts_world():
    client = Shazam(http_client=FakeHTTP([CSV_ROWS]))
    client.top_genre_charts("pop")
    url = client.http.requests[0][0][1]
    assert url.endswith("/genre/world/pop")


def test_search_parse():
    client = Shazam(http_client=FakeHTTP([ITUNES_SEARCH]))
    tracks = client.search("found", limit=1)
    assert len(tracks) == 1
    track = tracks[0]
    assert track.title == "Found"
    assert track.artist == "Artist"
    assert track.album.title == "LP"
    assert track.apple_music_adamid == "100"
    assert track.images[0].url == "http://art/100x100bb.jpg"
    assert track.preview_url == "http://preview"
    assert track.isrc == "USABC"


def test_search_requests_parameters():
    client = Shazam(http_client=FakeHTTP([ITUNES_SEARCH]))
    client.search("found", limit=5)
    params = client.http.requests[0][1]["params"]
    assert params["term"] == "found"
    assert params["entity"] == "song"
    assert params["limit"] == 5


def test_related_tracks_parse():
    response = {
        "tracks": [
            {"key": "10", "title": "Rel 1", "subtitle": "Artist 1", "url": "http://u"},
            {"key": "11", "title": "Rel 2", "subtitle": "Artist 2", "url": "http://u"},
        ]
    }
    client = Shazam(http_client=FakeHTTP([response]))
    tracks = client.related_tracks("123")
    assert [t.title for t in tracks] == ["Rel 1", "Rel 2"]


def test_artist_about_parses_name():
    client = Shazam(http_client=FakeHTTP([{"results": [{"artistName": "The Band"}]}]))
    result = client.artist_about("42")
    assert result == {"artist_id": "42", "name": "The Band"}
