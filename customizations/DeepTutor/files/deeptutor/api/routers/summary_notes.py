"""Simple durable note chats: one model call, then local template export."""

from __future__ import annotations

import asyncio
import json
import re
import time
from urllib.parse import quote
import uuid

from fastapi import APIRouter, HTTPException, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from deeptutor.services.file_io import atomic_write_json, atomic_write_text
from deeptutor.services.path_service import get_path_service
from deeptutor.services.summary_notes.render import ASSETS, COMPLETE, render_html, validate_notes

from deeptutor.services.summary_notes.enex import export_enex

router = APIRouter(prefix="/summary-notes")
generation_lock = asyncio.Lock()


def directory():
    folder = get_path_service().get_workspace_dir() / "summary_notes"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def session_path(session_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", session_id):
        raise HTTPException(404, "笔记聊天不存在。")
    return directory() / session_id / "session.json"


def read_session(session_id: str):
    try:
        return json.loads(session_path(session_id).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(404, "笔记聊天不存在。") from None
    except (ValueError, OSError):
        raise HTTPException(409, "笔记聊天文件无法读取，请保留文件并从备份恢复。") from None


class GenerateRequest(BaseModel):
    message: str = Field(min_length=1, max_length=40000)
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    confirm_api_cost: bool = False


@router.post('/import')
async def import_material(file: UploadFile = File(...)):
    from deeptutor.services.summary_notes.import_material import extract_material, SUPPORTED
    from pathlib import Path
    try:
        if Path(file.filename or '').suffix.lower() not in SUPPORTED:
            raise HTTPException(415, '支持 PDF（含扫描页及图片文字OCR）、DOCX、PPTX、XLSX、图片、TXT、MD、CSV、SRT、VTT 和常见音视频；旧版 Office 文件请先转换格式。')
        data = await file.read(50 * 1024 * 1024 + 1)
        if len(data) > 50 * 1024 * 1024: raise HTTPException(413, '单个文件不能超过50MB。')
        if not data: raise HTTPException(400, '文件为空。')
        text = await asyncio.to_thread(extract_material, file.filename or '', data)
        return {'name': file.filename, 'text': text, 'characters': len(text)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, '文件无法读取或处理超时，请检查格式、加密状态或拆分文件。') from None
    finally:
        await file.close()


@router.get("")
async def list_sessions():
    sessions = []
    for path in directory().glob("*/session.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sessions.append({key: data[key] for key in ("id", "title", "updated_at")})
        except (ValueError, KeyError, OSError):
            continue
    return {"sessions": sorted(sessions, key=lambda item: item["updated_at"], reverse=True)}


@router.post("")
async def create_session():
    data = {"id": uuid.uuid4().hex, "title": "新建笔记聊天", "updated_at": time.time(), "turns": []}
    atomic_write_json(session_path(data["id"]), data)
    return data


@router.get("/{session_id}")
async def get_session(session_id: str):
    data = read_session(session_id)
    for turn in data["turns"]:
        if turn["status"] == "generating" and not generation_lock.locked():
            turn["status"] = "interrupted"
            turn["error"] = "上次请求已中断。不会自动重试，请先核对已有结果再决定是否重新生成。"
    return data


def build_generation_history(turns: list[dict], message: str) -> list[dict]:
    """Use the latest full revision, not every duplicate historical revision."""
    latest = next(
        (turn for turn in reversed(turns) if turn.get("status") == "complete" and turn.get("notes")),
        None,
    )
    history = []
    if latest:
        history.extend([
            {"role": "user", "content": latest["message"]},
            {"role": "assistant", "content": latest["notes"]},
        ])
    history.append({"role": "user", "content": message})
    if sum(len(item["content"]) for item in history) > 60000:
        raise HTTPException(
            413,
            "本次材料与最近一版笔记合计超过6万字，未发送模型。请新建聊天单独整理本次材料；输入已保留，没有截断或重试。",
        )
    return history


@router.post("/{session_id}/generate")
async def generate(session_id: str, body: GenerateRequest):
    if not body.confirm_api_cost:
        raise HTTPException(400, "请先确认本次会调用已配置模型并产生 API 用量。")
    if not body.message.strip():
        raise HTTPException(400, "请粘贴可读取的材料正文。")
    if generation_lock.locked():
        raise HTTPException(409, "另一条笔记正在生成，请等待完成，不要重复发送。")
    async with generation_lock:
        data = read_session(session_id)
        if any(turn["id"] == body.request_id for turn in data["turns"]):
            return data  # A duplicated HTTP request must never bill a second time.
        history = build_generation_history(data["turns"], body.message.strip())
        turn = {
            "id": body.request_id,
            "message": body.message.strip(),
            "notes": "",
            "html": "",
            "status": "generating",
            "error": "",
            "created_at": time.time(),
        }
        data["turns"].append(turn)
        data["updated_at"] = time.time()
        path = session_path(session_id)
        atomic_write_json(path, data)
        chunks = []
        try:
            from deeptutor.services.llm import (
                clean_thinking_tags,
                get_llm_config,
                get_token_limit_kwargs,
            )
            from deeptutor.services.llm.factory import stream
            from deeptutor.services.llm.types import StreamOutcome

            config = get_llm_config()
            # Match Content Shelf's note-generation request: use the budget for
            # the six-chapter answer instead of consuming it on hidden thinking.
            request_options = {}
            if config.binding == "deepseek" or (
                (config.base_url or "").rstrip("/") in {
                    "https://api.deepseek.com", "https://api.deepseek.com/v1"
                }
            ):
                request_options["extra_body"] = {"thinking": {"type": "disabled"}}
            outcome = StreamOutcome()
            system = (ASSETS / "instructions.md").read_text(encoding="utf-8")
            messages = [{"role": "system", "content": system}, *history]

            async def consume():
                async for chunk in stream(
                    prompt="",
                    system_prompt=system,
                    messages=messages,
                    model=config.model,
                    api_key=config.api_key,
                    base_url=config.base_url,
                    binding=config.binding,
                    api_version=getattr(config, "api_version", None),
                    extra_headers=getattr(config, "extra_headers", None),
                    max_retries=0,
                    outcome=outcome,
                    temperature=0.2,
                    **get_token_limit_kwargs(config.model, 16000),
                    **request_options,
                ):
                    chunks.append(chunk)

            await asyncio.wait_for(consume(), timeout=600)
            raw = clean_thinking_tags("".join(chunks), config.binding, config.model).strip()
            turn["notes"] = raw.replace(COMPLETE, "").strip()
            atomic_write_json(path, data)  # Text survives even if HTML conversion fails.
            turn["finish_reason"] = outcome.finish_reason
            if outcome.finish_reason not in {"stop", "end_turn"}:
                raise ValueError("模型回答被截断或未正常结束，已保留草稿，未当作成功。")
            turn["notes"] = validate_notes(raw, allow_missing_marker=True)
            title, html = render_html(turn["notes"])
            atomic_write_text(path.parent / (turn["id"] + ".md"), turn["notes"])
            atomic_write_text(path.parent / (turn["id"] + ".html"), html)
            turn.update(status="complete", title=title, html=html)
            data["title"] = title
        except (ValueError, asyncio.TimeoutError) as exc:
            turn["notes"] = turn["notes"] or "".join(chunks).replace(COMPLETE, "").strip()
            turn["status"] = "failed"
            turn["error"] = (
                str(exc)
                if isinstance(exc, ValueError)
                else "模型请求超时，已保留收到的草稿；没有自动重试。"
            )
        except Exception as exc:
            turn["notes"] = turn["notes"] or "".join(chunks).replace(COMPLETE, "").strip()
            turn["status"] = "failed"
            # Never expose provider exception text: it can contain credentials or prompts.
            status = getattr(exc, "status_code", None)
            messages = {
                401: "模型服务认证失败（401）：当前 API 密钥无效或已失效。请在设置的模型服务中更新密钥后手动发送；材料已保留，没有自动重试。",
                402: "模型服务余额不足（402）。请检查服务商账户；材料已保留，没有自动重试。",
                403: "模型服务拒绝访问（403）。请检查账户与模型访问权限；材料已保留，没有自动重试。",
                404: "模型或接口不存在（404）。请检查模型名称和服务地址；材料已保留，没有自动重试。",
                429: "模型服务请求受限（429）。请稍后手动发送；材料已保留，没有自动重试。",
            }
            turn["error"] = messages.get(status) or (
                "本地文件保存失败，请检查磁盘空间和目录权限；材料与已收到的文字已保留。"
                if isinstance(exc, OSError)
                else "模型服务或笔记处理失败，材料与已收到的文字已保留，没有自动重试。"
            )
        data["updated_at"] = time.time()
        atomic_write_json(path, data)
        return data


@router.delete('/{session_id}/turns/{turn_id}')
async def delete_turn(session_id: str, turn_id: str):
    if not re.fullmatch(r'[a-f0-9]{32}', turn_id):
        raise HTTPException(404, '笔记不存在。')
    if generation_lock.locked():
        raise HTTPException(409, '笔记正在生成，请完成后再删除。')
    async with generation_lock:
        data = read_session(session_id)
        turn = next((item for item in data['turns'] if item['id'] == turn_id), None)
        if not turn:
            raise HTTPException(404, '笔记不存在。')
        data['turns'] = [item for item in data['turns'] if item['id'] != turn_id]
        latest = next((item for item in reversed(data['turns']) if item['status'] == 'complete'), None)
        data['title'] = latest.get('title', '新建笔记聊天') if latest else '新建笔记聊天'
        data['updated_at'] = time.time()
        path = session_path(session_id)
        atomic_write_json(path, data)
        for suffix in ('.md', '.html'):
            (path.parent / (turn_id + suffix)).unlink(missing_ok=True)
        return data


@router.get("/{session_id}/turns/{turn_id}/download")
async def download(session_id: str, turn_id: str, format: str = "html"):
    if format not in {"html", "md", "enex"}:
        raise HTTPException(400, "只支持 HTML、Markdown 和印象笔记 ENEX。")
    data = read_session(session_id)
    turn = next((item for item in data["turns"] if item["id"] == turn_id), None)
    if not turn or turn["status"] != "complete":
        raise HTTPException(404, "完整文件尚未生成。")
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", turn["title"])[:100] + "读书笔记." + format
    content = export_enex(turn) if format == "enex" else turn["html"] if format == "html" else turn["notes"]
    return Response(
        content=content,
        media_type="application/xml" if format == "enex" else "text/html" if format == "html" else "text/markdown",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
