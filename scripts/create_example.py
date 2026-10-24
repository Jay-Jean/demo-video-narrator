#!/usr/bin/env python3
"""Create a nonprivate synthetic demo and editable narration plan for a smoke test."""
from pathlib import Path
import argparse
import json
import subprocess
from PIL import Image, ImageDraw, ImageFont
from narrator import ffmpeg, find_font


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'demo.mp4').exists() or (out / 'plan.json').exists():
        parser.error('Choose a new example directory; existing demo/plan will not be overwritten')
    font, family = find_font({})
    large, small = ImageFont.truetype(str(font), 30), ImageFont.truetype(str(font), 23)
    titles = ['选择演示场景', '调整参数', '比较结果']
    for i, title in enumerate(titles):
        image = Image.new('RGB', (1280, 720), '#cbd5e1')
        d = ImageDraw.Draw(image)
        d.text((20, 10), 'Synthetic browser header — example only', font=small, fill='#334155')
        d.rectangle((0, 48, 1279, 695), fill='#0d1b29')
        d.text((24, 68), '演示平台 · 合成示例', font=large, fill='white')
        d.line((0, 116, 1280, 116), fill='#334155', width=2)
        d.text((28, 148), titles[0], font=small, fill='#38bda5' if i == 0 else '#94a3b8')
        d.text((28, 204), titles[1], font=small, fill='#38bda5' if i == 1 else '#94a3b8')
        d.text((28, 260), titles[2], font=small, fill='#38bda5' if i == 2 else '#94a3b8')
        d.rounded_rectangle((250, 142, 1010, 568), radius=15, fill='#153344')
        d.text((280, 164), title, font=large, fill='white')
        for j in range(8):
            x = 290 + j * 82
            height = 80 + (j * 29 + i * 43) % 200
            d.rectangle((x, 520 - height, x + 40, 520), fill=['#52748c', '#37bba5', '#f6c85f'][i])
        d.text((1040, 170), '参数 A', font=small, fill='#cbd5e1')
        d.text((1040, 215), str(10 + i * 5), font=large, fill='#38bda5')
        d.text((270, 598), '用于验证制作流程，不代表真实产品或性能结果', font=small, fill='#94a3b8')
        d.text((20, 698), 'Synthetic desktop footer', font=ImageFont.truetype(str(font), 14), fill='#334155')
        image.save(out / f'stage_{i}.png')
    listing = ''.join(f"file 'stage_{i}.png'\nduration 8\n" for i in range(3)) + "file 'stage_2.png'\n"
    (out / 'frames.txt').write_text(listing, encoding='utf-8')
    subprocess.run([ffmpeg(), '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', 'frames.txt',
                    '-r', '24', '-t', '24', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', 'demo.mp4'], cwd=out, check=True)
    plan = {'version': 1, 'video': 'demo.mp4', 'voice': 'zh-CN-XiaoxiaoNeural', 'rate': '+0%',
            'font_path': str(font), 'max_speedup': 1.18, 'original_audio': 'mute',
            'crop': {'x': 0, 'y': 48, 'width': 1280, 'height': 648},
            'subtitle': {'font_size': 27, 'margin_bottom': 12, 'max_chars': 26},
            'segments': [
                {'start': .5, 'end': 7.7, 'text': '首先选择演示场景，查看平台中的数据与运行状态。'},
                {'start': 8.5, 'end': 15.7, 'text': '接下来调整参数，观察同一场景下的展示变化。'},
                {'start': 16.5, 'end': 23.7, 'text': '最后对比结果，用于验证字幕、配音和画面的同步。'}]}
    (out / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Created synthetic demo and plan in {out}')


if __name__ == '__main__':
    main()
