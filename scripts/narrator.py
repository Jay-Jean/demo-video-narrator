#!/usr/bin/env python3
"""Portable, scene-grounded narration production. Agent authors the JSON plan."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import html
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import wave


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def ffmpeg():
    candidate = os.environ.get('FFMPEG_EXE') or shutil.which('ffmpeg')
    if not candidate:
        import imageio_ffmpeg
        candidate = imageio_ffmpeg.get_ffmpeg_exe()
    return str(Path(candidate).resolve())


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def probe(ff, video):
    p = subprocess.run([ff, '-hide_banner', '-i', str(video)], capture_output=True, text=True)
    info = p.stderr
    d = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', info)
    v = re.search(r'Video:.*?\b(\d{2,6})x(\d{2,6})\b', info)
    if not d or not v:
        raise ValueError('Cannot read video duration/dimensions: ' + info[-1500:])
    duration = int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3])
    return {'duration': duration, 'width': int(v[1]), 'height': int(v[2]),
            'has_audio': bool(re.search(r'Stream .*Audio:', info))}


def capabilities(ff):
    filters = run([ff, '-hide_banner', '-filters'], capture_output=True, text=True).stdout
    encoders = run([ff, '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
    if not re.search(r'\bass\s+V->V', filters):
        raise ValueError('FFmpeg needs libass (ass filter). Install a compatible FFmpeg build.')
    if 'libx264' not in encoders or not re.search(r'\baac\s', encoders):
        raise ValueError('FFmpeg must provide libx264 and AAC encoders.')


def finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be a finite number')
    return value


def resolve(base, path):
    p = Path(path).expanduser()
    return (base / p).resolve() if not p.is_absolute() else p.resolve()


def load_plan(path, ff):
    path = Path(path).resolve()
    plan = json.loads(path.read_text(encoding='utf-8'))
    if plan.get('version') != 1:
        raise ValueError('Plan version must be 1')
    base = path.parent
    video = resolve(base, plan['video'])
    if not video.is_file():
        raise ValueError(f'Video not found: {video}')
    meta = probe(ff, video)
    width, height = meta['width'], meta['height']
    crop = plan.get('crop')
    if crop is not None:
        for k in ('x', 'y', 'width', 'height'):
            n = crop.get(k)
            if type(n) is not int or n < 0 or n % 2:
                raise ValueError(f'crop.{k} must be a nonnegative even integer')
        if crop['width'] < 2 or crop['height'] < 2 or crop['x'] + crop['width'] > width or crop['y'] + crop['height'] > height:
            raise ValueError('Crop is empty or outside source video')
        width, height = crop['width'], crop['height']
    if width % 2 or height % 2:
        raise ValueError('Output needs even dimensions. Choose an explicit even crop.')
    speed = finite(plan.get('max_speedup', 1.18), 'max_speedup')
    if not 1 <= speed <= 1.25:
        raise ValueError('max_speedup must be in [1, 1.25]; rewrite overlong narration instead')
    voice = plan.get('voice', 'zh-CN-XiaoxiaoNeural')
    rate = plan.get('rate', '+0%')
    if not isinstance(voice, str) or not voice.strip() or not isinstance(rate, str) or not re.fullmatch(r'[+-]\d+%', rate):
        raise ValueError('Invalid voice/rate')
    audio_mode = plan.get('original_audio', 'mute')
    if audio_mode not in ('mute', 'duck'):
        raise ValueError('original_audio must be mute or duck')
    if audio_mode == 'duck' and not meta['has_audio']:
        raise ValueError('Cannot duck: source has no audio stream')
    segments = plan.get('segments')
    if not isinstance(segments, list) or not segments:
        raise ValueError('At least one narration segment is required')
    last = 0.0
    for i, seg in enumerate(segments):
        a, b = finite(seg.get('start'), f'segment {i}.start'), finite(seg.get('end'), f'segment {i}.end')
        if a < 0 or a < last or b <= a or b > meta['duration']:
            raise ValueError(f'Segment {i}: unordered, overlapping or outside source duration')
        text = seg.get('text')
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f'Segment {i}: text must be nonempty')
        seg['text'] = re.sub(r'\s+', ' ', text).strip()
        for key in ('audio_file', 'boundaries_file'):
            if key in seg:
                seg[key] = str(resolve(base, seg[key]))
                if not Path(seg[key]).is_file():
                    raise ValueError(f'Segment {i}: missing {key}')
        if 'boundaries_file' in seg and 'audio_file' not in seg:
            raise ValueError('boundaries_file applies to external audio_file only')
        last = b
    sub = plan.setdefault('subtitle', {})
    defaults = {'font_size': max(22, round(width / 49)), 'margin_bottom': 10, 'max_chars': 26}
    for k, value in defaults.items():
        sub.setdefault(k, value)
        if type(sub[k]) is not int or sub[k] < (0 if k == 'margin_bottom' else 1):
            raise ValueError(f'subtitle.{k} must be a valid integer')
    if sub['max_chars'] < 4 or sub['font_size'] + sub['margin_bottom'] + 10 >= height:
        raise ValueError('Subtitle settings do not fit the output frame')
    # The bundled style is intentionally one line. Require a new style for oversized captions.
    if sub['font_size'] * sub['max_chars'] > width - 80:
        raise ValueError('Caption line may exceed frame width: reduce max_chars or font_size')
    if plan.get('font_path'):
        plan['font_path'] = str(resolve(base, plan['font_path']))
    plan.update(video=str(video), voice=voice, rate=rate, max_speedup=speed, original_audio=audio_mode)
    return plan, meta, (width, height)


def find_font(plan):
    from PIL import ImageFont
    explicit = plan.get('font_path')
    paths = [explicit] if explicit else [
        '/System/Library/Fonts/STHeiti Medium.ttc',
        '/System/Library/Fonts/PingFang.ttc',
        str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'),
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc']
    if not explicit and shutil.which('fc-match'):
        p = run(['fc-match', '-f', '%{file}', ':lang=zh'], capture_output=True, text=True).stdout.strip()
        # Generic Latin fallback from fontconfig is not proof of CJK coverage.
        if any(token in p.lower() for token in ('cjk', 'han', 'hei', 'song', 'wenquanyi')):
            paths.append(p)
    for p in paths:
        if p and Path(p).is_file():
            font = ImageFont.truetype(str(p), 30)
            family = font.getname()[0].replace(',', ' ')
            return Path(p), family
    raise ValueError('No CJK font found. Set font_path to a suitable licensed TTF/OTF/TTC; no fonts are bundled.')


def caption_parts(text, maximum):
    """Partition exactly, favor punctuation; no dropped or duplicated characters."""
    parts, start = [], 0
    while start < len(text):
        limit = min(start + maximum, len(text))
        natural = [i + 1 for i in range(start, limit) if text[i] in '，。；！？,.!?;']
        end = next((x for x in natural if text[x - 1] in '。！？.!?' and x - start >= 6), None)
        if end is None:
            preferred = [x for x in natural if x - start >= min(9, maximum)]
            end = preferred[-1] if preferred else limit
        parts.append((start, end, text[start:end]))
        start = end
    return parts


def aligned_captions(text, boundaries, start, duration, speed, maximum):
    words, cursor = [], 0
    for e in boundaries:
        if e.get('type') != 'WordBoundary':
            continue
        token = html.unescape(e.get('text', ''))
        if not token:
            continue
        p = text.find(token, cursor)
        offset = finite(e.get('offset'), 'word offset') / 1e7 / speed
        if offset < 0:
            raise ValueError('Negative word offset')
        if p >= 0:
            words.append((p, p + len(token), offset))
            cursor = p + len(token)
    parts = caption_parts(text, maximum)
    starts, approximate = [], False
    for p, q, _ in parts:
        candidates = [z for x, y, z in words if x <= p < y or p <= x < q]
        if candidates:
            t = candidates[0]
        else:
            approximate = True
            t = duration * p / len(text)
        starts.append(start + t)
    starts[0] = start
    cues = []
    for i, (_, _, value) in enumerate(parts):
        a = starts[i]
        b = starts[i + 1] if i + 1 < len(starts) else start + duration
        if b <= a or a < start or b > start + duration + 0.05:
            raise ValueError('Invalid caption timing metadata; provide matching word alignment or revise the clip')
        cues.append((a, b, value))
    return cues, approximate


def srt_time(t):
    n = round(t * 1000)
    return f'{n // 3600000:02}:{n // 60000 % 60:02}:{n // 1000 % 60:02},{n % 1000:03}'


def ass_time(t):
    n = round(t * 100)
    return f'{n // 360000}:{n // 6000 % 60:02}:{n // 100 % 60:02}.{n % 100:02}'


def write_captions(cues, out, work, dimensions, style, family):
    (out / 'subtitles.srt').write_text('\n\n'.join(
        f'{i + 1}\n{srt_time(a)} --> {srt_time(b)}\n{t}' for i, (a, b, t) in enumerate(cues)) + '\n', encoding='utf-8')
    w, h = dimensions
    header = f'''[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{family},{style['font_size']},&H00FFFFFF,&H00FFFFFF,&H70000000,&H70000000,0,0,0,0,100,100,0,0,3,5,0,2,35,35,{style['margin_bottom']},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    def safe(t):
        return t.replace('\\', '＼').replace('{', '｛').replace('}', '｝')
    (work / 'captions.ass').write_text(header + ''.join(
        f'Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,,0,0,0,,{safe(t)}\n' for a, b, t in cues), encoding='utf-8')


async def synthesize(plan, cache):
    import edge_tts
    version = importlib.metadata.version('edge-tts')
    sem = asyncio.Semaphore(3)
    async def one(index, segment):
        if 'audio_file' in segment:
            events = json.loads(Path(segment['boundaries_file']).read_text(encoding='utf-8')) if segment.get('boundaries_file') else []
            return Path(segment['audio_file']), events, 'external'
        key = hashlib.sha256(json.dumps([segment['text'], plan['voice'], plan['rate'], version, 'WordBoundary'], ensure_ascii=False).encode()).hexdigest()
        audio, meta = cache / f'{key}.mp3', cache / f'{key}.json'
        if audio.exists() and meta.exists():
            receipt = json.loads(meta.read_text(encoding='utf-8'))
            if receipt.get('audio_sha256') == digest_file(audio):
                return audio, receipt['boundaries'], key
        async with sem:
            for attempt in range(3):
                tmp = cache / f'{key}.partial'
                try:
                    events = []
                    with tmp.open('wb') as f:
                        async for event in edge_tts.Communicate(segment['text'], plan['voice'], rate=plan['rate'], boundary='WordBoundary').stream():
                            if event['type'] == 'audio':
                                f.write(event['data'])
                            elif event['type'] == 'WordBoundary':
                                events.append(event)
                    if not tmp.stat().st_size or not events:
                        raise ValueError('Provider returned empty audio or no word boundaries')
                    tmp.replace(audio)
                    write_json(meta, {'audio_sha256': digest_file(audio), 'boundaries': events})
                    print(f'Voice clip {index + 1}/{len(plan["segments"])} ready', flush=True)
                    return audio, events, key
                except Exception as exc:
                    tmp.unlink(missing_ok=True)
                    if attempt == 2:
                        raise RuntimeError(f'Voice clip {index + 1} failed after 3 attempts; no silent provider fallback. {type(exc).__name__}: {exc}') from exc
                    await asyncio.sleep(1.5 * (attempt + 1))
    return await asyncio.gather(*(one(i, seg) for i, seg in enumerate(plan['segments'])))


def pcm(ff, path, speed=1):
    args = [ff, '-v', 'error', '-i', str(path)]
    if speed != 1:
        args += ['-af', f'atempo={speed:.9f}']
    return run(args + ['-ar', '24000', '-ac', '1', '-f', 's16le', '-'], capture_output=True).stdout


def write_zeros(wav, count):
    block = bytes(48000)
    while count:
        n = min(count, len(block))
        wav.writeframesraw(block[:n])
        count -= n


def build(args, ff):
    plan, meta, dims = load_plan(args.plan, ff)
    capabilities(ff)
    font, family = find_font(plan)
    out, work = Path(args.output).resolve(), Path(args.work).resolve()
    if out == work or out in work.parents or work in out.parents:
        raise ValueError('Output and work directories must be separate, nonnested locations')
    if out == Path(plan['video']).parent:
        raise ValueError('Use a dedicated output directory separate from the source video')
    if out.exists() and any(out.iterdir()) and not args.overwrite:
        raise ValueError('Output directory is nonempty; choose a new directory or pass --overwrite')
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    # Remove old success markers before any operation that could fail.
    for name in ('receipt.json', 'verification.json'):
        (out / name).unlink(missing_ok=True)
    cache = work / 'voice-cache'
    cache.mkdir(exist_ok=True)
    clips = asyncio.run(synthesize(plan, cache))
    all_cues, timing, cursor = [], [], 0
    wavpath = work / 'narration.wav'
    with wave.open(str(wavpath), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        for i, (seg, (audio, events, key)) in enumerate(zip(plan['segments'], clips)):
            raw = pcm(ff, audio)
            duration = len(raw) / 48000
            available = seg['end'] - seg['start'] - 0.08
            if duration <= 0 or available <= 0:
                raise ValueError(f'Segment {i + 1}: empty audio or insufficient speech window')
            speed = max(1.0, duration / available)
            if speed > plan['max_speedup']:
                raise ValueError(f'Segment {i + 1}: {duration:.2f}s speech needs {speed:.3f}x speed; ceiling {plan["max_speedup"]}. Shorten narration or revise its scene window.')
            if speed > 1:
                raw = pcm(ff, audio, speed)
            actual = len(raw) / 48000
            if seg['start'] + actual > seg['end'] + 0.005:
                raise ValueError(f'Segment {i + 1}: processed clip exceeds reserved window; revise narration')
            offset = round(seg['start'] * 24000) * 2
            if offset < cursor:
                raise ValueError('Decoded audio clips would overlap')
            write_zeros(wav, offset - cursor)
            wav.writeframesraw(raw)
            cursor = offset + len(raw)
            cues, approximate = aligned_captions(seg['text'], events, seg['start'], actual, speed, plan['subtitle']['max_chars'])
            all_cues.extend(cues)
            timing.append({'index': i + 1, 'start': seg['start'], 'end': seg['start'] + actual,
                           'reserved_end': seg['end'], 'original_duration': duration, 'speed': speed,
                           'alignment': 'approximate' if approximate else 'word', 'audio_sha256': digest_file(audio)})
        write_zeros(wav, max(0, round(meta['duration'] * 24000) * 2 - cursor))
    write_json(work / 'timing.json', timing)
    write_captions(all_cues, out, work, dims, plan['subtitle'], family)
    (out / 'narration.txt').write_text('\n\n'.join(f'{srt_time(s["start"])}\n{s["text"]}' for s in plan['segments']) + '\n', encoding='utf-8')
    # Deliver an editable plan beside the MP4; it may contain private source paths/text.
    # It is a user output, never a file to add to the public skill repository.
    write_json(out / 'narration-plan.json', plan)
    run([ff, '-y', '-v', 'error', '-i', wavpath, '-af', 'loudnorm=I=-16:TP=-1.5:LRA=7',
         '-ar', '48000', '-c:a', 'aac', '-b:a', '192k', out / 'narration.m4a'])
    fonts = work / 'fonts'
    fonts.mkdir(exist_ok=True)
    shutil.copyfile(font, fonts / ('subtitle' + font.suffix.lower()))
    vf = 'ass=captions.ass:fontsdir=fonts'
    if plan.get('crop'):
        c = plan['crop']
        vf = f'crop={c["width"]}:{c["height"]}:{c["x"]}:{c["y"]},' + vf
    args_ff = [ff, '-y', '-hide_banner', '-i', plan['video'], '-i', out / 'narration.m4a', '-vf', vf, '-map', '0:v:0']
    if plan['original_audio'] == 'duck':
        args_ff += ['-filter_complex', '[0:a:0]volume=0.15[bed];[1:a:0][bed]amix=inputs=2:duration=first:normalize=0[a]',
                    '-map', '[a]', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000']
    else:
        args_ff += ['-map', '1:a:0', '-c:a', 'copy']
    temp = out / 'video.partial.mp4'
    args_ff += ['-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
                '-t', str(meta['duration']), '-movflags', '+faststart', temp]
    print('Rendering video...', flush=True)
    with (work / 'render.log').open('w', encoding='utf-8') as log:
        run(args_ff, cwd=work, stdout=subprocess.DEVNULL, stderr=log)
    logtext = (work / 'render.log').read_text(encoding='utf-8', errors='replace')
    if re.search(r'Glyph .* not found|failed to find .*glyph|Error opening font', logtext, re.I):
        raise ValueError('Font rendering warning. Review work/render.log and choose an accessible CJK font.')
    temp.replace(out / 'video.mp4')
    write_json(out / 'receipt.json', {
        'status': 'built_requires_review', 'source_sha256': digest_file(plan['video']),
        'source': meta, 'output_dimensions': list(dims), 'crop': plan.get('crop'),
        'voice': plan['voice'], 'rate': plan['rate'], 'original_audio': plan['original_audio'],
        'font_family': family, 'edge_tts_version': importlib.metadata.version('edge-tts'),
        'segments': timing, 'perceptual_review': 'pending',
        'artifacts': {p.name: digest_file(p) for p in (out / 'video.mp4', out / 'narration.m4a', out / 'subtitles.srt', out / 'narration.txt', out / 'narration-plan.json')}})
    print(f'Built: {out / "video.mp4"}. Run verify, then review frames and listen.', flush=True)


def inspect(args, ff):
    from PIL import Image, ImageDraw
    video, work = Path(args.video).resolve(), Path(args.work).resolve()
    meta = probe(ff, video)
    begin, end = args.start, min(args.end if args.end is not None else meta['duration'], meta['duration'])
    if not math.isfinite(args.interval) or args.interval <= 0 or not 0 <= begin < end:
        raise ValueError('Invalid inspection interval/range')
    work.mkdir(parents=True, exist_ok=True)
    times = []
    t = begin
    while t < end - 0.001:
        times.append(t)
        t += args.interval
    frames = []
    for i, t in enumerate(times):
        target = work / f'frame_{i:04d}_{round(t * 1000):09d}ms.jpg'
        run([ff, '-y', '-v', 'error', '-ss', str(t), '-i', video, '-frames:v', '1', target])
        frames.append({'time': t, 'file': target.name})
    for page in range(0, len(frames), 12):
        group = frames[page:page + 12]
        thumbw = 640
        thumbh = max(1, round(meta['height'] * thumbw / meta['width']))
        sheet = Image.new('RGB', (thumbw * 2, (thumbh + 30) * math.ceil(len(group) / 2)), 'white')
        draw = ImageDraw.Draw(sheet)
        for j, f in enumerate(group):
            with Image.open(work / f['file']) as img:
                img = img.resize((thumbw, thumbh))
                x, y = j % 2 * thumbw, j // 2 * (thumbh + 30)
                sheet.paste(img, (x, y))
                draw.text((x + 8, y + thumbh + 5), f'{f["time"]:.3f} seconds', fill='black')
        sheet.save(work / f'contact_{page // 12 + 1:02d}.jpg')
    write_json(work / 'inspection.json', {'source': meta, 'frames': frames})
    print(f'Extracted {len(frames)} timestamped frames and contact sheets in {work}')


def parse_srt(path, duration):
    text = Path(path).read_text(encoding='utf-8').strip()
    cues, last = [], 0.0
    def seconds(s):
        h, m, sec = s.split(':')
        return int(h) * 3600 + int(m) * 60 + float(sec.replace(',', '.'))
    for block in re.split(r'\n\s*\n', text):
        lines = block.splitlines()
        if len(lines) < 3 or not re.fullmatch(r'\d+', lines[0]):
            raise ValueError('Malformed SRT block')
        m = re.fullmatch(r'(\d+:\d\d:\d\d,\d{3}) --> (\d+:\d\d:\d\d,\d{3})', lines[1])
        if not m:
            raise ValueError('Malformed SRT timestamp')
        a, b = seconds(m[1]), seconds(m[2])
        if a < last - 0.001 or b <= a or b > duration + 0.05:
            raise ValueError('SRT has overlap, invalid range or overrun')
        cues.append((a, b, '\n'.join(lines[2:])))
        last = b
    if not cues:
        raise ValueError('No subtitle cues')
    return cues


def verify(args, ff):
    out = Path(args.output).resolve()
    (out / 'verification.json').unlink(missing_ok=True)
    receipt = json.loads((out / 'receipt.json').read_text(encoding='utf-8'))
    for name, expected in receipt['artifacts'].items():
        if digest_file(out / name) != expected:
            raise ValueError(f'Artifact changed since build: {name}')
    video = out / 'video.mp4'
    meta = probe(ff, video)
    if abs(meta['duration'] - receipt['source']['duration']) > 0.15:
        raise ValueError('Output duration differs from source')
    if [meta['width'], meta['height']] != receipt['output_dimensions'] or not meta['has_audio']:
        raise ValueError('Wrong output dimensions or missing audio')
    cues = parse_srt(out / 'subtitles.srt', meta['duration'])
    result = run([ff, '-hide_banner', '-v', 'info', '-xerror', '-i', video, '-af', 'volumedetect', '-f', 'null', '-'], capture_output=True, text=True)
    (out / 'decode.log').write_text(result.stderr, encoding='utf-8')
    mean = re.search(r'mean_volume:\s*(-?\d+(?:\.\d+)?|-inf) dB', result.stderr)
    peak = re.search(r'max_volume:\s*(-?\d+(?:\.\d+)?|-inf) dB', result.stderr)
    if not mean or not peak or float(mean[1]) < -45 or float(peak[1]) >= -0.05:
        raise ValueError('Audio is missing, unexpectedly quiet or clipping; inspect decode.log')
    # Whole-file level checks are insufficient: ensure every scheduled clip is audible.
    clip_levels = []
    for seg in receipt['segments']:
        span = seg['end'] - seg['start']
        check = run([ff, '-v', 'info', '-ss', str(seg['start']), '-i', video, '-t', str(span), '-vn', '-af', 'volumedetect', '-f', 'null', '-'], capture_output=True, text=True)
        m = re.search(r'max_volume:\s*(-?\d+(?:\.\d+)?|-inf) dB', check.stderr)
        if not m or float(m[1]) < -45:
            raise ValueError(f'Scheduled segment {seg["index"]} has no audible signal')
        clip_levels.append({'index': seg['index'], 'peak_dbfs': float(m[1])})
    qa = out / 'qa-frames'
    qa.mkdir(exist_ok=True)
    # Every narration scene plus the last frame; open these before delivery.
    times = sorted(set([min(meta['duration'] - .1, (s['start'] + s['end']) / 2) for s in receipt['segments']] + [max(0, meta['duration'] - .2)]))
    for i, t in enumerate(times):
        run([ff, '-y', '-v', 'error', '-ss', str(t), '-i', video, '-frames:v', '1', qa / f'{i + 1:03d}_{t:.3f}s.jpg'])
    report = {'technical_status': 'passed', 'perceptual_review': 'pending', 'metadata': meta,
              'cue_count': len(cues), 'mean_dbfs': float(mean[1]), 'peak_dbfs': float(peak[1]),
              'clip_levels': clip_levels, 'qa_times': times,
              'approximate_alignment_segments': [s['index'] for s in receipt['segments'] if s['alignment'] != 'word']}
    write_json(out / 'verification.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('Technical checks passed. Review QA frames and listen; perceptual review is still pending.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('inspect')
    p.add_argument('video'); p.add_argument('--work', required=True)
    p.add_argument('--interval', type=float, default=10); p.add_argument('--start', type=float, default=0); p.add_argument('--end', type=float)
    p = sub.add_parser('validate'); p.add_argument('plan')
    p = sub.add_parser('build'); p.add_argument('plan'); p.add_argument('--work', required=True); p.add_argument('--output', required=True); p.add_argument('--overwrite', action='store_true')
    p = sub.add_parser('verify'); p.add_argument('output')
    args = parser.parse_args()
    try:
        ff = ffmpeg()
        if args.command == 'inspect': inspect(args, ff)
        elif args.command == 'build': build(args, ff)
        elif args.command == 'verify': verify(args, ff)
        else:
            plan, meta, dims = load_plan(args.plan, ff)
            capabilities(ff)
            font, family = find_font(plan)
            print(json.dumps({'valid': True, 'source': meta, 'output_dimensions': dims, 'font_family': family, 'segments': len(plan['segments'])}, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
