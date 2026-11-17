# Sounds

## preroll.mp3

The tone Pepa plays on a satellite just before it speaks a reply (see
`agent/preroll.py`).

It is a trimmed copy of Home Assistant's own acknowledge tone,
`homeassistant/components/assist_pipeline/acknowledge.mp3` — the sound HA plays
when "Prefer handling commands locally" handles a command — so the fast path
and Pepa's spoken replies share one sound.

Changes from the original: cut at 0.83 s (the original's 0.22 s lead-in
silence and the beep are kept; most of its 0.9 s quiet tail is dropped) with a
0.10 s fade-out.

The original file is part of Home Assistant Core, licensed under the
Apache License 2.0: https://github.com/home-assistant/core
