"""Trusted Manim scene renderer. Reads data, never executes model-written code."""
import json
import os
from pathlib import Path

import imageio_ffmpeg

os.environ["PATH"] = str(Path(imageio_ffmpeg.get_ffmpeg_exe()).parent) + os.pathsep + os.environ.get("PATH", "")
from manim import *  # noqa: E402,F403

config.pixel_width = 1920
config.pixel_height = 1080
config.frame_rate = 30
config.frame_width = 16
config.frame_height = 9
config.background_color = "#F6F7FA"
INK, BLUE, MUTED, LINE, ORANGE = "#253B52", "#3466E8", "#7E8DA2", "#DFE7F3", "#C88648"
PALE, WARM, GREEN = "#EDF3FF", "#FFF3E3", "#EAF5EF"


def wrap_words(value, width, size):
    # Keep English tokens together; Chinese text can break between characters.
    import re
    tokens = re.findall(r"[A-Za-z0-9≥≤%./+×＝=<>_-]+|[^\n]", value)
    limit = max(5, width / (size / 48 * .54))
    rows, row, used = [], "", 0
    for token in tokens:
        weight = sum(.54 if ord(c) < 128 else 1 for c in token)
        if row and used + weight > limit:
            rows.append(row.strip())
            row, used = "", 0
        row += token
        used += weight
    if row:
        rows.append(row.strip())
    return "\n".join(rows)


def tx(value, size=25, color=INK, width=None, height=None, bold=False):
    value = wrap_words(value, width, size) if width else value
    obj = Text(value or " ", font="Microsoft YaHei", font_size=size, color=color, weight=BOLD if bold else NORMAL, line_spacing=.9)
    if width and obj.width > width:
        obj.scale_to_fit_width(width)
    if height and obj.height > height:
        obj.scale_to_fit_height(height)
    return obj


def box(w, h, fill=WHITE, stroke=LINE):
    return RoundedRectangle(width=w, height=h, corner_radius=.16, fill_color=fill, fill_opacity=1, stroke_color=stroke, stroke_width=1.5)


def icon(kind, size=.8):
    if kind in {"box", "truck"}:
        obj = VGroup(Polygon([-.5,-.35,0],[.3,-.35,0],[.3,.3,0],[-.5,.3,0],fill_color="#FFE1BB",fill_opacity=1,stroke_color="#C99963"), Polygon([-.5,.3,0],[-.22,.55,0],[.58,.55,0],[.3,.3,0],fill_color="#FFF0D6",fill_opacity=1,stroke_color="#C99963"), Polygon([.3,-.35,0],[.58,-.1,0],[.58,.55,0],[.3,.3,0],fill_color="#F2D1A6",fill_opacity=1,stroke_color="#C99963"))
    elif kind == "search":
        obj = VGroup(Circle(radius=.34,color=BLUE,fill_color=PALE,fill_opacity=1), Line([.22,-.23,0],[.58,-.58,0],color=BLUE,stroke_width=5))
    elif kind == "shield":
        obj = VGroup(Polygon([0,.5,0],[.43,.3,0],[.32,-.2,0],[0,-.5,0],[-.32,-.2,0],[-.43,.3,0],color=BLUE,fill_color=PALE,fill_opacity=1), VMobject(color=BLUE,stroke_width=4).set_points_as_corners([[-.2,0,0],[-.02,-.17,0],[.23,.2,0]]))
    elif kind == "coins":
        obj = VGroup(*[Circle(radius=.28,fill_color="#FFE9BB",fill_opacity=1,color=ORANGE).shift(RIGHT*i*.25+UP*i*.13) for i in range(3)])
    elif kind == "target":
        obj = VGroup(*[Circle(radius=r,color=BLUE,stroke_width=2) for r in [.47,.3,.1]])
    elif kind == "megaphone":
        obj = VGroup(Polygon([-.5,.12,0],[.35,.48,0],[.35,-.4,0],[-.5,-.12,0],color=BLUE,fill_color=PALE,fill_opacity=1),Line([-.2,-.22,0],[-.05,-.6,0],color=BLUE))
    elif kind == "store":
        obj = VGroup(box(.9,.65,PALE),box(1,.24,BLUE,BLUE).shift(UP*.35),box(.25,.38,WHITE).shift(RIGHT*.2+DOWN*.14))
    elif kind == "tag":
        obj = VGroup(Polygon([-.5,.35,0],[.25,.35,0],[.5,0,0],[.25,-.35,0],[-.5,-.35,0],color=BLUE,fill_color=PALE,fill_opacity=1),Circle(radius=.07,color=BLUE).shift(RIGHT*.24))
    else:
        obj = VGroup(*[Rectangle(width=.2,height=h,fill_color=BLUE,fill_opacity=1,stroke_width=0).move_to([-.32+i*.32,-.45+h/2,0]) for i,h in enumerate([.35,.6,.95])])
    obj.scale_to_fit_width(size)
    return obj


def tile(item, x, y, w, h, fill=WHITE, number=None, large_icon=False):
    bg = box(w,h,fill).move_to([x,y,0])
    label = tx((f"{number:02d}  " if number else "")+item["label"],24,BLUE,w-.4,.55,True).move_to([x,y+h/2-.48,0])
    rows = [label]
    if item.get("value"):
        value = tx(item["value"],30,BLUE,w-.44,1.0,True).next_to(label,DOWN,buff=.32)
        rows.append(value)
    detail = tx(item.get("detail", ""),20,INK,w-.5, min(1.2,h*.34)).next_to(rows[-1],DOWN,buff=.3)
    rows.append(detail)
    content = VGroup(*rows)
    available = h-(1.5 if large_icon else .55)
    if content.height>available:
        content.scale(available/content.height)
    content.move_to([x,y+h/2-.28-content.height/2,0])
    group = VGroup(bg,*rows)
    if item.get("icon", "none") != "none":
        if large_icon:
            art = icon(item["icon"],.8).move_to([x,y-h/2+.67,0])
        else:
            art = icon(item["icon"],.37).move_to([x+w/2-.32,y+h/2-.32,0])
            label.scale_to_fit_width(min(label.width,w-.95)).shift(LEFT*.18)
        group.add(art)
    return group


class AutoReview(Scene):
    def construct(self):
        plan_path = Path(os.environ.get("MANIM_REVIEW_PLAN", str(Path(__file__).with_name("storyboard.json"))))
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        total = len(plan["scenes"])
        for i, scene in enumerate(plan["scenes"]):
            start = self.time
            if self.mobjects:
                self.play(*[FadeOut(m) for m in list(self.mobjects)],run_time=.15)
            header = tx(scene["title"],37,INK,14.4,.65,True).to_edge(LEFT,buff=.7).to_edge(UP,buff=.92)
            subtitle = tx(scene.get("subtitle", ""),21,MUTED,14.4,.45).next_to(header,DOWN,buff=.2).align_to(header,LEFT)
            self.add(tx("DEEPTUTOR  /  MANIM 快复习",14,MUTED).to_corner(UL,buff=.65),tx(f"{i+1:02d} / {total:02d}",14,MUTED).to_corner(UR,buff=.65))
            caption = VGroup(box(14.5,.64,PALE,PALE).move_to([0,-3.42,0]),tx(scene["caption"],21,BLUE,13.9,.43,True).move_to([0,-3.42,0]))
            note = tx(scene.get("caution") or "依据所选 AI 笔记编排 · 条件与口径请结合原文复核",14,ORANGE if scene.get("caution") else MUTED,14.3,.38).move_to([0,-3.99,0])
            self.add(caption,note)
            self.play(FadeIn(header,shift=UP*.06),FadeIn(subtitle),run_time=.22)
            items, kind = scene["items"], scene["layout"]
            n, cards, arrows = len(items), [], []
            if kind == "recall":
                question = tx(scene.get("question") or "先回忆：这次复习的关键框架是什么？",32,BLUE,13,1.5,True).move_to([0,.1,0])
                self.play(FadeIn(question),run_time=.15)
                self.wait(1.1)
                self.play(FadeOut(question),run_time=.15)
            if kind in {"flow","inventory"}:
                gap=.35; w=(14.5-(n-1)*gap)/n
                for j,item in enumerate(items):
                    x=-7.25+w/2+j*(w+gap)
                    cards.append(tile(item,x,-.15,w,4.15,number=j+1,large_icon=True))
                    if j<n-1:
                        arrows.append(Arrow([x+w/2+.035,-.15,0],[x+w/2+gap-.035,-.15,0],buff=0,color=BLUE,stroke_width=3,max_tip_length_to_length_ratio=.25))
                if kind=="inventory":
                    self.play(Create(Line([-7.2,-2.5,0],[7.2,-2.5,0],color=LINE)),run_time=.2)
            elif kind=="matrix" or (kind in {"recall","compare"} and n>2):
                for j,item in enumerate(items):
                    cards.append(tile(item,-3.73+(j%2)*7.46,.99-(j//2)*2.52,7.05,2.25,[WHITE,PALE,GREEN,WARM][j%4]))
                if kind=="matrix":
                    arrows=[Line([0,2.2,0],[0,-2.72,0],color=LINE),Line([-7.35,-.25,0],[7.35,-.25,0],color=LINE)]
            elif kind=="funnel":
                for j,item in enumerate(items):
                    y=1.7-j*1.15; w=5.8-j*.85
                    shape=Polygon([-5.8-w/2,y+.46,0],[-5.8+w/2,y+.46,0],[-5.8+w/2-.24,y-.46,0],[-5.8-w/2+.24,y-.46,0],fill_color=PALE,fill_opacity=1,stroke_color=BLUE).shift(RIGHT*2.9)
                    label=tx(item["label"],24,BLUE,w-.6,.5,True).move_to([-2.9,y,0])
                    value=tx(" · ".join(filter(None,[item.get("value"),item.get("detail")])),23,INK,7.8,.8).move_to([3.25,y,0])
                    cards.append(VGroup(shape,label,value))
            elif kind in {"compare","recall"}:
                cards=[tile(item,-3.73+j*7.46,-.15,7.05,4.1,PALE if j==0 else WARM,large_icon=True) for j,item in enumerate(items)]
            else:
                w=(14.5-(n-1)*.28)/n
                cards=[tile(item,-7.25+w/2+j*(w+.28),-.15,w,4.15,large_icon=True) for j,item in enumerate(items)]
            self.play(LaggedStart(*[FadeIn(card,shift=UP*.14) for card in cards],lag_ratio=.16),run_time=.75)
            if arrows:
                self.play(*[GrowArrow(a) if isinstance(a,Arrow) else Create(a) for a in arrows],run_time=.3)
            if kind=="metrics":
                self.play(*[Indicate(card[2],color=BLUE,scale_factor=1.06) for card in cards if len(card)>2],run_time=.35)
            remaining=start+scene["duration"]-self.time
            if remaining>0:
                self.wait(remaining)
            print(f"MANIM_REVIEW_PROGRESS={i+1}/{total}",flush=True)
