# shazamlite

[![CI](https://github.com/danielytuk/shazamlite/actions/workflows/ci.yml/badge.svg)](https://github.com/danielytuk/shazamlite/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

Identify any song from audio, with a pure-Python fingerprinting engine and live
Shazam recognition — no API keys required.

`shazamlite` implements Shazam's legacy audio-signature algorithm in pure Python
+ numpy (byte-identical to ShazamIO's `SignatureGenerator`), sends the signature
to Shazam's live `discovery/v5` endpoint, and enriches results with iTunes
metadata (artwork, album, previews).

> **Transparency:** this project is a 50/50 collaboration between human
> creativity and AI implementation. The initial concept, requirements, and
> rough functionality were created by a human developer, then refined and
> polished by AI to ensure smooth functionality, proper error handling, and
> production-ready code quality.

## Features

- **Recognition** — match audio against Shazam's live `discovery/v5` endpoint.
  Long files are scanned across their loudest windows, so quiet intros or
  trailing silence never block a match.
- **Signature engine** — `shazamlite.signature` is a dependency-free reimpl of
  the legacy Shazam algorithm; output is byte-identical to ShazamIO
  (`data:audio/vnd.shazam.sig`).
- **Metadata** — search (iTunes Search), world + genre charts (official CSVs),
  related tracks, artist info and top songs, all enriched with 600×600 artwork.
- **Optional extras** — Chrome TLS impersonation (`curl_cffi`), broad audio
  decoding (`soundfile`/`miniaudio`), live-mic capture (`sounddevice`),
  accurate timezone detection (`tzlocal`), `pydub` support.
- **Sync + async facades**, JSON-serializable dataclasses, rich errors with
  status code + body + URL.

Only `numpy` is required. Everything else is optional.

## Install

```bash
pip install shazamlite                 # + numpy
pip install "shazamlite[all]"          # + curl_cffi, soundfile, miniaudio, tzlocal, sounddevice
```

| Extra         | Provides                                         |
| ------------- | ------------------------------------------------ |
| `curl-cffi`   | Chrome TLS impersonation (JA3/JA4/HTTP2)         |
| `soundfile`   | Decode mp3 / flac / ogg / m4a files              |
| `miniaudio`   | Alternative universal decoder                    |
| `tzlocal`     | Accurate local timezone detection                |
| `mic`         | Live microphone capture via `sounddevice`        |
| `pydub`       | Accept `pydub.AudioSegment` objects directly     |
| `dev`         | pytest + ShazamIO (byte-parity test)             |

## Quick start

```python
import asyncio
from shazamlite import Shazam, ShazamAsync

shazam = Shazam(country="US")

track = shazam.recognize("song.mp3")     # path, WAV bytes, numpy array, or pydub segment
print(track.title, "-", track.artist)    # "Won't Bite (feat. Smino) - Doja Cat"
print(track.coverart)                    # 600x600 artwork URL
print(track.to_dict())                   # JSON-serializable dict

# Async
async def main():
    return await ShazamAsync().recognize("song.flac")

asyncio.run(main())
```

`recognize()` accepts a file path, raw WAV bytes, a numpy float array
(pass `sample_rate=` for anything other than 16 kHz), or a `pydub.AudioSegment`.
For recordings of speech or noise the server simply answers "no match".

## CLI

```bash
shazamlite recognize song.mp3
shazamlite search "olivia rodrigo" --limit 5
shazamlite charts --world
shazamlite charts --country FR
shazamlite charts --country US --city "New York"
shazamlite charts --genre pop
shazamlite related 502331060
shazamlite artist 830588310 --top-songs
```

All output is JSON. Global flags: `--country`, `--language`, `--timezone`,
`--endpoint`, `--no-enrich`, `--json`.

## Metadata

```python
shazam.search("queen bohemian", limit=5)
shazam.top_world_charts(limit=10)
shazam.top_genre_charts("pop")          # genre/world charts
shazam.top_country_charts("FR")         # note: country CSVs are 404 server-side (2026-08)
shazam.top_city_charts("US", "New York")# note: city CSVs are 404 server-side (2026-08)
shazam.related_tracks("502331060")
shazam.artist_about("830588310")        # -> {"artist_id", "name"}
shazam.artist_top_songs("830588310")
```

## Errors

All errors derive from `ShazamError`.

| Error                  | Meaning                                               |
| ---------------------- | ----------------------------------------------------- |
| `NoMatch`              | Server answered, but nothing matched                 |
| `BadData`              | Not enough audio for a signature, or undecodable input |
| `FailedDecodeJson`     | Response was not valid JSON                          |
| `HTTPStatusError`      | Non-2xx (or persistent 429/5xx) — carries code, body, URL |
| `MaxRetriesExceeded`   | Transport failure after all retry attempts            |

429/5xx responses are retried with exponential backoff + jitter (default 3 attempts).

## Troubleshooting

**403 / 405 from Shazam?** Shazam's edge (Fastly) blocks VPN, proxy and
datacenter exit IPs. Disconnect any VPN/proxy first — a 403/405 here is almost
always a network-level block, not a code issue. `HTTPStatusError` carries a
`.hint` property that says the same, and the CLI prints it.

> **VPN users:** we're actively working on a fix so VPN/proxy connections work
> out of the box. Until then, run without a VPN or proxy (or with a residential
> exit) for reliable recognition.

**Shazam changed something server-side?** Follow the maintenance runbook in
[`plan.md`](plan.md) — it covers grabbing the latest extension source, diffing
endpoints/payloads/signatures, applying fixes, and testing with `example_test.wav`.

## Development

```bash
pip install ".[dev]"
pytest                       # full suite (59 tests)
pytest tests/test_parity.py  # byte-parity vs ShazamIO
```

## License

MIT — see [LICENSE](LICENSE).

---

© 2026 Daniel Richard Todd Back · [dytuk.media/shazamlite](https://dytuk.media/shazamlite)
