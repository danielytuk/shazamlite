import asyncio
import base64
import time
import uuid
from typing import Any, Dict, List, Optional, Union

import numpy as np

from .audio import load_audio, pcm_to_sig_input
from .constants import (
    DEFAULT_COUNTRY,
    DEFAULT_LANG,
    ENDPOINTS,
    HEADERS_DISCOVERY,
)
from .errors import BadData, NoMatch
from .http import HTTPClient
from .itunes import ITunesClient
from .models import Album, Artist, Image, Track, TrackMatch
from .signature import extract_signature, extract_signature_uri
from .utils import detect_timezone

DEFAULT_INID = "0a0a0a0a-1b1b-2c2c-3d3d-4c4c4c4c4c4c"


def _track_from_extension_match(match: dict) -> Track:
    attributes = match.get("attributes") or {}
    images_raw = attributes.get("images") or {}

    track = Track(
        key=str(match.get("trackId") or attributes.get("id") or ""),
        title=attributes.get("title"),
        subtitle=attributes.get("subtitle"),
        url=attributes.get("webUrl"),
        apple_music_adamid=str(attributes.get("adamid") or "") or None,
        source="shazam",
    )

    for label in ("coverArtHq", "coverArt", "background"):
        artwork_url = images_raw.get(label)
        if artwork_url:
            track.images.append(Image(url=artwork_url))

    artist_name = attributes.get("artistName") or attributes.get("subtitle")
    if artist_name:
        track.artists = [
            Artist(
                adamid=str(attributes.get("artistAdamId") or "") or None,
                name=artist_name,
            )
        ]

    album_name = attributes.get("albumName") or attributes.get("album")
    if album_name:
        track.album = Album(
            adamid=str(attributes.get("albumAdamId") or "") or None,
            title=album_name,
            name=album_name,
        )

    genre_list = (attributes.get("genres") or {}).get("genres") or []
    track.genres = [genre.get("name") for genre in genre_list if genre.get("name")]

    previews = attributes.get("previews") or []
    if previews:
        track.preview_url = previews[0].get("url")

    return track


def _track_from_discovery(track_data: dict) -> Track:
    track = Track(
        key=str(track_data.get("key") or ""),
        title=track_data.get("title"),
        subtitle=track_data.get("subtitle"),
        url=track_data.get("url") or ((track_data.get("share") or {}).get("href")),
        source="shazam",
    )

    images_raw = track_data.get("images") or {}
    for label in ("coverart", "coverArtHQ", "coverArt", "background"):
        artwork_url = images_raw.get(label)
        if artwork_url:
            track.images.append(Image(url=artwork_url))

    adamid = track_data.get("adamid")
    if adamid:
        track.apple_music_adamid = str(adamid)

    artists_raw = track_data.get("artists") or []
    for artist in artists_raw:
        name = artist.get("name")
        if not name:
            continue
        track.artists.append(
            Artist(
                id=str(artist.get("id") or "") or None,
                adamid=str(artist.get("adamid") or "") or None,
                name=name,
            )
        )
    if not track.artists and track.subtitle:
        track.artists = [Artist(name=track.subtitle)]

    album_raw = track_data.get("album") or {}
    if isinstance(album_raw, dict) and album_raw.get("title"):
        track.album = Album(title=album_raw.get("title"), name=album_raw.get("title"))
    elif isinstance(album_raw, str):
        track.album = Album(title=album_raw, name=album_raw)

    hub = track_data.get("hub") or {}
    for action in hub.get("actions") or []:
        uri = action.get("uri")
        name = (action.get("name") or "").lower()
        action_type = (action.get("type") or "").lower()
        if name == "apple":
            if "applemusicplay" in action_type:
                if action.get("id"):
                    track.apple_music_adamid = str(action["id"])
                if uri and not track.apple_music_url:
                    track.apple_music_url = uri
            elif "uri" in action_type:
                if uri and not track.preview_url:
                    track.preview_url = uri
            elif uri and not track.apple_music_url:
                track.apple_music_url = uri
        elif name == "uri" and uri and not track.preview_url:
            track.preview_url = uri
        elif name == "open" and uri and not track.apple_music_url:
            track.apple_music_url = uri
    if not track.apple_music_url and track.apple_music_adamid:
        track.apple_music_url = "https://music.apple.com/us/album/%s" % track.apple_music_adamid

    sections = track_data.get("sections") or []
    track.sections = [section for section in sections if isinstance(section, dict)]
    for section in track.sections:
        if not track.album and section.get("type") == "SONG":
            for meta in section.get("metadata") or []:
                if (meta.get("title") or "").lower() == "album" and meta.get("text"):
                    track.album = Album(title=meta["text"], name=meta["text"])
                    break
        break
    if track.album and track_data.get("albumadamid"):
        track.album.adamid = str(track_data["albumadamid"])

    genres = track_data.get("genres") or {}
    primary = genres.get("primary")
    if primary:
        track.genres.append(primary)

    track.isrc = track_data.get("isrc")
    if track_data.get("music_video"):
        track.metadata["music_video"] = track_data["music_video"]

    return track


class Shazam:
    def __init__(
        self,
        language: str = DEFAULT_LANG,
        country: str = DEFAULT_COUNTRY,
        timezone: Optional[str] = None,
        endpoint: str = "auto",
        enrich: bool = True,
        max_time_seconds: float = 3.1,
        scan_windows: int = 10,
        http_client: Optional[HTTPClient] = None,
        inid: str = DEFAULT_INID,
    ):
        if endpoint not in ("auto", "extension", "discovery"):
            raise ValueError("endpoint must be one of: auto, extension, discovery")
        self.language = language
        self.country = country
        self.timezone = detect_timezone(timezone)
        self.endpoint = endpoint
        self.enrich = enrich
        self.max_time_seconds = max_time_seconds
        self.scan_windows = max(1, scan_windows)
        self.http = http_client or HTTPClient()
        self.itunes = ITunesClient(self.http)
        self.inid = inid

    def _recognition_order(self) -> List[str]:
        if self.endpoint == "extension":
            return ["extension"]
        return ["discovery"]

    def _sig_input(self, data, sample_rate: Optional[int] = None):
        samples, sample_rate = load_audio(data, sample_rate)
        sig_input = pcm_to_sig_input(samples, sample_rate)
        return sig_input, len(sig_input)

    def _windowed_candidates(self, sig_input: np.ndarray):
        window = max(1, int(16000 * self.max_time_seconds))
        total = len(sig_input)
        if total <= window:
            return [(sig_input, total)]
        step = max(window, (total - window) // max(1, self.scan_windows - 1))
        offsets = list(range(0, total - window + 1, step))
        if total - window not in offsets:
            offsets.append(total - window)
        candidates = []
        for offset in offsets:
            chunk = sig_input[offset : offset + window]
            energy = float(np.abs(chunk.astype(np.float32)).mean())
            candidates.append((energy, chunk))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [
            (chunk, len(chunk)) for _, chunk in candidates[: self.scan_windows]
        ]

    def signature(self, data, sample_rate: Optional[int] = None) -> bytes:
        sig_input, _ = self._sig_input(data, sample_rate)
        return extract_signature(
            sig_input, sample_rate_hz=16000, max_time_seconds=self.max_time_seconds
        )

    def signature_uri(self, data, sample_rate: Optional[int] = None) -> str:
        signature = self.signature(data, sample_rate)
        return "data:audio/vnd.shazam.sig;base64," + base64.b64encode(signature).decode("ascii")

    def _match_extension(self, signature: bytes) -> Optional[Track]:
        payload = {
            "data": base64.b64encode(signature).decode("ascii"),
            "sessionId": str(uuid.uuid4()),
            "inid": self.inid,
            "lang": self.language,
            "country": self.country,
        }
        headers = {"Content-Type": "application/json"}
        result = self.http.request(
            "POST",
            ENDPOINTS["match_extensionv2"],
            headers=headers,
            json_body=payload,
        )
        matches = (result or {}).get("results") or {}
        matches = matches.get("matches") or []
        if not matches:
            return None
        return _track_from_extension_match(matches[0])

    def _match_discovery(self, signature: bytes, samplems: int) -> Optional[Track]:
        uri = "data:audio/vnd.shazam.sig;base64," + base64.b64encode(signature).decode("ascii")
        timestamp = int(time.time())
        payload = {
            "geolocation": {"altitude": 300, "latitude": 45, "longitude": 2},
            "signature": {
                "samplems": samplems,
                "timestamp": timestamp,
                "uri": uri,
            },
            "timestamp": timestamp,
            "timezone": self.timezone,
        }
        url = (
            ENDPOINTS["discovery/v5"]
            .replace("{lang}", self.language)
            .replace("{cc}", self.country)
            .replace("{device}", "android")
            .replace("{uuid1}", str(uuid.uuid4()).upper())
            .replace("{uuid2}", str(uuid.uuid4()))
        )
        url += (
            "?sync=true&webv3=true&sampling=true&connected="
            "&shazamapiversion=v3&sharehub=true&video=v3"
        )
        headers = dict(HEADERS_DISCOVERY)
        headers.update(
            {
                "Content-Type": "application/json",
                "Content-Language": "en_US",
                "X-Shazam-Platform": "IPHONE",
            }
        )
        result = self.http.request("POST", url, headers=headers, json_body=payload)
        result = result or {}
        track_data = result.get("track")
        matches = result.get("matches") or []
        if not track_data and matches:
            track_data = matches[0].get("track")
        if not track_data:
            return None
        return _track_from_discovery(track_data)

    def recognize(self, data, match_type: str = "audio", sample_rate: Optional[int] = None) -> Track:
        sig_input, _ = self._sig_input(data, sample_rate)
        last_error: Optional[Exception] = None
        for chunk, n_samples in self._windowed_candidates(sig_input):
            try:
                signature = extract_signature(
                    chunk, sample_rate_hz=16000, max_time_seconds=self.max_time_seconds
                )
            except BadData:
                continue
            duration_ms = n_samples * 1000 // 16000
            for backend in self._recognition_order():
                try:
                    if backend == "extension":
                        track = self._match_extension(signature)
                    else:
                        track = self._match_discovery(signature, duration_ms)
                    if track is not None and track.title:
                        track.metadata["backend"] = backend
                        if self.enrich:
                            try:
                                track = self.itunes.enrich(track, country=self.country)
                            except Exception:
                                pass
                        return track
                except Exception as error:
                    last_error = error
                    continue

        if last_error is not None and not isinstance(last_error, NoMatch):
            raise last_error
        raise NoMatch("no match found for the given audio")

    def _parse_csv_charts(self, rows: list, source: str) -> List[Track]:
        if not rows:
            return []
        header_index = None
        header = None
        for index, row in enumerate(rows):
            lowered = [(column or "").strip().lower() for column in row]
            if (
                any(value in lowered for value in ("rank", "position", "#"))
                and any(value in lowered for value in ("artist", "artist name"))
                and any(value in lowered for value in ("title", "track", "song", "track title"))
            ):
                header_index = index
                header = row
                break
        if header_index is None:
            return []
        artist_index = title_index = rank_index = 0
        for index, column in enumerate(header):
            lowered = (column or "").strip().lower()
            if lowered in ("artist", "artist name"):
                artist_index = index
            elif lowered in ("title", "track", "song", "track title"):
                title_index = index
            elif lowered in ("rank", "position", "#"):
                rank_index = index
        tracks = []
        for row in rows[header_index + 1 :]:
            if len(row) <= max(artist_index, title_index):
                continue
            title = (row[title_index] or "").strip()
            artist = (row[artist_index] or "").strip()
            if not title:
                continue
            track = Track(
                title=title,
                subtitle=artist,
                artists=[Artist(name=artist)] if artist else [],
                metadata={"chart_rank": row[rank_index].strip() if rank_index < len(row) else ""},
                source=source,
            )
            tracks.append(track)
        return tracks

    def _charts(self, url: str, limit: int, offset: int, source: str) -> List[Track]:
        rows = self.http.request("GET", url, response_format="csv")
        tracks = self._parse_csv_charts(rows, source)
        return tracks[offset : offset + limit]

    def top_world_charts(self, limit: int = 20, offset: int = 0) -> List[Track]:
        return self._charts(
            ENDPOINTS["charts_csv_top_200_world"], limit, offset, "charts:world"
        )

    def top_country_charts(self, country: str = None, limit: int = 20, offset: int = 0) -> List[Track]:
        cc = country or self.country
        return self._charts(
            ENDPOINTS["charts_csv_top_200_cc"].replace("{cc}", cc), limit, offset, "charts:%s" % cc
        )

    def top_city_charts(self, country: str, city: str, limit: int = 20, offset: int = 0) -> List[Track]:
        city_slug = self._resolve_city_slug(country, city)
        url = ENDPOINTS["charts_csv_top_50_city"].replace("{cc}", country).replace("{city}", city_slug)
        return self._charts(url, limit, offset, "charts:%s:%s" % (country, city_slug))

    def top_genre_charts(self, genre: str, country: str = None, limit: int = 20, offset: int = 0) -> List[Track]:
        cc = country or "world"
        if cc == "world":
            url = ENDPOINTS["charts_csv_genre_world"].replace("{genre}", genre)
        else:
            url = ENDPOINTS["charts_csv_genre_cc"].replace("{cc}", cc).replace("{genre}", genre)
        return self._charts(url, limit, offset, "charts:%s:%s" % (cc, genre))

    def _resolve_city_slug(self, country: str, city: str) -> str:
        city_lowered = city.strip().lower().replace(" ", "-")
        wanted_country = country.strip().lower()
        try:
            result = self.http.request("GET", ENDPOINTS["locations"])
        except Exception:
            return city_lowered

        def matches(entry):
            name = ((entry.get("name") or "") or "").lower().replace(" ", "-")
            url_name = (entry.get("urlName") or "").lower()
            return name == city_lowered or url_name == city_lowered

        def find(entries):
            for entry in entries:
                if matches(entry):
                    return entry.get("urlName") or city_lowered
                for nested in (entry.get("cities") or [], entry.get("subcountries") or []):
                    found = find(nested) if nested else None
                    if found:
                        return found
            return None

        countries = (result or {}).get("countries") or []
        for country_entry in countries:
            entry_id = (country_entry.get("id") or "").lower()
            entry_name = (country_entry.get("name") or "").lower()
            if entry_id == wanted_country or entry_name == wanted_country:
                found = find(country_entry.get("cities") or [])
                if found:
                    return found
        found = find(countries)
        return found or city_lowered

    def search(self, query: str, limit: int = 10, offset: int = 0) -> List[Track]:
        tracks = self.itunes.search(query, country=self.country, limit=limit + offset)
        return tracks[offset : offset + limit]

    def related_tracks(self, track_id: str, limit: int = 10) -> List[Track]:
        url = (
            ENDPOINTS["related_tracks"]
            .replace("{cc}", self.country)
            .replace("{lang}", self.language)
            .replace("{track_id}", track_id)
        )
        result = self.http.request(
            "GET", url, params={"startFrom": 0, "pageSize": limit}
        )
        tracks = []
        for related in (result or {}).get("tracks") or []:
            track = _track_from_discovery(related)
            if track.title:
                tracks.append(track)
        return tracks[:limit]

    def artist_about(self, artist_id: str) -> Dict[str, Any]:
        try:
            name = self.itunes.lookup_artist(artist_id, country=self.country)
        except Exception:
            name = None
        return {"artist_id": artist_id, "name": name}

    def artist_top_songs(self, artist_id: str, limit: int = 10) -> List[Track]:
        try:
            return self.itunes.lookup_songs(
                artist_id, country=self.country, limit=limit
            )
        except Exception:
            return []


class ShazamAsync(Shazam):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def _run(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def recognize(self, data, match_type: str = "audio", sample_rate: Optional[int] = None) -> Track:
        return await self._run(super().recognize, data, match_type, sample_rate)

    async def signature(self, data, sample_rate: Optional[int] = None) -> bytes:
        return await self._run(super().signature, data, sample_rate)

    async def signature_uri(self, data, sample_rate: Optional[int] = None) -> str:
        return await self._run(super().signature_uri, data, sample_rate)

    async def top_world_charts(self, limit: int = 20, offset: int = 0) -> List[Track]:
        return await self._run(super().top_world_charts, limit, offset)

    async def top_country_charts(self, country: str = None, limit: int = 20, offset: int = 0) -> List[Track]:
        return await self._run(super().top_country_charts, country, limit, offset)

    async def top_city_charts(self, country: str, city: str, limit: int = 20, offset: int = 0) -> List[Track]:
        return await self._run(super().top_city_charts, country, city, limit, offset)

    async def top_genre_charts(self, genre: str, country: str = None, limit: int = 20, offset: int = 0) -> List[Track]:
        return await self._run(super().top_genre_charts, genre, country, limit, offset)

    async def search(self, query: str, limit: int = 10, offset: int = 0) -> List[Track]:
        return await self._run(super().search, query, limit, offset)

    async def related_tracks(self, track_id: str) -> List[Track]:
        return await self._run(super().related_tracks, track_id)

    async def artist_about(self, artist_id: str) -> Dict[str, Any]:
        return await self._run(super().artist_about, artist_id)

    async def artist_top_songs(self, artist_id: str, limit: int = 10) -> List[Track]:
        return await self._run(super().artist_top_songs, artist_id, limit)
