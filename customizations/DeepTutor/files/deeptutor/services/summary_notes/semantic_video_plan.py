"""Semantic storyboard contract: model content is independent of drawing slots."""
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class ReviewCard(BaseModel):
    model_config = ConfigDict(extra='forbid')
    heading: str = Field(min_length=1, max_length=24)
    highlight: str = Field(default='', max_length=32)
    detail: str = Field(default='', max_length=80)


class ReviewScene(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=50)
    subtitle: str = Field(default='', max_length=100)
    layout: Literal['cards','compare','recall'] = 'cards'
    duration: float = Field(ge=4, le=18)
    cards: list[ReviewCard] = Field(min_length=2, max_length=6)
    caption: str = Field(default='', max_length=100)
    note: str = Field(default='', max_length=120)
    question: str = Field(default='', max_length=60)
    source_quote: str = Field(min_length=1, max_length=180)

    @computed_field
    @property
    def caution(self) -> str:
        return self.note


class SemanticPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    template_id: Literal['manim-review-v2'] = 'manim-review-v2'
    title: str = Field(min_length=1,max_length=60)
    summary: str = Field(min_length=1,max_length=260)
    scenes: list[ReviewScene] = Field(min_length=2,max_length=24)

    @model_validator(mode='after')
    def total_duration(self):
        if sum(s.duration for s in self.scenes)>240:
            raise ValueError('复习视频超过240秒，请拆分主题。')
        return self


def validate_semantic_plan(raw, notes, finish_reason=None):
    from deeptutor.services.llm.types import finish_was_truncated
    if finish_was_truncated(finish_reason):
        raise ValueError('分镜输出被截断，草稿已保留。')
    try:
        plan=SemanticPlan.model_validate_json(re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip()))
    except ValueError as exc:
        issues='；'.join('.'.join(map(str,e['loc']))+': '+e['msg'] for e in exc.errors()) if hasattr(exc,'errors') else str(exc)
        raise ValueError('分镜结构需修正：'+issues[:2500]) from None
    normalize=lambda s:re.sub(r'[\s*_`#]','',s)
    for scene in plan.scenes:
        if normalize(scene.source_quote) not in normalize(notes):
            raise ValueError('分镜引用不在原笔记中，已停止。')
    return plan


def validate_storyboard(raw, notes, finish_reason=None):
    """Keep old saved plans usable while new generations use semantic cards."""
    try:
        data=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip()))
    except ValueError:
        return validate_semantic_plan(raw,notes,finish_reason)
    if isinstance(data,dict) and data.get('template_id')=='manim-quick-review-v1':
        from .exact_video_plan import validate_exact_plan
        # A footer was optional in meaning but used to be mandatory in the wire
        # format. Reuse the model's own caption; never invent knowledge.
        optional_footer={'competition':'body_07','profit':'body_10','reputation':'body_10','logistics':'body_08'}
        for scene in data.get('scenes',[]):
            if isinstance(scene,dict) and isinstance(scene.get('texts'),dict):
                key=optional_footer.get(scene.get('layout'))
                if key and key not in scene['texts']:
                    scene['texts'][key]=scene['texts'].get('caption') or scene['texts'].get('title','')
        return validate_exact_plan(json.dumps(data,ensure_ascii=False),notes,finish_reason)
    return validate_semantic_plan(raw,notes,finish_reason)


STORYBOARD_PROMPT='''你是复习视频的教学编辑。只返回JSON，所有智能分析只使用当前DeepSeek模型。
输入review_brief是已整理的精简笔记。根据重点和学习顺序组织场景，不再处理整篇原文，不扩写知识。
你负责标题、要点、关系、自然短句与阅读节奏。程序负责微软雅黑、配色、位置、卡片尺寸、自动换行和Manim渲染。
每页包含2—6张cards。每卡heading是概念或步骤，highlight是可选短结论/数字，detail是简短解释。不要写body_01等内部槽、字体、坐标、Python或HTML。
可选内容可以省略，不为填满卡片而编造。不要把同一知识在标题、highlight、detail重复三遍。
layout选择cards（分类/步骤）、compare（对比）、recall（主动回忆）。recall先question再揭晓2—6个答案，不强凑8项。
保留有编号的完整步骤：例如“五步拆解”应包含5步，不得漏最后一步。可用5张卡或拆页，标题声称的数量与展示内容一致。
卡片heading建议8字以内，highlight建议6字以内，detail建议24字以内；数字必须保留单位与条件。文案较多时增加场景，不用生硬缩略词。
每页duration由你判断4—18秒：简单页4—6秒，关系和多条件页7—10秒，密集页10—14秒。复习用途节奏紧凑，入场后要有阅读时间。总时长<=240秒，不固定页数或50秒。
subtitle/caption/note/question均可省略。caption是本页记忆线索；note保留来源中的重要适用条件。source_id从review_brief.points选取，由程序取回原文。
只返回如下结构，未展示的可选字段可省略：
{"template_id":"manim-review-v2","title":"复习标题","summary":"覆盖范围及节奏理由","scenes":[{"title":"先调研，再推广","layout":"cards","duration":6,"cards":[{"heading":"调研","highlight":"找机会","detail":"按资料归纳需求与竞争"},{"heading":"推广","highlight":"验证","detail":"按资料归纳推广动作"}],"caption":"先明确需求，再做推广","source_id":"N0001"}]}
至少2页；上例仅演示结构，不复制示例知识。'''
