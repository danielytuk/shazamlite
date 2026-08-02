from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Artist:
    id: Optional[str] = None
    adamid: Optional[str] = None
    name: Optional[str] = None
    avatar: Optional[str] = None
    verified: bool = False


@dataclass
class Album:
    id: Optional[str] = None
    adamid: Optional[str] = None
    title: Optional[str] = None
    name: Optional[str] = None
    coverart: Optional[str] = None


@dataclass
class Image:
    height: int = 0
    width: int = 0
    url: str = ""


@dataclass
class Track:
    key: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    artists: List[Artist] = field(default_factory=list)
    album: Optional[Album] = None
    url: Optional[str] = None
    images: List[Image] = field(default_factory=list)
    preview_url: Optional[str] = None
    apple_music_url: Optional[str] = None
    apple_music_adamid: Optional[str] = None
    spotify_uri: Optional[str] = None
    isrc: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    sections: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "shazam"

    @property
    def artist(self) -> Optional[str]:
        if self.artists and self.artists[0].name:
            return self.artists[0].name
        return self.subtitle

    @property
    def coverart(self) -> Optional[str]:
        if self.images:
            return max(self.images, key=lambda image: image.height).url
        if self.album and self.album.coverart:
            return self.album.coverart
        return None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Track":
        data = dict(data or {})
        artists = [Artist(**artist) for artist in data.pop("artists", []) or [] if artist]
        album_data = data.pop("album", None)
        album = Album(**album_data) if album_data else None
        images = [Image(**image) for image in data.pop("images", []) or [] if image]
        return cls(artists=artists, album=album, images=images, **data)


@dataclass
class TrackMatch:
    track: Optional[Track] = None
    match_type: str = "audio"
    matched: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)
