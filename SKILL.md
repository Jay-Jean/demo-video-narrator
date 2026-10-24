---
name: demo-video-narrator
description: Turn a screen recording or product demonstration into a polished narrated video with scene-grounded explanations, natural Mandarin voiceover and synchronized burned-in subtitles. Use for 演示视频配音、讲解字幕、录屏解说 or a leadership-facing demo; not simple verbatim transcription, slide-to-video conversion or voice cloning.
---

# Demo Video Narrator

Produce a finished MP4, matching SRT, standalone narration and editable narration plan. The distinguishing work is understanding the demonstration and writing an explanation that follows it; TTS alone is not sufficient.

## Before producing audio

1. Inspect the source with `scripts/narrator.py inspect`. Open the timestamped contact sheets and individual full-resolution frames. Sample densely around state changes; a coarse sheet alone can miss a result, warning, menu selection or transition. If the source has speech, inspect/transcribe it with an available audio tool before deciding whether to retain it.
2. Infer language, audience and presentation style from the request/history. Default to clear Mandarin with `zh-CN-XiaoxiaoNeural`, neutral pitch and natural pace. Preserve established preferences. Clarify only genuinely missing decisions that prevent useful work.
3. Describe what appears, why it matters and what changes next. Read [the narration guide](references/narration-guide.md) before drafting. Distinguish visible functionality, illustrative predictions, calculated results, measured evidence and future goals. Do not invent performance improvements or treat a prototype as deployed production capability.
4. Build an editable JSON plan using [the plan reference](references/plan.md). Reserve real timeline windows per scene; start around 3.5–4.5 Chinese characters/second including pauses. Let some visual actions breathe. This is a drafting estimate: synthesize and measure rather than assuming speech length from characters.
5. Preserve original duration and actions unless editing is requested. Crop browser/desktop borders when requested or already established, using observed pixel bounds. Keep the complete requested interface. Do not reuse another video's coordinates. An already clean recording needs no crop. Validate the crop on early, middle and final frames.

## Voice, timing and subtitles

- Preferred provider: the community `edge-tts` client, voice **`zh-CN-XiaoxiaoNeural`**. This is the exact provider/voice combination used for the reference workflow, not a claim that it is an OpenAI voice or guaranteed to remain available. `boundary="WordBoundary"` is essential: current clients otherwise may return sentence-level events only.
- Edge sends narration text to Microsoft's online speech endpoint. Keep private scripts local when required; use per-segment `audio_file` recordings or an approved provider instead. The source video is never uploaded by the helper. Do not silently change voice/provider after a service failure.
- Generate separate clips per timeline window with at most three concurrent requests. Cache by text, voice, rate and client version; retry transient failures up to three times total. A bounded client update can resolve outdated-endpoint 403 errors. Do not loop forever, bypass authentication or substitute silent audio.
- Measure decoded PCM. Small tempo correction is acceptable; default ceiling is **1.18×**, preserving pitch. If a clip exceeds it, shorten the script or revise the scene windows based on the video. Do not truncate speech, overlap it or silently accelerate the whole demonstration.
- Derive caption timing from TTS word events and scale the offsets by the tempo change. If external audio lacks alignment, proportional timing is an explicitly recorded approximation and requires extra listening/visual review.
- Break captions at natural phrases, normally 12–26 Chinese characters per line. Match caption wording to the spoken script. Place white text on a restrained translucent dark box in a quiet part of the frame; use a real CJK font. At 1474×720, a useful starting point is 30 px with a 10 px bottom margin. Re-evaluate after any crop; do not cover key controls/results or leave subtitles outside the new frame.
- Keep or duck useful original audio only when appropriate; the default for silent UI recordings is narration only. Do not add music unless requested.

## Execute and verify

Use Python 3.10+ and an isolated environment. Install `requirements.txt` with a modern pip. The helper accepts a system FFmpeg or `imageio-ffmpeg` binary; **libass is required**. No paid API key is needed for Edge, but the online service is best effort and subject to its own terms/availability.

```bash
python scripts/narrator.py inspect /absolute/path/demo.mp4 --work /absolute/path/work
python scripts/narrator.py validate /absolute/path/plan.json
python scripts/narrator.py build /absolute/path/plan.json --work /absolute/path/work --output /absolute/path/output
python scripts/narrator.py verify /absolute/path/output
```

The helper writes MP4, M4A, SRT, narration text, QA frames and a machine-readable receipt. `verify` decodes the complete file, checks timing/audio and extracts frames; **a technical pass does not replace perception**. Open QA frames across all stages and transition points; listen to the opening, a dense passage, transitions, any tempo-adjusted clips, and the ending with the agent's available audio/video tools. Check pronunciation, pacing, actual event timing, missing glyphs, layout and the absence of clipping. If audio perception is unavailable, state that limitation rather than claiming a listening check.

Fix demonstrated defects, rerun the affected stages and verify again. Deliver the video first, then useful source files. Report material limitations briefly. Never include private source videos, scripts, screenshots, local absolute paths or client-specific identifiers in a public skill repository; use synthetic examples.

## Portability

Resolve scripts and references relative to this skill directory. No Codex-only tool, browser integration, OS voice or another skill is required. Any agent with file, shell, image-reading and audio/video-review tools can follow this workflow. Agents without native skill discovery can read this `SKILL.md` directly and execute the commands. See the repository README for installation and a provider-independent audio-input route.
