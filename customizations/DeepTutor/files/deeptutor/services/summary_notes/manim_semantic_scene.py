"""Code-drawn review cards. DeepSeek supplies meaning; this module owns layout."""
import json
import os
from pathlib import Path
import re

import imageio_ffmpeg
os.environ['PATH']=str(Path(imageio_ffmpeg.get_ffmpeg_exe()).parent)+os.pathsep+os.environ.get('PATH','')
from manim import *
from manimpango import list_fonts

if 'Microsoft YaHei' not in list_fonts():
    raise RuntimeError('请安装微软雅黑 Microsoft YaHei 后渲染。')
config.pixel_width=1920
config.pixel_height=1080
config.frame_rate=30
config.frame_width=16
config.frame_height=9
config.background_color='#F6F7FA'
STYLE=json.loads((Path(__file__).resolve().parent/'quick_review_v1/typography.json').read_text(encoding='utf8'))
INK,BLUE,MUTED,PALE,LINE,ORANGE=[STYLE['colors'][name] for name in ('ink','blue','muted','pale','line','orange')]
SIZES=STYLE['sizes']
PLAN=json.loads(Path(os.environ.get('MANIM_REVIEW_PLAN','storyboard.json')).read_text(encoding='utf8'))


def label(value,size=25,color=INK,bold=False,width=14,height=1):
    """Wrap whole English tokens and Chinese characters, then measure real glyphs."""
    if not value:
        return VGroup()
    tokens=re.findall(r'[A-Za-z0-9_./%+≥≤=-]+|[^\n]',value)
    rows=[];row='';used=0
    budget=width*69/size
    for token in tokens:
        cost=sum(.54 if ord(c)<128 else 1 for c in token)
        if row and used+cost>budget:
            rows.append(row);row='';used=0
        row+=token;used+=cost
    if row:rows.append(row)
    obj=Text('\n'.join(rows),font=STYLE['font'],font_size=size,color=color,weight=BOLD if bold else NORMAL,line_spacing=.9)
    scale=min(1,width/max(obj.width,.001),height/max(obj.height,.001))
    if scale<.85:
        raise ValueError('本页文字超出可读排版空间，请将长解释拆成更多场景。')
    if scale<1:obj.scale(scale)
    return obj


def box(x,y,w,h,fill=WHITE,border=LINE):
    return RoundedRectangle(width=w,height=h,corner_radius=.17,fill_color=fill,fill_opacity=1,stroke_color=border,stroke_width=1.4).move_to([x,y,0])


class AutoReview(Scene):
    def construct(self):
        total=len(PLAN['scenes'])
        for index,scene in enumerate(PLAN['scenes']):
            start=self.time
            print(f'MANIM_REVIEW_PROGRESS={index+1}/{total}',flush=True)
            if self.mobjects:self.play(*[FadeOut(o) for o in list(self.mobjects)],run_time=.15)
            title=label(scene['title'],SIZES['title'],bold=True,width=14.2,height=.85).to_edge(LEFT,buff=.7).to_edge(UP,buff=.98)
            sub=label(scene['subtitle'],SIZES['subtitle'],MUTED,width=14.4,height=.65).next_to(title,DOWN,buff=.22).align_to(title,LEFT) if scene.get('subtitle') else None
            self.add(label(f'快复习 / {index+1:02d}',SIZES['corner'],MUTED).to_corner(UL,buff=.7).shift(UP*.14),label('MANIM / 教学版',SIZES['corner'],MUTED).to_corner(UR,buff=.7))
            if scene.get('caption'):
                self.add(box(0,-3.4,14.5,.64,PALE,PALE),label(scene['caption'],SIZES['caption'],BLUE,True,13.9,.48).move_to([0,-3.4,0]))
            if scene.get('note'):
                self.add(label(scene['note'],SIZES['footnote'],MUTED,width=14.2,height=.42).move_to([0,-3.96,0]))
            entrances=[FadeIn(title,shift=UP*.05)]
            if sub is not None:entrances.append(FadeIn(sub))
            self.play(*entrances,run_time=.20)
            if scene['layout']=='recall' and scene.get('question'):
                prompt=label(scene['question'],SIZES['question'],BLUE,True,13.8,1.4)
                self.add(prompt);self.wait(min(1.5,scene['duration']*.18));self.play(FadeOut(prompt),run_time=.2)
            count=len(scene['cards'])
            grid=count>4
            width=4.45 if grid else {2:6.9,3:4.45,4:3.15}[count]
            step=4.9 if grid else {2:7.4,3:4.9,4:3.6}[count]
            objects=[]
            for j,card in enumerate(scene['cards']):
                x=(j%3-1)*step if grid else (j-(count-1)/2)*step
                y=.8-(j//3)*2.2 if grid else -.3
                group=VGroup(box(x,y,width,1.95 if grid else 4.05))
                warning=bool(re.search(r'风险|谨慎|慎选|误区|警告|异常',card['heading']))
                accent=ORANGE if warning else BLUE
                heading_size=SIZES['grid_heading'] if grid else SIZES['four_card_heading'] if count==4 else SIZES['card_heading']
                group.add(label(card['heading'],heading_size,accent,True,width-.4,.55 if grid else .9).move_to([x,y+.59 if grid else 1.13,0]))
                if card.get('highlight'):
                    numeric=bool(re.fullmatch(r'[≥≤<>≈~+\-]?\s*\d[\d.,%％×xX/万千百亿天日件个条倍元$¥￥kgKG小时分钟秒—–\-+ ≥≤<>:→]*',card['highlight']))
                    highlight_size=SIZES['grid_highlight'] if grid else SIZES['numeric_highlight'] if numeric else SIZES['compact_highlight'] if count==4 or len(card['highlight'])>6 else SIZES['text_highlight']
                    highlight_color=ORANGE if warning else MUTED if grid else BLUE if numeric else INK
                    group.add(label(card['highlight'],highlight_size,highlight_color,not grid,width-.4,.55 if grid else 1.15).move_to([x,y+.02 if grid else .1,0]))
                    detail_y=y-.55 if grid else -1.15;detail_h=.65 if grid else 1.3
                else:
                    detail_y=y-.15 if grid else -.35;detail_h=1.1 if grid else 2.5
                if card.get('detail'):
                    detail_color=ORANGE if re.search(r'谨慎|慎选|需核实|未明确|待核实',card['detail']) else MUTED
                    group.add(label(card['detail'],SIZES['four_card_detail'] if count==4 else SIZES['detail'],detail_color,width=width-.4,height=detail_h).move_to([x,detail_y,0]))
                objects.append(group)
            self.play(LaggedStart(*[FadeIn(o,shift=UP*.12) for o in objects],lag_ratio=.2),run_time=min(1.6,.4+count*.25))
            remaining=start+scene['duration']-self.time
            if remaining>0:self.wait(remaining)
