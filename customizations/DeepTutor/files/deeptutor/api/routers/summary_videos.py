"""Persisted DeepSeek video planning jobs, independent of note revisions."""
import asyncio
import json
import re
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from deeptutor.services.file_io import atomic_write_json
from deeptutor.services.path_service import get_path_service
from deeptutor.services.summary_notes.semantic_video_plan import STORYBOARD_PROMPT as PROMPT, validate_storyboard as validate_video_plan

router = APIRouter()
jobs: dict[tuple[str, str, str], asyncio.Task] = {}


class PlanRequest(BaseModel):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    target_seconds: int | None = Field(default=None, ge=30, le=120)
    instructions: str = Field(default="", max_length=1200)
    confirm_api_cost: bool = False


def folder(session_id: str, turn_id: str):
    if not all(re.fullmatch(r"[a-f0-9]{32}", value) for value in (session_id, turn_id)):
        raise HTTPException(404, "笔记不存在。")
    return get_path_service().get_workspace_dir() / "summary_video_plans" / session_id / turn_id


def job_path(session_id: str, turn_id: str, job_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(404, "视频任务不存在。")
    return folder(session_id, turn_id) / f"{job_id}.json"


def public(data):
    result = {k: v for k, v in data.items() if k not in {"draft", "first_draft", "brief_draft", "notes"}}
    key = (data["session_id"], data["turn_id"], data["id"])
    if result["status"] in {"queued", "summarizing", "planning", "planned", "rendering"} and key not in jobs:
        result.update(status="interrupted", error="服务重启导致任务中断；不会自动重试或再次调用模型。")
    return result


def load(session_id, turn_id, job_id):
    try:
        return json.loads(job_path(session_id, turn_id, job_id).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(404, "视频任务不存在。") from None


async def run_plan(data, notes):
    from .summary_notes import generation_lock
    key = (data["session_id"], data["turn_id"], data["id"])
    path = job_path(*key)
    chunks = []
    try:
        async with generation_lock:
            from deeptutor.services.llm import get_llm_config, get_token_limit_kwargs, clean_thinking_tags
            from deeptutor.services.llm.factory import stream
            from deeptutor.services.llm.types import StreamOutcome
            config = get_llm_config()
            if config.binding != 'deepseek' and 'deepseek' not in config.model.lower():
                raise ValueError('请在模型设置中选择 DeepSeek；复习视频的所有 AI 步骤均使用 DeepSeek。')
            from deeptutor.services.summary_notes.video_brief import BRIEF_PROMPT, validate_brief, source_units, resolve_storyboard_sources, brief_cache_key
            data.update(status="summarizing", model=config.model, provider=config.binding, pipeline_version=3, api_calls=data.get('api_calls',0), compute={'ai':'DeepSeek API','render':'local-manim'})
            atomic_write_json(path, data)

            async def ask(system, messages):
                chunks.clear()
                outcome = StreamOutcome()
                data['api_calls'] += 1
                atomic_write_json(path, data)
                async def consume():
                    async for chunk in stream(prompt="", system_prompt=system, messages=messages, model=config.model, api_key=config.api_key, base_url=config.base_url, binding=config.binding, api_version=config.api_version, extra_headers=config.extra_headers, max_retries=0, outcome=outcome, temperature=0.15, response_format={'type':'json_object'}, extra_body={"thinking": {"type": "disabled"}}, **get_token_limit_kwargs(config.model, 12000)):
                        chunks.append(chunk)
                        if sum(map(len, chunks)) > 100000:
                            raise ValueError("模型输出超出限制，已停止并保留草稿。")
                await asyncio.wait_for(consume(), 300)
                return clean_thinking_tags("".join(chunks), config.binding, config.model).strip(), outcome.finish_reason

            # Stage one sees the original note, with no animation template burden.
            input_hash = brief_cache_key(notes,data['instructions'])
            if data.get('review_brief') and data.get('brief_input_hash') == input_hash:
                brief_raw, brief_finish = json.dumps(data['review_brief'],ensure_ascii=False), 'cached'
            else:
                first_payload = {"title": data["note_title"], "note_passages": source_units(notes), "requirements": data["instructions"]}
                brief_raw, brief_finish = await ask(BRIEF_PROMPT, [{"role":"system","content":BRIEF_PROMPT},{"role":"user","content":json.dumps(first_payload,ensure_ascii=False)}])
                data['brief_draft'] = brief_raw
            brief = validate_brief(brief_raw, notes, brief_finish)
            data.update(review_brief=brief.model_dump(), status="planning", brief_finish_reason=brief_finish, brief_input_hash=input_hash)
            atomic_write_json(path, data)

            # Stage two receives only the concise brief plus traceable quotations.
            # The original full note stays local for final source validation.
            system = PROMPT
            payload = {"review_brief": brief.model_dump(), "requirements":data["instructions"], "duration_mode":"按复习稿内容密度判断页数和每页时长"}
            messages = [{"role":"system","content":system},{"role":"user","content":json.dumps(payload,ensure_ascii=False)}]
            raw, finish_reason = await ask(system, messages)
            data['draft'] = raw
            try:
                plan = validate_video_plan(resolve_storyboard_sources(raw, brief), notes, finish_reason)
            except ValueError as validation_error:
                data.update(first_draft=raw, repair_count=1, validation_error=str(validation_error))
                atomic_write_json(path, data)
                messages.extend([{"role":"assistant","content":raw},{"role":"user","content":"根据精简复习稿修正校验问题。优先用keyphrase和screen_text，完整解释不塞进短槽。只返回完整JSON。\n"+str(validation_error)}])
                raw, finish_reason = await ask(system, messages)
                data['draft'] = raw
                plan = validate_video_plan(resolve_storyboard_sources(raw, brief), notes, finish_reason)
            data.update(status="planned", plan=plan.model_dump(), finish_reason=finish_reason)
            atomic_write_json(path, data)
        await run_render(data)
    except asyncio.CancelledError:
        data.update(status="cancelled", error="已取消本次分镜生成；已发出的模型请求可能产生用量。")
    except ValueError as exc:
        data.update(status="failed", error=str(exc))
    except Exception:
        data.update(status="failed", error="DeepSeek 连接、余额或响应异常；没有自动重试，请检查模型设置后手动重试。")
    finally:
        data["draft"] = data.get("draft") or "".join(chunks)
        data["updated_at"] = time.time()
        atomic_write_json(path, data)
        jobs.pop(key, None)


async def run_render(data):
    from deeptutor.services.summary_notes.manim_render import render_manim
    key = (data["session_id"], data["turn_id"], data["id"])
    path = job_path(*key)
    try:
        data.update(status="rendering", progress=0, error="")
        atomic_write_json(path, data)
        def progress(current, total):
            data.update(progress=round(current/total*100), rendered_scenes=current)
            atomic_write_json(path, data)
        await render_manim(data["plan"], folder(key[0], key[1]) / key[2], progress)
        data.update(status="complete", progress=100, video=True)
    except asyncio.CancelledError:
        data.update(status="cancelled", error="任务已取消；AI 分镜已保留。")
    except ValueError as exc:
        data.update(status="failed", error=str(exc))
    except Exception:
        data.update(status="failed", error="Manim 渲染异常；分镜已保留，可重新渲染而不再次调用 DeepSeek。")
    finally:
        data["updated_at"] = time.time()
        atomic_write_json(path, data)
        jobs.pop(key, None)


@router.post("/{session_id}/turns/{turn_id}/video-plans", status_code=202)
async def create_plan(session_id: str, turn_id: str, body: PlanRequest):
    from .summary_exams import turn_for
    from .summary_notes import generation_lock
    from deeptutor.services.llm import get_llm_config
    _, turn = turn_for(session_id, turn_id)
    path = job_path(session_id, turn_id, body.request_id)
    if path.exists():
        return public(load(session_id, turn_id, body.request_id))
    if not body.confirm_api_cost:
        raise HTTPException(400, "本次将调用你配置的 DeepSeek 并产生 API 用量。")
    if generation_lock.locked() or jobs:
        raise HTTPException(409, "另一项笔记、试卷或视频分镜正在生成，请稍后再试。")
    if not turn.get("notes", "").strip() or len(turn["notes"]) > 40000:
        raise HTTPException(400, "请先完成 AI 笔记；单次笔记不能超过4万字。")
    config = get_llm_config()
    if config.binding != "deepseek" and "deepseek" not in config.model.lower():
        raise HTTPException(400, "请先在模型设置中选择你已配置的 DeepSeek；本模块不会自动切换到其它模型。")
    from deeptutor.services.summary_notes.manim_render import manim_python
    try:
        manim_python()  # Fail before calling a paid model if the renderer is missing.
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    data = {"id": body.request_id, "session_id": session_id, "turn_id": turn_id, "note_title": turn.get("title", "学习笔记"), "renderer": "manim", "status": "queued", "created_at": time.time(), "updated_at": time.time(), "target_seconds": body.target_seconds, "instructions": body.instructions, "plan": None, "error": "", "video": False, "progress": 0}
    atomic_write_json(path, data)
    key = (session_id, turn_id, body.request_id)
    jobs[key] = asyncio.create_task(run_plan(data, turn["notes"]))
    return public(data)


@router.get("/{session_id}/turns/{turn_id}/video-plans")
async def list_plans(session_id: str, turn_id: str):
    from .summary_exams import turn_for
    turn_for(session_id, turn_id)
    result = []
    for path in folder(session_id, turn_id).glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("renderer") == "manim":
                result.append(public(data))
        except (ValueError, KeyError, OSError):
            continue
    return {"jobs": sorted(result, key=lambda x: x["created_at"], reverse=True)}


@router.get("/{session_id}/turns/{turn_id}/video-plans/{job_id}")
async def get_plan(session_id: str, turn_id: str, job_id: str):
    return public(load(session_id, turn_id, job_id))


@router.delete("/{session_id}/turns/{turn_id}/video-plans/{job_id}")
async def cancel_plan(session_id: str, turn_id: str, job_id: str):
    data = load(session_id, turn_id, job_id)
    task = jobs.get((session_id, turn_id, job_id))
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            jobs.pop((session_id, turn_id, job_id), None)
        data = load(session_id, turn_id, job_id)
        if data["status"] in {"queued", "summarizing", "planning", "rendering", "planned"}:
            data.update(status="cancelled", error="已取消本次分镜生成；已发出的模型请求可能产生用量。")
            atomic_write_json(job_path(session_id, turn_id, job_id), data)
    return public(load(session_id, turn_id, job_id) if task else data)


@router.post("/{session_id}/turns/{turn_id}/video-plans/{job_id}/render", status_code=202)
async def rerender(session_id: str, turn_id: str, job_id: str):
    data = load(session_id, turn_id, job_id)
    if not data.get("plan") or data.get("renderer") != "manim":
        raise HTTPException(400, "没有可渲染的 Manim 分镜。")
    if jobs:
        raise HTTPException(409, "另一条视频正在制作，请稍后重试。")
    data.update(status="rendering", progress=0, error="", video=False)
    atomic_write_json(job_path(session_id, turn_id, job_id), data)
    jobs[(session_id, turn_id, job_id)] = asyncio.create_task(run_render(data))
    return public(data)


@router.get("/{session_id}/turns/{turn_id}/video-plans/{job_id}/file")
async def video_file(session_id: str, turn_id: str, job_id: str, inline: bool = False):
    data = load(session_id, turn_id, job_id)
    path = folder(session_id, turn_id) / job_id / "video.mp4"
    if data.get("status") != "complete" or not data.get("video") or not path.is_file():
        raise HTTPException(404, "视频尚未生成完整。")
    return FileResponse(path, media_type="video/mp4", filename="Manim-复习视频.mp4", content_disposition_type="inline" if inline else "attachment", headers={"Cache-Control": "no-store"})


@router.post('/{session_id}/turns/{turn_id}/video-plans/{job_id}/continue', status_code=202)
async def continue_from_brief(session_id: str, turn_id: str, job_id: str):
    from .summary_notes import generation_lock
    from .summary_exams import turn_for
    from deeptutor.services.summary_notes.video_brief import brief_cache_key
    data=load(session_id,turn_id,job_id)
    _,turn=turn_for(session_id,turn_id)
    if jobs or generation_lock.locked():
        raise HTTPException(409,'另一项任务正在生成，请稍后重试。')
    if not data.get('review_brief') or data.get('plan'):
        raise HTTPException(400,'没有可继续的复习稿，已有分镜请使用重新渲染。')
    if data.get('brief_input_hash') != brief_cache_key(turn['notes'],data['instructions']):
        raise HTTPException(409,'原笔记已经变化，请重新整理复习稿。')
    data.update(status='planning',error='',progress=0)
    atomic_write_json(job_path(session_id,turn_id,job_id),data)
    jobs[(session_id,turn_id,job_id)]=asyncio.create_task(run_plan(data,turn['notes']))
    return public(data)


@router.get("/{session_id}/turns/{turn_id}/video-plans/{job_id}/source")
async def source_file(session_id: str, turn_id: str, job_id: str):
    data = load(session_id, turn_id, job_id)
    if not data.get("plan") or data.get("renderer") != "manim":
        raise HTTPException(404, "Manim 分镜尚未生成。")
    output = folder(session_id, turn_id) / job_id
    output.mkdir(parents=True, exist_ok=True)
    path = output / "Manim-source.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        service = Path(__file__).parents[2] / "services/summary_notes"
        semantic = data['plan'].get('template_id') == 'manim-review-v2'
        exact = semantic or data['plan'].get('template_id') == 'manim-quick-review-v1'
        archive.write(service / ('manim_semantic_scene.py' if semantic else 'manim_exact_scene.py' if exact else 'manim_scene.py'), 'manim_scene.py')
        if exact:
            archive.write(service / 'template_geometry.py', 'template_geometry.py')
            for asset in (service / 'quick_review_v1').iterdir():
                if asset.is_file():
                    archive.write(asset, 'quick_review_v1/' + asset.name)
            archive.write(service / 'exact_video_plan.py', 'exact_video_plan.py')
            if semantic:
                archive.write(service / 'semantic_video_plan.py', 'semantic_video_plan.py')
        archive.writestr("storyboard.json", json.dumps(data["plan"], ensure_ascii=False, indent=2))
        if data.get('review_brief'):
            archive.writestr('review-brief.json', json.dumps(data['review_brief'], ensure_ascii=False, indent=2))
            archive.write(service / 'video_brief.py', 'video_brief.py')
        archive.writestr("README.txt", "安装 manim==0.22.0 和 imageio-ffmpeg，并安装 Microsoft YaHei 字体。\n运行：python quick_review_v1/render.py\n新版本修改storyboard.json的cards内容；旧模板修改texts。\n所有AI步骤调用DeepSeek API；MP4由本地Manim/FFmpeg执行。")
    return FileResponse(path, media_type="application/zip", filename="Manim-复习视频源码.zip")
