"""Review exams for summary note turns. API credentials stay in runtime settings."""
import asyncio
import json
import re
import time
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from deeptutor.services.file_io import atomic_write_json
from deeptutor.services.summary_notes.exams import validate_paper, export_word, export_html
from deeptutor.services.summary_notes.render import ASSETS

router = APIRouter()
tasks = set()


class ExamRequest(BaseModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')


def turn_for(session_id, turn_id):
    from .summary_notes import read_session
    data = read_session(session_id)
    turn = next((t for t in data['turns'] if t['id'] == turn_id), None)
    if not turn or turn['status'] != 'complete':
        raise HTTPException(404, '请先生成完整 AI 笔记。')
    return data, turn


@router.get('/{session_id}/turns/{turn_id}/exams')
async def list_exams(session_id: str, turn_id: str):
    _, turn = turn_for(session_id, turn_id)
    exams = sorted(turn.get('exams', []), key=lambda e: e['created_at'], reverse=True)
    for e in exams:
        if e['status'] == 'generating' and e['id'] not in tasks:
            e.update(status='failed', error='生成已中断，草稿保留，请手动重试。')
    return {'exams': [{k: v for k, v in e.items() if k != 'draft'} for e in exams]}


async def run_exam(session_id, turn_id, request_id):
    from .summary_notes import generation_lock, session_path
    try:
        async with generation_lock:
            data, turn = turn_for(session_id, turn_id)
            exam = next(e for e in turn['exams'] if e['id'] == request_id)
            chunks = []
            try:
                from deeptutor.services.llm import get_llm_config, get_token_limit_kwargs, clean_thinking_tags
                from deeptutor.services.llm.factory import stream
                from deeptutor.services.llm.types import StreamOutcome
                config = get_llm_config()
                system = (ASSETS / 'exam-instructions.md').read_text(encoding='utf-8')
                messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': json.dumps({'title': turn.get('title', '学习笔记'), 'material': turn['notes'], 'sourceType': 'ai-note', 'requestedCount': None}, ensure_ascii=False)}]
                options = {}
                if config.binding == 'deepseek' or (config.base_url or '').rstrip('/') in {'https://api.deepseek.com', 'https://api.deepseek.com/v1'}:
                    options['extra_body'] = {'thinking': {'type': 'disabled'}}
                outcome = StreamOutcome()

                async def consume():
                    async for chunk in stream(prompt='', system_prompt=system, messages=messages, model=config.model, api_key=config.api_key, base_url=config.base_url, binding=config.binding, api_version=getattr(config, 'api_version', None), extra_headers=getattr(config, 'extra_headers', None), max_retries=0, outcome=outcome, temperature=0.2, **get_token_limit_kwargs(config.model, 16000), **options):
                        chunks.append(chunk)
                await asyncio.wait_for(consume(), 600)
                raw = clean_thinking_tags(''.join(chunks), config.binding, config.model).strip()
                raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw)
                exam['draft'] = raw
                exam['paper'] = validate_paper(raw, outcome.finish_reason)
                exam['status'] = 'complete'
            except ValueError as exc:
                exam.update(status='failed', error=str(exc))
            except Exception:
                exam.update(status='failed', error='模型连接、余额或服务异常，请检查设置后手动重试。已有内容已保留。')
            finally:
                exam['draft'] = exam.get('draft') or ''.join(chunks)
                data['updated_at'] = time.time()
                atomic_write_json(session_path(session_id), data)
    finally:
        tasks.discard(request_id)


@router.post('/{session_id}/turns/{turn_id}/exams', status_code=202)
async def generate_exam(session_id: str, turn_id: str, body: ExamRequest):
    from .summary_notes import generation_lock, session_path
    data, turn = turn_for(session_id, turn_id)
    old = next((e for e in turn.get('exams', []) if e['id'] == body.request_id), None)
    if old:
        return {'id': old['id']}
    if generation_lock.locked() or tasks:
        raise HTTPException(409, '另一项笔记或试卷正在生成，请稍后再试。')
    if not turn.get('notes', '').strip() or len(turn['notes']) > 40000:
        raise HTTPException(400, '笔记为空或超过4万字，请分篇整理。')
    async with generation_lock:
        turn.setdefault('exams', []).append({'id': body.request_id, 'created_at': time.time(), 'status': 'generating', 'error': '', 'paper': None})
        atomic_write_json(session_path(session_id), data)
        tasks.add(body.request_id)
        task = asyncio.create_task(run_exam(session_id, turn_id, body.request_id))
        background.add(task)
        task.add_done_callback(background.discard)
    return {'id': body.request_id}


background = set()


@router.get('/{session_id}/turns/{turn_id}/exams/{exam_id}/word')
async def download_word(session_id: str, turn_id: str, exam_id: str):
    _, turn = turn_for(session_id, turn_id)
    exam = next((e for e in turn.get('exams', []) if e['id'] == exam_id), None)
    if not exam or not exam.get('paper'):
        raise HTTPException(404, '试卷尚未生成完整。')
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', exam['paper']['title'])[:100] + '-复习练习卷.docx'
    return Response(export_word(exam['paper']), media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document', headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename), 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.get('/{session_id}/turns/{turn_id}/exams/{exam_id}/html')
async def download_html(session_id: str, turn_id: str, exam_id: str):
    _, turn = turn_for(session_id, turn_id)
    exam = next((e for e in turn.get('exams', []) if e['id'] == exam_id), None)
    if not exam or exam.get('status') != 'complete' or not exam.get('paper'):
        raise HTTPException(404, '试卷尚未生成完整。')
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', exam['paper']['title'])[:100] + '-复习练习卷.html'
    return Response(export_html(exam['paper'], 'deeptutor-exam-' + exam_id), media_type='text/html', headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename), 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
