from shazamlite.itunes import ITunesClient, entry_to_track
from shazamlite.models import Track


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


def test_entry_to_track_mapping():
    entry = {
        "trackId": 555,
        "trackName": "Song",
        "artistName": "Band",
        "artistId": 444,
        "collectionName": "LP",
        "collectionId": 333,
        "artworkUrl100": "http://img/100x100bb.jpg",
        "previewUrl": "http://preview",
        "trackViewUrl": "http://view",
        "primaryGenreName": "Rock",
        "isrc": "USXXX",
        "releaseDate": "2020-01-01",
    }
    track = entry_to_track(entry)
    assert track.title == "Song"
    assert track.artist == "Band"
    assert track.apple_music_adamid == "555"
    assert track.album.title == "LP"
    assert track.isrc == "USXXX"
    assert track.genres == ["Rock"]
    assert track.metadata["release_date"] == "2020-01-01"
    assert track.images[0].url.endswith("100x100bb.jpg")


def test_enrich_lookup_by_adamid():
    client = ITunesClient(FakeHTTP([
        {
            "results": [
                {
                    "trackId": 555,
                    "trackName": "Song",
                    "artistName": "Band",
                    "artworkUrl100": "http://img/100x100bb.jpg",
                    "previewUrl": "http://preview",
                }
            ]
        }
    ]))
    track = Track(title="Song", subtitle="Band", apple_music_adamid="555")
    enriched = client.enrich(track, country="US")
    assert enriched.preview_url == "http://preview"
    assert enriched.images[0].url == "http://img/600x600bb.jpg"


def test_enrich_search_fallback():
    client = ITunesClient(FakeHTTP([
        {"results": [{"trackName": "Song", "artistName": "Band", "previewUrl": "http://p"}]}
    ]))
    track = Track(title="Song", subtitle="Band")
    enriched = client.enrich(track, country="US")
    assert enriched.preview_url == "http://p"


def test_enrich_keeps_original_when_nothing_found():
    client = ITunesClient(FakeHTTP([{"results": []}]))
    track = Track(title="Song", subtitle="Band")
    enriched = client.enrich(track, country="US")
    assert enriched.title == "Song"
