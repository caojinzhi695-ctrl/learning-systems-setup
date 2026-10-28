import json
import pytest

from deeptutor.services.summary_notes.semantic_video_plan import validate_storyboard, validate_semantic_plan
from deeptutor.services.summary_notes.video_brief import validate_brief, resolve_storyboard_sources


def semantic_example():
    return {'title':'推广复习','summary':'先调研再推广','scenes':[
        {'title':'先调研','duration':6,'cards':[{'heading':'需求','detail':'理解需求'},{'heading':'竞争','highlight':'找机会'}],'source_quote':'先调研再推广'},
        {'title':'再推广','layout':'recall','duration':7,'question':'先做什么？','cards':[{'heading':'调研'},{'heading':'推广'}],'source_quote':'先调研再推广'}
    ]}


def test_semantic_optional_content_and_card_counts_do_not_require_internal_slots():
    result=validate_semantic_plan(json.dumps(semantic_example()),'先调研再推广')
    assert result.template_id=='manim-review-v2'
    assert result.scenes[0].caption=='' and result.scenes[0].cards[1].detail==''
    assert len(result.scenes[1].cards)==2
    assert 'texts' not in result.model_dump()['scenes'][0]


def test_legacy_missing_optional_footer_reuses_its_own_caption():
    from deeptutor.services.summary_notes.exact_video_plan import ASSETS
    plan=json.loads((ASSETS/'example.json').read_text(encoding='utf8'))
    for scene in plan['scenes']:scene['source_quote']='先调研再推广'
    page=plan['scenes'][2]
    del page['texts']['body_07']
    result=validate_storyboard(json.dumps(plan),'先调研再推广')
    assert result.scenes[2].texts['body_07']==page['texts']['caption']


@pytest.mark.parametrize('mutation',[
    lambda p:p['scenes'][0].update(script="import os"),
    lambda p:p['scenes'][0]['cards'][0].update(font='Other Font'),
    lambda p:p['scenes'][0].update(cards=[]),
    lambda p:p['scenes'][0].update(duration=500),
])
def test_semantic_rejects_code_style_and_invalid_payloads(mutation):
    plan=semantic_example();mutation(plan)
    with pytest.raises(ValueError):validate_semantic_plan(json.dumps(plan),'先调研再推广')


def test_semantic_preserves_evidence_and_rejects_untraceable_claim_source():
    plan=semantic_example()
    plan['scenes'][0]['source_quote']='另一篇笔记'
    with pytest.raises(ValueError,match='引用'):validate_semantic_plan(json.dumps(plan),'先调研再推广')


def test_five_step_note_does_not_have_to_omit_a_step_to_fit_four_cards():
    plan=semantic_example()
    plan['scenes'][0].update(title='五步拆解',cards=[{'heading':f'第{i}步'} for i in range(1,6)])
    result=validate_semantic_plan(json.dumps(plan),'先调研再推广')
    assert len(result.scenes[0].cards)==5
