"""Portable source-ZIP renderer: python quick_review_v1/render.py."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent.parent
plan = json.loads((ROOT / 'storyboard.json').read_text(encoding='utf8'))
env = dict(os.environ, MANIM_REVIEW_PLAN=str(ROOT/'storyboard.json'), PYTHONUTF8='1')
scene = ROOT/'manim_scene.py'
if not scene.exists():
    scene = ROOT/'manim_exact_scene.py'
with tempfile.TemporaryDirectory(prefix='manim-review-') as media:
    subprocess.run([sys.executable, '-m', 'manim', str(scene), 'AutoReview', '--media_dir', media, '--output_file', 'review', '--disable_caching', '-r', '1920,1080', '--fps', '30'], env=env, check=True)
    silent = next(Path(media).rglob('review.mp4'))
    duration = sum(s['duration'] for s in plan['scenes'])
    music=Path(os.environ.get('DEEPTUTOR_REVIEW_MUSIC',str(ROOT/'quick_review_v1/reference-music.m4a')))
    inputs=['-stream_loop','-1','-i',str(music),'-map','0:v:0','-map','1:a:0'] if music.is_file() else ['-map','0:v:0']
    audio=(['-c:a','copy'] if duration == 50 else ['-c:a','aac','-b:a','192k','-af',f'afade=t=out:st={max(0,duration-1)}:d=1']) if music.is_file() else ['-an']
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-i', str(silent), *inputs, '-vf', 'fps=30,tpad=stop_mode=clone:stop_duration=1,scale=1920:1080:in_range=auto:out_range=tv,setsar=1,format=yuv420p', '-color_range', 'tv', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', *audio, '-t', str(duration), '-movflags', '+faststart', str(ROOT/'video.mp4')], check=True)
