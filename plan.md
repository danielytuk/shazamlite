# shazamlite — Update & Maintenance Playbook

This runbook is the explicit, step-by-step procedure to follow **whenever Shazam
changes its server-side behaviour** — typically announced by an extension update,
sudden `403`/`405`/`400`/`404` responses, or "no match" regressions.

---

## Step 0 — Check the environment FIRST (do not skip)

Shazam/Fastly and many other CDNs **block VPN / datacenter / proxy exit IPs**.
When a VPN (or a system proxy, or a browser like Helium with a built-in tunnel)
is active, *every* endpoint returns `403 Forbidden` or `405 Not allowed` —
even non-Shazam sites.

```powershell
# 1. Is a system proxy configured?
Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' |
  Select-Object ProxyEnable, ProxyServer

# 2. What is our real exit IP, and who owns it?
curl.exe -s https://ipwho.is/
```

- `org` / `asn` shows **Mullvad / Datacamp / VPN / hosting** → **turn the VPN OFF**,
  then re-test.
- `ipwho.is` returning `403 Forbidden` on its own page is the same symptom and a
  smoking gun for a network-level block.

**Only debug endpoints after confirming a clean residential exit IP.**

---

## Step 1 — Grab the extension source code

The installed extension lives in Helium's profile:

```powershell
$ext = "$env:LocalAppData\imput\Helium\User Data\Default\Extensions\mmioliijnhnoblpgimnlajmefafdfilb"
Get-ChildItem $ext | Select-Object Name          # one folder per version, e.g. 2.5.0_0
```

- Copy the newest `*_0` folder to a **scratch directory outside the repo** (never commit it).
- Record the version from `manifest.json` and the folder's `LastWriteTime`.
- If a newer version folder appeared since the last maintenance run, the extension
  **did** update — continue to Step 2. If the version is unchanged, the endpoint
  behaviour changed server-side instead — still continue, the process is the same.

---

## Step 2 — Inventory the endpoints the extension uses

The logic is in `popup.bundle.js` (minified). Extract every URL:

```powershell
$c = [System.IO.File]::ReadAllText("$ext\2.5.0_0\popup.bundle.js")
[regex]::Matches($c, 'https?://[a-zA-Z0-9\.\-/_\?=&:]+') |
  ForEach-Object { $_.Value } | Sort-Object -Unique
```

### Known extension endpoints (2.5.0)

| Endpoint | Purpose |
| -------- | ------- |
| `https://www.shazam.com/services/webrec/match_extensionv2` | **Recognition** (the only match endpoint the extension calls) |
| `https://www.shazam.com/services/webrec/country` | Country detection |
| `https://amp.shazam.com/count/v2/web/track/{trackId}` | Tag count |
| `https://beacon.shazam.com/beacons/api/v1/beacon/` | Analytics |
| `https://www.shazam.com/services/config/features/website.json` | Feature flags |

> **Important:** the extension **does not use `discovery/v5`**. `discovery/v5`
> (from SongRec) is *our* primary recognition path and is not tied to extension
> releases — a 403/405 there is almost always a network/IP problem (Step 0).

Compare the inventory against `shazamlite/constants.py` → `ENDPOINTS` and the
payload/headers in `shazamlite/api.py`.

---

## Step 3 — Figure out what changed

### 3a. Signature algorithm (wasm)

The signature WASM is the source of truth for `shazamlite/signature.py`:

```powershell
Get-FileHash "$ext\2.5.0_0\sigx.wasm" "$ext\2.5.0_0\f384fe9d9d59f3750003.wasm"
```

- Both files should be **identical** (the same build, two names).
- Compare the SHA-256 with the last recorded value. If it changed, re-run the
  byte-parity suite (`pytest tests/test_parity.py`) and, if it fails, port the
  new algorithm.
- If unchanged (as of 2.5.0), `signature.py` needs no work.

### 3b. The recognition call (`match_extensionv2`)

Real extension behaviour (2.5.0, extracted verbatim):

```js
fetch("https://www.shazam.com/services/webrec/match_extensionv2", {
  method: "POST",
  body: JSON.stringify({
    data: <base64 signature>,
    sessionId: uuidv4(),
    inid: chrome.storage.local.get("inidDetails")?.inid || "0a0a0a0a-1b1b-2c2c-3d3d-4c4c4c4c4c4c",
    lang: "en",
    country: "US",
  }),
  headers: { "Content-Type": "application/json" },   // ONLY this header
})
```

- Payload keys: `data`, `sessionId`, `inid`, `lang`, `country`.
- **Only** `Content-Type` is set — no `Origin`, no `Sec-Fetch-*`,
  no `X-Shazam-Platform`. The server discriminates browser requests (real
  `Origin: chrome-extension://…` set automatically by the browser) from bots.
- Success shape: `results.matches[0].attributes` (`title`, `subtitle`,
  `webUrl`, `images.coverArtHq`, `adamid`, `previews`).

### 3c. `discovery/v5` (our primary path)

- Request: `POST https://amp.shazam.com/discovery/v5/{lang}/{cc}/android/-/tag/{uuid1}/{uuid2}`
  with query `sync=true&webv3=true&sampling=true&connected=&shazamapiversion=v3&sharehub=true&video=v3`.
- `uuid1` **uppercase**, lowercase `cc` → 400.
- **Response shape:** the track object is at the **top level**
  (`result["track"]` with `key/title/subtitle/images/hub/sections/genres/isrc`);
  `result.matches[0]` only carries `{id, offset, timeskew}`. **Do not** look for
  `matches[0].track`.
- Long files: scan the loudest windows (`scan_windows`, default 10); silent
  windows are skipped.

---

## Step 4 — Apply fixes

All changes land in `shazamlite/constants.py`, `shazamlite/api.py`, and
`shazamlite/http.py` (+ tests in `tests/`).

1. Update `ENDPOINTS` / headers to match the inventory (Step 2).
2. Update payload + response parsing to match the shapes (Step 3b/3c).
3. Keep both match shapes parseable — tests cover each:
   - `tests/test_fallbacks.py` → discovery top-level track + extension shape.
   - `tests/test_parity.py` → signature byte-parity vs ShazamIO.
4. Add a regression test for anything new.
5. Run the offline suite (no network needed):
   ```powershell
   python -m pytest tests -q
   ```

---

## Step 5 — Live test (VPN must be OFF)

```powershell
shazamlite recognize example_test.wav
shazamlite search "olivia rodrigo" --limit 2
shazamlite charts --world
```

- `recognize` should print a JSON match. A clean `NoMatch` on silent/ambiguous
  audio is expected and fine — use a real song to confirm recognition itself.
- If `403`/`405` reappear here, go back to Step 0 (VPN/proxy), **not** Step 2.

---

## Step 6 — Commit and push

1. Delete any scratch/probe files (`_probe*.py`) — never commit them.
2. `git add -A && git commit -m "…"`
3. `git push origin main`
4. If releasing a new version: bump `shazamlite/_version.py` **and** the version
   in the commit, then `git tag vX.Y.Z && git push origin vX.Y.Z`. The
   `.github/workflows/publish.yml` workflow publishes to PyPI automatically.

---

## Golden rules (learned the hard way)

- **VPN OFF** is a hard requirement for live Shazam testing. VPN-on produces
  Fastly `405`s and Apache-style `403`s **on unrelated sites too**. (A fix to
  make VPN/proxy connections work is in progress; until it lands, use a
  residential exit IP.)
- `discovery/v5` returns the track at `result["track"]`, **not**
  `matches[0]["track"]`.
- `match_extensionv2` returns `400 rsa routines::oaep decoding error` for
  non-browser clients — keep it opt-in (`endpoint="extension"`); `auto` uses
  `discovery/v5`.
- 24-bit WAVs previously decoded to near-silence (uint8 shift truncation) —
  covered by `tests/test_audio.py::test_load_24bit_wav_preserves_levels`.
- The Chrome-store extension update URL is
  `https://clients2.google.com/service/update2/crx` (see `manifest.json`).
