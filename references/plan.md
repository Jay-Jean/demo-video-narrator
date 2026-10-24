# JSON plan and CLI

Paths resolve relative to the plan file, not the agent's current directory. The helper does not modify the input video. Output folders must be separate from the input. Use a new output directory for a new delivery; rerunning an existing output requires `--overwrite`.

```json
{
  "version": 1,
  "video": "demo.mp4",
  "voice": "zh-CN-XiaoxiaoNeural",
  "rate": "+0%",
  "max_speedup": 1.18,
  "original_audio": "mute",
  "crop": null,
  "subtitle": {"font_size": 30, "margin_bottom": 10, "max_chars": 26},
  "segments": [
    {"start": 0.5, "end": 8.5, "text": "首先选择演示场景，再查看相关参数与运行状态。"},
    {"start": 9.0, "end": 17.5, "text": "调整参数后，重新运行计算，对比同一场景下的结果。"}
  ]
}
```

Numbers in `start` and `end` are seconds. They are reserved speech windows, not an instruction to stretch each clip to fill all available time. Segments must be chronological, nonoverlapping, nonempty and within source duration. Keep the end a little before the recording finishes.

Optional fields:

| Field | Meaning |
|---|---|
| `crop` | `{"x": 4, "y": 114, "width": 1098, "height": 536}` in **source** pixels; null keeps all pixels. Coordinates/sizes must be even for the output codec. These sample coordinates are not a reusable preset. |
| `font_path` | Absolute or plan-relative path to a TTF/OTF/TTC. Fonts are not bundled. The helper tries common macOS, Windows and Linux CJK font locations and fontconfig; otherwise supply one. |
| `subtitle.font_size` | Pixels in output dimensions; default `max(22, round(output_width / 49))`. |
| `subtitle.margin_bottom` | Pixels from the bottom; default 10. Review after cropping. |
| `subtitle.max_chars` | Preferred maximum characters per caption; default 26, includes punctuation. |
| `original_audio` | `"mute"` (default) or `"duck"` (mix source audio at 15% amplitude). Duck requires an actual source audio stream. |
| `max_speedup` | Allowed pitch-preserving correction; default 1.18. The helper rejects values outside 1–1.25. Prefer rewriting over increasing it. |
| segment `audio_file` | Existing recording/provider output instead of Edge TTS. Paths resolve from the plan. Every segment may choose its own audio. |
| segment `boundaries_file` | Optional JSON list of Edge-format `WordBoundary` events, `offset`/`duration` in 100-nanosecond units and `text` matching the script. Applies to external audio only. Without it, caption timing is approximate and flagged in the receipt. |

Custom voice/rate examples must be verified against the provider's available voices. Arbitrary provider names are not accepted as voices. For a different provider, generate clips with that provider and use `audio_file`; the rest of the workflow is independent.

## Commands

```bash
python scripts/narrator.py inspect demo.mp4 --work work/inspection --interval 10
python scripts/narrator.py inspect demo.mp4 --work work/detail --interval 2 --start 40 --end 60
python scripts/narrator.py validate plan.json
python scripts/narrator.py build plan.json --work work/render --output output
python scripts/narrator.py verify output
```

`inspect` extracts full-resolution frames at actual sampled timestamps, creates bounded-size contact-sheet pages and writes `inspection.json`. It does not analyze scenes or author a script. The agent must open the images.

`build` validates first, synthesizes/caches each clip, checks pacing, generates word-aligned captions, normalizes audio and renders H.264/AAC MP4 with `+faststart`. It leaves the source unchanged. It writes a build receipt and a pending human/perceptual-review status. `verify` does a complete decode/audio check, validates SRT, checks technical metadata and generates QA frames. Its report still records that perceptual review is required.

A failed build has no success receipt. Review the error and fix its cause; do not present a partial MP4 as finished. A successful technical check does not establish content accuracy, pronunciation or visual quality.

## Dependencies and recovery

Use Python 3.10+; create a venv, upgrade pip, install `requirements.txt`. An old pip on macOS can mistakenly build packages from source or omit FFmpeg's binary wheel. Prefer a compatible wheel over installing unnecessary system build dependencies.

Prefer a supplied `FFMPEG_EXE` or system FFmpeg; otherwise use `imageio-ffmpeg`. The binary must provide `ass` (libass), `libx264` and AAC. The helper checks for these. FFprobe is not required.

Edge's community client can stop working when the upstream endpoint changes. This workflow was validated with `edge-tts 7.3.1`, `boundary="WordBoundary"`, `zh-CN-XiaoxiaoNeural`, `rate="+0%"`. SentenceBoundary is not an equivalent replacement for word timing. For a 403, allow one update attempt within the supported major version, then a small test. If still failing, explain the concrete failure and use user-approved clips/provider; do not hide a voice change. Network/429 failures get bounded retries. No credentials are harvested or stored.

FFmpeg `loudnorm` uses an analysis estimate in its single-pass mode; the helper targets -16 LUFS and -1.5 dBTP, then independently checks decoded peak/mean level. These checks are not a calibrated broadcast loudness certification. The narration output uses 48 kHz AAC. Caption proportional fallback, simulated media and technical checks are labeled honestly.
