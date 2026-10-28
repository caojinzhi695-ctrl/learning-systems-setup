"""Versioned reference-video contract. DeepSeek supplies text, never drawing code."""
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from .template_geometry import text_capacity

ASSETS = Path(__file__).with_name('quick_review_v1')
CONTRACT = json.loads((ASSETS / 'slots.json').read_text(encoding='utf8'))


class ExactScene(BaseModel):
    model_config = ConfigDict(extra='forbid')
    layout: str
    duration: float = Field(ge=4, le=14)
    texts: dict[str, str]
    source_quote: str = Field(min_length=1, max_length=180)

    @computed_field
    @property
    def title(self) -> str:
        return self.texts['title']

    @computed_field
    @property
    def caption(self) -> str:
        return self.texts['caption']

    @computed_field
    @property
    def caution(self) -> str:
        return self.texts['note']

class ExactPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    template_id: Literal['manim-quick-review-v1']
    title: str = Field(min_length=1, max_length=40)
    summary: str = Field(min_length=1, max_length=160)
    scenes: list[ExactScene] = Field(min_length=2, max_length=24)

    @model_validator(mode='after')
    def lock_template(self):
        library = {p['layout']: p for p in CONTRACT}
        if sum(s.duration for s in self.scenes) > 240:
            raise ValueError('单条复习视频超过240秒，请拆分主题')
        errors = []
        for index, scene in enumerate(self.scenes):
            page = library.get(scene.layout)
            if not page or scene.texts.keys() != page['slots'].keys():
                raise ValueError('版式或文字槽不符合模板')
            if scene.layout == 'overview' and scene.duration < 6:
                raise ValueError('八项回忆页需要至少6秒完成揭晓与阅读')
            for key, value in scene.texts.items():
                units = sum(.54 if ord(c) < 128 else 1 for c in value)
                capacity = text_capacity(scene.layout, key, page['slots'][key])
                if not value.strip() or '\n' in value or '\r' in value or units > capacity + .01:
                    errors.append(f'第{index+1}页 {scene.layout}.{key}：文字过多，请保留短句（约{capacity:.0f}字容量）')
        if errors:
            raise ValueError('文字槽需精简：' + '；'.join(errors))
        return self


def validate_exact_plan(raw, notes, finish_reason=None):
    from deeptutor.services.llm.types import finish_was_truncated
    if finish_was_truncated(finish_reason):
        raise ValueError('DeepSeek 输出被截断，已停止，草稿保留。')
    try:
        plan = ExactPlan.model_validate(json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())))
    except (ValueError, TypeError) as exc:
        issues = '；'.join(e['msg'] for e in exc.errors()) if hasattr(exc, 'errors') else str(exc)
        raise ValueError(f'DeepSeek 格式未通过模板校验，未渲染。{issues[:3000]}') from None
    normalize = lambda s: re.sub(r'[\s*_`#]', '', s)
    for scene in plan.scenes:
        if normalize(scene.source_quote) not in normalize(notes):
            raise ValueError('分镜引用无法在所选 AI 笔记中找到，已停止。')
    return plan


PROMPT_CONTRACT = json.loads(json.dumps(CONTRACT))
for page in PROMPT_CONTRACT:
    for key, slot in page['slots'].items():
        slot['max_units'] = text_capacity(page['layout'], key, slot)
PROMPT = (ASSETS / 'DEEPSEEK_INSTRUCTIONS.md').read_text(encoding='utf8') + '\n逐页槽说明（按实际卡片宽度计算容量，原文字数不是限制）：\n' + json.dumps(PROMPT_CONTRACT, ensure_ascii=False) + '\n完整输出示例：\n' + (ASSETS / 'example.json').read_text(encoding='utf8')
