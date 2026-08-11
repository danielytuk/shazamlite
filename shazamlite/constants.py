ENDPOINTS = {
    "match_extensionv2": "https://www.shazam.com/services/webrec/match_extensionv2",
    "discovery/v5": "https://amp.shazam.com/discovery/v5/{lang}/{cc}/{device}/-/tag/{uuid1}/{uuid2}",
    "related_tracks": "https://cdn.shazam.com/shazam/v3/{lang}/{cc}/web/-/tracks/track-similarities-id-{track_id}",
    "charts_csv_top_200_world": "https://www.shazam.com/services/charts/csv/top-200/world",
    "charts_csv_top_200_cc": "https://www.shazam.com/services/charts/csv/top-200/{cc}",
    "charts_csv_top_50_city": "https://www.shazam.com/services/charts/csv/top-50/{cc}/{city}",
    "charts_csv_genre_world": "https://www.shazam.com/services/charts/csv/genre/world/{genre}",
    "charts_csv_genre_cc": "https://www.shazam.com/services/charts/csv/genre/{cc}/{genre}",
    "locations": "https://www.shazam.com/services/charts/locations",
}

EXTENSION_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

HEADERS_DISCOVERY = {
    "User-Agent": EXTENSION_UA,
    "X-Shazam-Platform": "iOS",
    "X-Shazam-AppVersion": "17.1.0",
    "Accept": "application/json",
}

ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
ITUNES_SEARCH = "https://itunes.apple.com/search"

DEFAULT_LANG = "en"
DEFAULT_COUNTRY = "US"
DEFAULT_TIMEZONE = "UTC"
