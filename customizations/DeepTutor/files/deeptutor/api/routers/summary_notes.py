"""Simple durable note chats: one model call, then local template export."""

from __future__ import annotations

import asyncio
import json
import re
import time
from urllib.parse import quote
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from deeptutor.services.file_io import atomic_write_json, atomic_write_text
from deeptutor.services.path_service import get_path_service
from deeptutor.services.summary_notes.render import ASSETS, COMPLETE, render_html, validate_notes

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
        history = []
        for turn in data["turns"]:
            history.append({"role": "user", "content": turn["message"]})
            if turn.get("notes") and turn["status"] == "complete":
                history.append({"role": "assistant", "content": turn["notes"]})
        history.append({"role": "user", "content": body.message.strip()})
        if sum(len(item["content"]) for item in history) > 60000:
            raise HTTPException(
                413,
                "本聊天材料过长（累计超过6万字），未发送模型。请新建聊天并分篇整理，不会静默截断。",
            )
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
                    **get_token_limit_kwargs(config.model, 12000),
                ):
                    chunks.append(chunk)

            await asyncio.wait_for(consume(), timeout=300)
            raw = clean_thinking_tags("".join(chunks), config.binding, config.model).strip()
            turn["notes"] = raw.replace(COMPLETE, "").strip()
            atomic_write_json(path, data)  # Text survives even if HTML conversion fails.
            if outcome.finish_reason not in {"stop", "end_turn"}:
                raise ValueError("模型回答被截断或未正常结束，已保留草稿，未当作成功。")
            turn["notes"] = validate_notes(raw)
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
        except Exception:
            turn["status"] = "failed"
            turn["error"] = (
                "模型或保存服务调用失败，没有自动重试。请检查模型连接和可用余额后再手动发送。"
            )
        data["updated_at"] = time.time()
        atomic_write_json(path, data)
        return data


@router.get("/{session_id}/turns/{turn_id}/download")
async def download(session_id: str, turn_id: str, format: str = "html"):
    if format not in {"html", "md"}:
        raise HTTPException(400, "只支持 HTML 和 Markdown。")
    data = read_session(session_id)
    turn = next((item for item in data["turns"] if item["id"] == turn_id), None)
    if not turn or turn["status"] != "complete":
        raise HTTPException(404, "完整文件尚未生成。")
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", turn["title"])[:100] + "读书笔记." + format
    content = turn["html"] if format == "html" else turn["notes"]
    return Response(
        content=content,
        media_type="text/html" if format == "html" else "text/markdown",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
