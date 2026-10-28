import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from deeptutor.api.routers import summary_videos as api
from deeptutor.services.summary_notes.exact_video_plan import ASSETS, validate_exact_plan as validate_video_plan


def valid_plan():
    plan = json.loads((ASSETS / "example.json").read_text(encoding="utf8"))
    for scene in plan["scenes"]:
        scene["source_quote"] = "先调研再推广"
    return plan


def valid_brief():
    return {"title":"推广复习","core_question":"如何推广？","summary":"先调研，再推广。","points":[{"heading":"调研","takeaway":"先调研再推广","keyphrase":"先调研","screen_text":"先调研再推广","condition":"","source_id":"N0001"},{"heading":"推广","takeaway":"先调研再推广","keyphrase":"再推广","screen_text":"依据调研推广","condition":"","source_id":"N0001"}],"omitted":"合并重复内容"}


def test_rejects_untraceable_or_truncated_plans():
    raw = json.dumps(valid_plan(), ensure_ascii=False)
    assert validate_video_plan(raw, "**先调研再推广**").scenes
    with pytest.raises(ValueError, match="引用"):
        validate_video_plan(raw, "另一篇笔记")
    with pytest.raises(ValueError, match="截断"):
        validate_video_plan(raw, "先调研再推广", "length")


def test_rejects_code_and_invalid_diagram_structure():
    plan = valid_plan()
    plan["scenes"][0]["script"] = "fetch('secret')"
    with pytest.raises(ValueError, match="格式"):
        validate_video_plan(json.dumps(plan), "先调研再推广")


def test_template_allows_variable_length_and_repeated_layouts_but_locks_style():
    plan = valid_plan()
    plan['scenes'] = [plan['scenes'][2], plan['scenes'][2].copy()]
    plan['scenes'][0]['duration'] = 5
    plan['scenes'][1]['duration'] = 8
    result = validate_video_plan(json.dumps(plan), '先调研再推广')
    assert sum(s.duration for s in result.scenes) == 13
    plan['scenes'][0]['texts']['font'] = 'Arial'
    with pytest.raises(ValueError, match='格式'):
        validate_video_plan(json.dumps(plan), '先调研再推广')


def test_template_rejects_missing_slots_overflow_and_unreadable_recall():
    import copy
    for mutate in (
        lambda p: p['scenes'][0]['texts'].pop('body_01'),
        lambda p: p['scenes'][0]['texts'].update(body_01='长' * 100),
        lambda p: p['scenes'][-1].update(duration=4),
    ):
        plan = copy.deepcopy(valid_plan())
        mutate(plan)
        with pytest.raises(ValueError, match='格式'):
            validate_video_plan(json.dumps(plan), '先调研再推广')


def test_real_card_capacity_accepts_island_draft_previously_rejected_by_example_length():
    plan = valid_plan()
    plan['scenes'][3]['texts'].update(body_02='增维护资本',body_03='储蓄的鱼是投资物品')
    plan['scenes'][4]['texts']['body_02']='时间被消耗'
    plan['scenes'][7]['texts']['body_15']='提高效率或支配资源'
    result = validate_video_plan(json.dumps(plan), '先调研再推广')
    assert result.scenes[3].texts['body_02'] == '增维护资本'
    assert result.scenes[7].texts['body_15'] == '提高效率或支配资源'


def test_brief_evidence_is_resolved_from_original_passages_and_unknown_ids_rejected():
    from deeptutor.services.summary_notes.video_brief import source_units, validate_brief, resolve_storyboard_sources
    notes = '先调研再推广\n\n' + '长段原文。' * 70
    units = source_units(notes)
    assert all(len(v) <= 180 and v in notes for v in units.values())
    brief = validate_brief(json.dumps(valid_brief()), notes)
    assert brief.points[0].source_quote == '先调研再推广'
    plan = valid_plan()
    for scene in plan['scenes']:
        scene.pop('source_quote')
        scene['source_id']='N0001'
    resolved=resolve_storyboard_sources(json.dumps(plan),brief)
    assert validate_video_plan(resolved,notes).scenes[0].source_quote == '先调研再推广'
    plan['scenes'][0]['source_id']='N9999'
    with pytest.raises(ValueError,match='编号'):
        resolve_storyboard_sources(json.dumps(plan),brief)


@pytest.mark.asyncio
async def test_bad_brief_stops_before_storyboard_call_and_saves_draft(store, monkeypatch):
    from deeptutor.services.llm import factory
    calls=[]
    async def stream(**kwargs):
        calls.append(kwargs)
        kwargs['outcome'].finish_reason='stop'
        brief=valid_brief();brief['points'][0]['source_id']='N9999'
        yield json.dumps(brief)
    monkeypatch.setattr(factory,'stream',stream)
    sid,tid,jid=store
    await api.create_plan(sid,tid,api.PlanRequest(request_id=jid,confirm_api_cost=True))
    await api.jobs[(sid,tid,jid)]
    data=api.load(sid,tid,jid)
    assert len(calls)==1 and data['status']=='failed' and data['brief_draft']
    assert 'brief_draft' not in api.public(data)


@pytest.mark.asyncio
async def test_continue_reuses_brief_without_resending_full_note(store, monkeypatch):
    from deeptutor.services.llm import factory
    from deeptutor.services.file_io import atomic_write_json
    from deeptutor.services.summary_notes.video_brief import validate_brief,brief_cache_key
    sid,tid,jid=store
    brief=validate_brief(json.dumps(valid_brief()),'先调研再推广')
    data={'id':jid,'session_id':sid,'turn_id':tid,'note_title':'笔记','instructions':'','renderer':'manim','status':'failed','plan':None,'review_brief':brief.model_dump(),'brief_input_hash':brief_cache_key('先调研再推广','')}
    atomic_write_json(api.job_path(sid,tid,jid),data)
    calls=[]
    async def stream(**kwargs):
        calls.append(kwargs)
        assert 'note_passages' not in json.loads(kwargs['messages'][1]['content'])
        kwargs['outcome'].finish_reason='stop'
        yield json.dumps(valid_plan())
    monkeypatch.setattr(factory,'stream',stream)
    await api.continue_from_brief(sid,tid,jid)
    await api.jobs[(sid,tid,jid)]
    assert len(calls)==1 and api.load(sid,tid,jid)['status']=='complete'
    data['brief_input_hash']='stale'
    atomic_write_json(api.job_path(sid,tid,jid),data)
    with pytest.raises(HTTPException) as error:
        await api.continue_from_brief(sid,tid,jid)
    assert error.value.status_code == 409
    plan = valid_plan()
    plan["scenes"][0]["layout"] = "matrix"
    with pytest.raises(ValueError, match="格式"):
        validate_video_plan(json.dumps(plan), "先调研再推广")


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "get_path_service", lambda: SimpleNamespace(get_workspace_dir=lambda: tmp_path))
    from deeptutor.api.routers import summary_exams
    monkeypatch.setattr(summary_exams, "turn_for", lambda *_: ({}, {"status": "complete", "title": "AI笔记", "notes": "先调研再推广"}))
    from deeptutor.services import llm
    config = SimpleNamespace(model="deepseek-test", binding="deepseek", api_key="private-test-key", base_url="https://example.invalid", api_version=None, extra_headers=None)
    monkeypatch.setattr(llm, "get_llm_config", lambda: config)
    monkeypatch.setattr(llm, "get_token_limit_kwargs", lambda *_: {})
    from deeptutor.services.summary_notes import manim_render
    monkeypatch.setattr(manim_render, "manim_python", lambda: tmp_path / "python.exe")
    async def render(plan, output, progress):
        output.mkdir(parents=True, exist_ok=True)
        (output / "video.mp4").write_bytes(b"test-video" * 200)
        progress(len(plan["scenes"]), len(plan["scenes"]))
    monkeypatch.setattr(manim_render, "render_manim", render)
    return "a" * 32, "b" * 32, "c" * 32


@pytest.mark.asyncio
async def test_idempotency_and_cancel_before_worker_starts(store, monkeypatch):
    calls = []
    async def worker(*args):
        calls.append(args)
        await asyncio.sleep(30)
    monkeypatch.setattr(api, "run_plan", worker)
    sid, tid, jid = store
    request = api.PlanRequest(request_id=jid, confirm_api_cost=True)
    await api.create_plan(sid, tid, request)
    await api.create_plan(sid, tid, request)
    assert len(api.jobs) == 1
    cancelled = await api.cancel_plan(sid, tid, jid)
    assert cancelled["status"] == "cancelled"
    assert not api.jobs
    assert len(calls) <= 1


@pytest.mark.asyncio
async def test_uses_configured_deepseek_and_ai_notes_without_exposing_key(store, monkeypatch):
    from deeptutor.services.llm import factory
    calls = []
    async def stream(**kwargs):
        calls.append(kwargs)
        kwargs["outcome"].finish_reason = "stop"
        yield json.dumps(valid_brief() if len(calls) == 1 else valid_plan(), ensure_ascii=False)
    monkeypatch.setattr(factory, "stream", stream)
    sid, tid, jid = store
    response = await api.create_plan(sid, tid, api.PlanRequest(request_id=jid, confirm_api_cost=True))
    await api.jobs[(sid, tid, jid)]
    value = await api.get_plan(sid, tid, jid)
    assert value["status"] == "complete"
    assert value["model"] == "deepseek-test"
    assert value["renderer"] == "manim" and value["video"]
    assert calls[0]["api_key"] == "private-test-key"
    assert calls[0]["max_retries"] == 0
    assert all(c['response_format']=={'type':'json_object'} for c in calls)
    assert all(c['binding']=='deepseek' and c['model']=='deepseek-test' for c in calls)
    assert json.loads(calls[0]["messages"][1]["content"])["note_passages"] == {"N0001": "先调研再推广"}
    assert len(calls) == 2
    second = json.loads(calls[1]["messages"][1]["content"])
    assert "notes" not in second and "review_brief" in second
    assert value["review_brief"]["points"]
    assert "private-test-key" not in json.dumps(value)
    assert "draft" not in value
    assert value['compute']=={'ai':'DeepSeek API','render':'local-manim'}
    assert response["status"] == "queued"


@pytest.mark.asyncio
async def test_rerender_does_not_call_model_and_media_is_server_persisted(store, monkeypatch):
    sid, tid, jid = store
    from deeptutor.services.file_io import atomic_write_json
    data = {"id": jid, "session_id": sid, "turn_id": tid, "renderer": "manim", "status": "failed", "plan": valid_plan(), "error": "render interrupted"}
    atomic_write_json(api.job_path(sid, tid, jid), data)
    result = await api.rerender(sid, tid, jid)
    await api.jobs[(sid, tid, jid)]
    assert result["status"] == "rendering"
    assert (await api.get_plan(sid, tid, jid))["video"]
    response = await api.video_file(sid, tid, jid)
    assert response.media_type == "video/mp4"
    assert "attachment" in response.headers["content-disposition"]


@pytest.mark.asyncio
@pytest.mark.parametrize('repair_succeeds', [True, False])
async def test_one_bounded_format_repair_and_no_draft_leak(store, monkeypatch, repair_succeeds):
    from deeptutor.services.llm import factory
    calls = []
    async def stream(**kwargs):
        calls.append(len(kwargs['messages']))
        kwargs['outcome'].finish_reason = 'stop'
        yield json.dumps(valid_brief()) if len(calls) == 1 else json.dumps(valid_plan()) if repair_succeeds and len(calls) == 3 else '{}'
    monkeypatch.setattr(factory, 'stream', stream)
    sid, tid, jid = store
    await api.create_plan(sid, tid, api.PlanRequest(request_id=jid, confirm_api_cost=True))
    await api.jobs[(sid, tid, jid)]
    result = await api.get_plan(sid, tid, jid)
    assert calls == [2, 2, 4]
    assert result['repair_count'] == 1
    assert result['status'] == ('complete' if repair_succeeds else 'failed')
    assert 'first_draft' not in result and 'draft' not in result


@pytest.mark.asyncio
async def test_missing_renderer_fails_before_paid_model_request(store, monkeypatch):
    from deeptutor.services.summary_notes import manim_render
    monkeypatch.setattr(manim_render, "manim_python", lambda: (_ for _ in ()).throw(ValueError("Manim 未安装")))
    sid, tid, jid = store
    with pytest.raises(HTTPException) as error:
        await api.create_plan(sid, tid, api.PlanRequest(request_id=jid, confirm_api_cost=True))
    assert error.value.status_code == 422
    assert not api.job_path(sid, tid, jid).exists()


@pytest.mark.asyncio
async def test_source_download_contains_portable_template_and_reference_assets(store):
    import zipfile
    from deeptutor.services.file_io import atomic_write_json
    sid, tid, jid = store
    atomic_write_json(api.job_path(sid, tid, jid), {'id':jid,'session_id':sid,'turn_id':tid,'renderer':'manim','plan':valid_plan()})
    response = await api.source_file(sid, tid, jid)
    with zipfile.ZipFile(response.path) as archive:
        assert {'manim_scene.py','storyboard.json','quick_review_v1/render.py','quick_review_v1/slots.json','quick_review_v1/reference_story.json','quick_review_v1/typography.json','quick_review_v1/DEEPSEEK_INSTRUCTIONS.md'} <= set(archive.namelist())
        assert ('quick_review_v1/reference-music.m4a' in archive.namelist()) == (ASSETS/'reference-music.m4a').is_file()


def test_path_and_restart_safety(store):
    sid, tid, jid = store
    with pytest.raises(HTTPException):
        api.job_path(sid, tid, "../secret")
    data = {"id": jid, "session_id": sid, "turn_id": tid, "status": "planning", "draft": "private draft"}
    assert api.public(data)["status"] == "interrupted"
    assert "draft" not in api.public(data)


@pytest.mark.asyncio
async def test_cancel_terminates_manim_and_does_not_forward_model_secrets(monkeypatch, tmp_path):
    from deeptutor.services.summary_notes import manim_render
    monkeypatch.setattr(manim_render, "get_path_service", lambda: SimpleNamespace(project_root=tmp_path))
    monkeypatch.setattr(manim_render, "manim_python", lambda: tmp_path / "python.exe")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "private-render-test")
    started = asyncio.Event()
    class Process:
        returncode = None
        def __init__(self):
            self.stdout = self
        async def readline(self):
            await asyncio.sleep(30)
        def terminate(self):
            self.returncode = -15
        async def wait(self):
            return self.returncode
    process = Process()
    async def spawn(*args, **kwargs):
        assert "DEEPSEEK_API_KEY" not in kwargs["env"]
        media = args[args.index("--media_dir") + 1]
        assert str(tmp_path / "tools/manim/render") in media
        started.set()
        return process
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    task = asyncio.create_task(manim_render.render_manim(valid_plan(), tmp_path / "deep/note/path", lambda *_: None))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.returncode == -15
    assert not list((tmp_path / "tools/manim/render").glob("mv-*"))
