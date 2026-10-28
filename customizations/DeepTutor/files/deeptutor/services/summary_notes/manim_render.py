"""Isolated, cancellable Manim rendering with no model-code execution."""
import asyncio
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from deeptutor.services.file_io import atomic_write_json
from deeptutor.services.path_service import get_path_service


def manim_python():
    override = os.environ.get("DEEPTUTOR_MANIM_PYTHON")
    path = Path(override) if override else get_path_service().project_root / "tools/manim/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not path.is_file():
        raise ValueError("Manim 渲染环境尚未安装，请先配置 Manim 独立运行环境。")
    return path


async def render_manim(plan: dict, output: Path, progress):
    output.mkdir(parents=True, exist_ok=True)
    story = output / "storyboard.json"
    atomic_write_json(story, plan)
    semantic = plan.get('template_id') == 'manim-review-v2'
    exact = semantic or plan.get('template_id') == 'manim-quick-review-v1'
    scene = Path(__file__).with_name('manim_semantic_scene.py' if semantic else "manim_exact_scene.py" if exact else "manim_scene.py")
    # Model credentials are not needed by the drawing subprocess.
    env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
    env.update(MANIM_REVIEW_PLAN=str(story), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    # Manim adds several directory levels; Windows' 260-character limit makes
    # deeply nested note/session paths unsuitable for partial movie files.
    cache_root = (get_path_service().project_root / "tools/manim/render").resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix="mv-", dir=cache_root)
    media = Path(temporary.name).resolve()
    assert media.is_relative_to(cache_root) and media.name.startswith("mv-")
    args = [str(manim_python()), "-m", "manim", str(scene), "AutoReview", "--media_dir", str(media), "--output_file", "review", "--format", "mp4", "--disable_caching", "--progress_bar", "none", "--verbosity", "WARNING", "-r", "1920,1080", "--fps", "30"]
    process = None
    try:
        process = await asyncio.create_subprocess_exec(*args, cwd=output, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        async def consume():
            with (output / "render.log").open("wb") as log:
                while line := await process.stdout.readline():
                    log.write(line)
                    match = re.search(rb"MANIM_REVIEW_PROGRESS=(\d+)/(\d+)", line)
                    if match:
                        progress(int(match[1]), int(match[2]))
            return await process.wait()
        status = await asyncio.wait_for(consume(), 1200)
        if status:
            raise ValueError("Manim 渲染失败，AI 分镜和渲染日志已保留，可重新渲染而不再次调用模型。")
        candidates = list(media.rglob("review.mp4"))
        if len(candidates) != 1 or candidates[0].stat().st_size < 1000:
            raise ValueError("Manim 未输出完整视频，分镜已保留。")
        if exact:
            # Final normalization matches the reference finish.py; duration is
            # selected by the model and validated independently from styling.
            # 1080p30 TV range, H.264 CRF18, and the supplied reference soundtrack.
            probe = await asyncio.create_subprocess_exec(str(manim_python()), '-c', 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())', stdout=asyncio.subprocess.PIPE, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            stdout, _ = await probe.communicate()
            ffmpeg = stdout.decode().strip()
            configured_music = os.environ.get('DEEPTUTOR_REVIEW_MUSIC')
            music = Path(configured_music) if configured_music else scene.parent / 'quick_review_v1/reference-music.m4a'
            if configured_music and not music.is_file():
                raise ValueError('配置的复习视频配乐不存在，请检查 DEEPTUTOR_REVIEW_MUSIC 路径。')
            metadata = output / 'chapters.txt'
            chapter_lines = [';FFMETADATA1']
            start = 0
            for item in plan['scenes']:
                end = start + round(item['duration'] * 1000)
                title = (item['title'] if semantic else item['texts']['title']).replace('\\', '\\\\').replace('=', '\\=').replace(';', '\\;').replace('#', '\\#')
                chapter_lines.extend(['[CHAPTER]', 'TIMEBASE=1/1000', f'START={start}', f'END={end}', f'title={title}'])
                start = end
            metadata.write_text('\n'.join(chapter_lines), encoding='utf8')
            args = [ffmpeg, '-y', '-i', str(candidates[0]), '-i', str(music), '-i', str(metadata), '-map', '0:v:0', '-map', '1:a:0', '-map_chapters', '2', '-map_metadata', '2', '-vf', 'fps=30,tpad=stop_mode=clone:stop_duration=1,scale=1920:1080:in_range=auto:out_range=tv,setsar=1,format=yuv420p', '-color_range', 'tv', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-c:a', 'copy', '-t', '50', '-movflags', '+faststart', str(output/'video.mp4')]
            duration = sum(item['duration'] for item in plan['scenes'])
            args[args.index('-t')+1] = str(duration)
            if not music.is_file():
                # Public source distributions do not include the user's music.
                # Export a complete silent MP4 instead of failing after AI use.
                args = [ffmpeg,'-y','-i',str(candidates[0]),'-i',str(metadata),'-map','0:v:0','-map_chapters','1','-map_metadata','1','-vf','fps=30,tpad=stop_mode=clone:stop_duration=1,scale=1920:1080:in_range=auto:out_range=tv,setsar=1,format=yuv420p','-color_range','tv','-c:v','libx264','-preset','fast','-crf','18','-an','-t',str(duration),'-movflags','+faststart',str(output/'video.mp4')]
            elif duration != 50:
                music_index = args.index(str(music)) - 1
                args[music_index:music_index] = ['-stream_loop', '-1']
                args[args.index('-c:a')+1] = 'aac'
                args[-1:-1] = ['-b:a','192k','-af',f'afade=t=out:st={max(0,duration-1)}:d=1']
            with (output/'finish.log').open('wb') as log:
                process = await asyncio.create_subprocess_exec(*args, env=env, stdout=log, stderr=asyncio.subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                if await asyncio.wait_for(process.wait(), 300):
                    raise ValueError('固定模板视频封装失败，分镜与日志已保留。')
        else:
            shutil.copy2(candidates[0], output / "video.mp4")
    finally:
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        # Only remove the unique temporary directory created above.
        assert Path(temporary.name).resolve().is_relative_to(cache_root)
        temporary.cleanup()
