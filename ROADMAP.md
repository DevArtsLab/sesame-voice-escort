# Sesame Voice Escort: capabilities and next steps

Companion document to the [README](README.md). The README covers setup and
operation; this file is the working record of what the tool does today and the
paths worth taking next.

## What it is

The desktop path into Sesame Voice Capture, which is audio-only and iPhone-only
upstream. See the [README](README.md) for the intro and architecture diagram.

## Current capabilities

| Capability     | Notes                                                                                                           |
| -------------- | --------------------------------------------------------------------------------------------------------------- |
| Mic recording  | MediaRecorder + live waveform; prefers AAC/mp4, falls back to webm/ogg                                          |
| File upload    | picker, multi-select, drag and drop anywhere in the window                                                      |
| Typed text     | spoken via macOS `say` into an m4a, sent through the same pipeline (`POST /speak`)                              |
| Formats        | m4a, aac, mp3, wav, ogg, opus, webm, flac; 10 MB per note enforced                                              |
| Reliability    | per-note `Idempotency-Key`, retry on failure, `X-Recorded-At` backdating                                        |
| History        | local `sent/` copies with in-page playback; `history.json` ledger                                               |
| Connectivity   | `POST /test` ping (`X-Voice-Capture-Test`)                                                                      |
| Security       | device secret stays server-side; loopback CSRF/rebinding guard; path-traversal-safe audio serving               |
| TLS inspection | `setup-certs.sh` merges macOS keychain roots (Cloudflare Gateway, Zscaler, Netskope) into `certs/ca-bundle.pem` |

## Interfaces

| Endpoint          | Purpose                                                                  |
| ----------------- | ------------------------------------------------------------------------ |
| `GET /`           | the single-file UI                                                       |
| `GET /health`     | `{"configured": bool, "device_name": str}`                               |
| `POST /send`      | raw audio body; headers `X-Filename`, `X-Recorded-At`, `Idempotency-Key` |
| `POST /speak`     | JSON `{"text": str}`; TTS via `say`, then identical to `/send`           |
| `POST /test`      | forwards the Sesame test ping                                            |
| `GET /history`    | JSON list of sent notes                                                  |
| `GET /audio/<id>` | stored copy of a sent note                                               |

Config: `config.json` (gitignored) or env vars `SESAME_DEVICE_URL` /
`SESAME_DEVICE_SECRET`. Optional `tts_voice` selects the `say` voice.

## Next steps

Ordered roughly by value-for-effort.

1. **Small fix: `say` timeout temp file.** If `say` exceeds its timeout, a
   partial `.tts-*.m4a` is left behind in `sent/`. One-line `unlink` in the
   timeout branch of `_handle_speak`.
2. **Hotkey/script entry point.** A tiny `sesame-say` shell helper (stdin ->
   `POST /speak`) enables clipboard-to-Sesame flows from Raycast, Shortcuts,
   or Keyboard Maestro. `~/.local/bin/sesame-note` already covers raw file
   upload; decide whether the helpers should live in this repo or be merged.
3. **Tests.** stdlib `unittest` + a local echo server (the same pattern used
   to verify `/speak`) can cover send, retry, history, and TTS paths without
   touching the real device endpoint.
4. **Packaging.** A `homebrew-tap` repo exists in the workspace; the tool is
   stdlib-only Python, so a formula is mostly a tarball + a launch wrapper
   around `Sesame Voice Escort.command`.
5. **MCP server refresh.** The Devin MCP `sesame-voice-escort` server needs a
   fresh setup-link JWT; document or automate the renewal flow if the MCP path
   stays useful.
6. **Menu-bar port.** `../kaiku-menubar-recorder` is a kept-aside native
   recorder clone; a Swift port would remove the browser tab entirely.
7. **Voice quality.** `tts_voice` accepts any `say -v` name; premium macOS
   voices read far better than the default. Optionally expose voice + rate in
   the UI.
8. **Round-trip transcripts.** Voice Capture is one-way today; if Sesame ever
   exposes a read API, surfacing transcripts in the history feed closes the
   loop.

## Open questions

- Should text sends be marked differently upstream (a distinguishing
  `X-Filename` or header) so the agent can tell typed input from speech?
- Is the 10 MB ceiling per note or per request batch at the Sesame side?
- Worth a `GET /config` endpoint so the UI can show the active `tts_voice`?

## Publishing checklist

Safe to publish as-is:

- `config.json`, `sent/`, `certs/`, `.DS_Store`, `__pycache__/` are all
  gitignored; the device URL and secret never leave the local config.
- No hostnames, account IDs, or personal paths appear in tracked files; the
  docs use `~` and placeholders throughout.
- The MIT license is already in place.
