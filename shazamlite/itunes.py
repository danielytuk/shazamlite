from typing import List, Optional

from .constants import ITUNES_LOOKUP, ITUNES_SEARCH
from .http import HTTPClient
from .models import Album, Artist, Image, Track


def _upgrade_artwork(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return url.replace("100x100bb", "600x600bb")


def entry_to_track(entry: dict, source: str = "itunes") -> Track:
    artist_name = entry.get("artistName") or entry.get("collectionArtistName")
    artists = []
    if artist_name:
        artists = [
            Artist(
                adamid=str(entry["artistId"]) if entry.get("artistId") else None,
                name=artist_name,
            )
        ]

    album_title = entry.get("collectionName")
    album = None
    if album_title:
        album = Album(
            adamid=str(entry.get("collectionId") or "") or None,
            title=album_title,
            name=album_title,
        )

    images = []
    artwork = entry.get("artworkUrl100")
    if artwork:
        images = [Image(height=100, width=100, url=artwork)]

    genres = []
    primary_genre = entry.get("primaryGenreName")
    if primary_genre:
        genres = [primary_genre]

    track = Track(
        key=str(entry.get("trackId") or entry.get("amgArtistId") or ""),
        title=entry.get("trackName"),
        subtitle=artist_name,
        artists=artists,
        album=album,
        url=entry.get("trackViewUrl") or entry.get("collectionViewUrl"),
        images=images,
        preview_url=entry.get("previewUrl"),
        apple_music_adamid=str(entry.get("trackId") or "") or None,
        isrc=entry.get("isrc"),
        genres=genres,
        source=source,
    )
    if entry.get("releaseDate"):
        track.metadata["release_date"] = entry["releaseDate"]
    if entry.get("trackTimeMillis"):
        track.metadata["duration_ms"] = entry["trackTimeMillis"]
    if entry.get("collectionName"):
        track.metadata["collection_name"] = entry["collectionName"]
    if entry.get("currency"):
        track.metadata["currency"] = entry["currency"]
    return track


class ITunesClient:
    def __init__(self, http_client: Optional[HTTPClient] = None):
        self.http = http_client or HTTPClient()

    def lookup(self, adam_id, country: str = "US") -> Optional[Track]:
        result = self.http.request(
            "GET",
            ITUNES_LOOKUP,
            params={"id": adam_id, "country": country, "entity": "song"},
        )
        results = (result or {}).get("results") or []
        if not results:
            return None
        return entry_to_track(results[0])

    def lookup_artist(self, artist_id, country: str = "US") -> Optional[str]:
        result = self.http.request(
            "GET",
            ITUNES_LOOKUP,
            params={"id": artist_id, "country": country, "entity": "musicArtist"},
        )
        results = (result or {}).get("results") or []
        if not results:
            return None
        return results[0].get("artistName") or results[0].get("name")

    def lookup_songs(self, artist_id, country: str = "US", limit: int = 10) -> List[Track]:
        result = self.http.request(
            "GET",
            ITUNES_LOOKUP,
            params={"id": artist_id, "country": country, "entity": "song", "limit": limit},
        )
        results = (result or {}).get("results") or []
        return [
            entry_to_track(entry) for entry in results if entry.get("trackName")
        ]


    def search(self, title: str, artist: Optional[str] = None, country: str = "US", limit: int = 5) -> List[Track]:
        term = title
        if artist:
            term = "%s %s" % (title, artist)
        result = self.http.request(
            "GET",
            ITUNES_SEARCH,
            params={
                "term": term,
                "media": "music",
                "entity": "song",
                "country": country,
                "limit": limit,
            },
        )
        results = (result or {}).get("results") or []
        return [entry_to_track(entry) for entry in results]

    def enrich(self, track: Track, country: str = "US") -> Track:
        if track.apple_music_adamid:
            enriched = self.lookup(track.apple_music_adamid, country=country)
        else:
            found = self.search(track.title or "", track.artist, country=country)
            enriched = found[0] if found else None

        if not enriched:
            return track

        if track.apple_music_url is None:
            track.apple_music_url = enriched.apple_music_url
        if not track.preview_url:
            track.preview_url = enriched.preview_url
        if track.images:
            for image in track.images:
                image.url = _upgrade_artwork(image.url) or image.url
        else:
            for image in enriched.images:
                track.images.append(Image(height=image.height, width=image.width, url=_upgrade_artwork(image.url) or image.url))
        if track.album is None:
            track.album = enriched.album
        if not track.genres:
            track.genres = enriched.genres
        if track.isrc is None:
            track.isrc = enriched.isrc
        if track.apple_music_adamid is None:
            track.apple_music_adamid = enriched.apple_music_adamid
        if track.url is None:
            track.url = enriched.url
        return track
