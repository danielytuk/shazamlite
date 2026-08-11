import argparse
import json
import sys

from .api import Shazam
from .errors import ShazamError


def _print_json(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _tracks_to_json(tracks):
    return [track.to_dict() for track in tracks]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="shazamlite", description="Lightweight Shazam recognition and metadata client.")
    parser.add_argument("--country", default="US", help="country code (default: US)")
    parser.add_argument("--language", default="en", help="language (default: en)")
    parser.add_argument("--timezone", default=None, help="timezone (default: auto-detect)")
    parser.add_argument("--endpoint", default="auto", choices=["auto", "extension", "discovery"])
    parser.add_argument("--no-enrich", action="store_true", help="skip iTunes enrichment")
    parser.add_argument("--json", action="store_true", help="pretty print JSON output")

    subparsers = parser.add_subparsers(dest="command", required=True)

    recognize_parser = subparsers.add_parser("recognize", help="recognize audio from a file")
    recognize_parser.add_argument("audio", help="path to an audio file (wav, mp3, flac, ogg)")

    search_parser = subparsers.add_parser("search", help="search tracks by term")
    search_parser.add_argument("term")
    search_parser.add_argument("--limit", type=int, default=10)

    charts_parser = subparsers.add_parser("charts", help="top charts")
    charts_parser.add_argument("--world", action="store_true", help="top 200 world")
    charts_parser.add_argument("--country", dest="chart_country", default=None, help="country code for charts")
    charts_parser.add_argument("--city", default=None, help="city for top 50 city charts (with --country)")
    charts_parser.add_argument("--genre", default=None, help="genre slug for genre charts")
    charts_parser.add_argument("--limit", type=int, default=20)
    charts_parser.add_argument("--offset", type=int, default=0)

    related_parser = subparsers.add_parser("related", help="related tracks for a track id")
    related_parser.add_argument("track_id")

    artist_parser = subparsers.add_parser("artist", help="artist info / top songs")
    artist_parser.add_argument("artist_id")
    artist_parser.add_argument("--top-songs", action="store_true")
    artist_parser.add_argument("--limit", type=int, default=10)

    args = parser.parse_args(argv)

    client = Shazam(
        language=args.language,
        country=args.country,
        timezone=args.timezone,
        endpoint=args.endpoint,
        enrich=not args.no_enrich,
    )

    try:
        if args.command == "recognize":
            track = client.recognize(args.audio)
            _print_json(track.to_dict())
        elif args.command == "search":
            tracks = client.search(args.term, limit=args.limit)
            _print_json(_tracks_to_json(tracks))
        elif args.command == "charts":
            if args.world:
                tracks = client.top_world_charts(limit=args.limit, offset=args.offset)
            elif args.city and args.chart_country:
                tracks = client.top_city_charts(
                    args.chart_country, args.city, limit=args.limit, offset=args.offset
                )
            elif args.genre:
                tracks = client.top_genre_charts(
                    args.genre, country=args.chart_country, limit=args.limit, offset=args.offset
                )
            elif args.chart_country:
                tracks = client.top_country_charts(
                    args.chart_country, limit=args.limit, offset=args.offset
                )
            else:
                tracks = client.top_world_charts(limit=args.limit, offset=args.offset)
            _print_json(_tracks_to_json(tracks))
        elif args.command == "related":
            tracks = client.related_tracks(args.track_id)
            _print_json(_tracks_to_json(tracks))
        elif args.command == "artist":
            if args.top_songs:
                tracks = client.artist_top_songs(args.artist_id, limit=args.limit)
                _print_json(_tracks_to_json(tracks))
            else:
                _print_json(client.artist_about(args.artist_id))
    except ShazamError as error:
        print("error: %s" % error, file=sys.stderr)
        hint = getattr(error, "hint", None)
        if hint:
            print("hint: %s" % hint, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
