# Sesame Voice Escort

Local send box for [Sesame Voice Capture](https://capture.sesameai.app): record
voice notes or drop existing audio files, and they upload to your Sesame agent,
which transcribes them.

UI derived from the [voce](https://github.com/29-Cu/voce) demo (record -> upload
-> voice bar), adapted to forward audio to a Sesame device endpoint instead of a
local transcription model.

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Layout](#layout)
- [Setup](#setup)
- [Config](#config)
- [TLS inspection note](#tls-inspection-note)
- [Related](#related)
- [License](#license)

## Features

- Record from the mic (MediaRecorder + live waveform)
- Type text and send it as speech (macOS `say` -> m4a -> same upload path)
- Upload existing files: picker, multi-select, or drag and drop anywhere
- Formats: m4a, aac, mp3, wav, ogg, opus, webm, flac (10 MB per note, enforced)
- Test-connection ping (`X-Voice-Capture-Test`)
- Idempotent sends (per-note `Idempotency-Key`), retry on failure
- `X-Recorded-At` backdating from file mtime / record start time
- Local history of sent notes with in-page playback (`sent/`)
- Device secret stays server-side; the browser never sees it

## Architecture

[![Diagram](https://gitdiagram.com/diagram-badge.svg)](https://gitdiagram.com/devartslab/sesame-voice-escort?utm_source=readme&utm_medium=badge)

```
browser (index.html) ←→ server.py (localhost) ←→ Sesame device API
```

## Layout

```
server.py                     stdlib-only HTTP server + Sesame forwarder
index.html                    single-file UI (record, upload, history, test)
config.example.json           config template
config.json                   local credentials (gitignored)
setup-certs.sh                builds certs/ca-bundle.pem (TLS-inspection roots)
Sesame Voice Escort.command   double-click launcher
sent/                         local copies + history.json (gitignored)
certs/                        generated CA bundle (gitignored)
```

## Setup

```bash
cp config.example.json config.json   # fill in device_url + device_secret
./setup-certs.sh                     # only needed behind TLS inspection
python3 server.py                    # serves http://127.0.0.1:8377
```

Or double-click `Sesame Voice Escort.command` (starts the server and opens the page).
`PORT` and `HOST` env vars are respected.

## Config

`config.json` is gitignored. Env vars `SESAME_DEVICE_URL` /
`SESAME_DEVICE_SECRET` override the file. Get both from the Voice Capture
settings page in the Sesame app.

```json
{
  "device_url": "https://capture.sesameai.app/v1/devices/<device-id>",
  "device_secret": "sesame_whsec_<secret>",
  "device_name": "Mac",
  "tts_voice": ""
}
```

`tts_voice` is optional: any `say -v` name (see `say -v '?'`), used by the
type-and-speak input.

## TLS inspection note

On networks with TLS inspection (Cloudflare Gateway, Zscaler, Netskope),
Python's OpenSSL cannot verify the chain because the inspection root lives in
the macOS keychain, not in the OpenSSL bundle. `setup-certs.sh` merges the
keychain roots into `certs/ca-bundle.pem`; `server.py` uses it automatically
when present.

## Related

- `~/.local/bin/sesame-note` - CLI uploader for the same device endpoint
- `../kaiku-menubar-recorder` - native menu-bar recorder clone, kept for a
  possible future Swift port
- Devin MCP: `sesame-voice-escort` server (needs a fresh setup-link JWT)
- `ROADMAP.md` - capability inventory and next-steps path

## License

MIT — © 2026 [DevArts Lab](https://devartslab.com)
