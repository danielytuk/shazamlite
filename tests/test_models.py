from shazamlite.models import Album, Artist, Image, Track


def test_track_dict_roundtrip():
    track = Track(
        key="1",
        title="Song",
        subtitle="Band",
        artists=[Artist(id="a1", adamid="123", name="Band")],
        album=Album(title="LP", name="LP"),
        images=[Image(height=100, width=100, url="http://img")],
        preview_url="http://preview",
        apple_music_adamid="123",
        genres=["Pop"],
        metadata={"backend": "extension"},
    )
    data = track.to_dict()
    restored = Track.from_dict(data)
    assert restored.to_dict() == data
    assert restored.artist == "Band"
    assert restored.coverart == "http://img"


def test_artist_falls_back_to_subtitle():
    track = Track(title="Song", subtitle="Band")
    assert track.artist == "Band"


def test_coverart_prefers_largest_image():
    track = Track(
        title="Song",
        images=[
            Image(height=100, width=100, url="http://small"),
            Image(height=600, width=600, url="http://big"),
        ],
    )
    assert track.coverart == "http://big"


def test_coverart_from_album():
    track = Track(title="Song", album=Album(title="LP", coverart="http://cover"))
    assert track.coverart == "http://cover"


def test_track_dict_handles_missing_optional_fields():
    restored = Track.from_dict({"title": "Song"})
    assert restored.title == "Song"
    assert restored.artists == []
