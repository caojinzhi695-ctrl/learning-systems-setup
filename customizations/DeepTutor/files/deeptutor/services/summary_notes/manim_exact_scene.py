from pathlib import Path
import json
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from template_geometry import slot_width
import imageio_ffmpeg
os.environ['PATH'] = str(Path(imageio_ffmpeg.get_ffmpeg_exe()).parent) + os.pathsep + os.environ.get('PATH', '')
from manim import *
from manimpango import list_fonts
if 'Microsoft YaHei' not in list_fonts():
 raise RuntimeError('固定模板要求 Microsoft YaHei（微软雅黑）；不允许自动替换字体。')
config.pixel_width=1920;config.pixel_height=1080;config.frame_rate=30
config.frame_width=16;config.frame_height=9;config.background_color='#F6F7FA'
ROOT=Path(__file__).resolve().parent
ASSETS=ROOT/'quick_review_v1'
STORY=json.loads((ASSETS/'reference_story.json').read_text(encoding='utf8'))
PLAN_PATH=Path(os.environ.get('MANIM_REVIEW_PLAN', 'storyboard.json'))
PLAN=json.loads(PLAN_PATH.read_text(encoding='utf8')) if PLAN_PATH.exists() else None
if PLAN:
 library={s['type']:s for s in STORY}
 STORY=[dict(library[s['layout']],section=f'快复习 / {i+1:02d}',durations={'manim':s.get('duration',library[s['layout']]['durations']['manim'])}) for i,s in enumerate(PLAN['scenes'])]
ACTIVE={}
CAPTURE=[]
# Only text values are replaceable. Geometry, fonts, colors and timing below
# are the original reference-video code and are deliberately not model inputs.
INK='#253B52';BLUE='#3466E8';MUTED='#7E8DA2';PALE='#EDF3FF';LINE='#DFE7F3';ORANGE='#C88648';GREEN='#43977A'
def tx(s,size=25,color=INK,bold=False,width=None):
 # Stable slot IDs follow actual draw order, including duplicate labels.
 # The two page-corner labels are fixed branding, never model-controlled.
 original=s
 key=None
 if not (s.startswith('快复习 / ') or s=='MANIM / 教学版'):
  index=len(CAPTURE[-1])
  key=['title','subtitle','caption','note'][index] if index<4 else f'body_{index-3:02d}'
  CAPTURE[-1][key]={'example':s,'font_size':size,'bold':bold,'width':width}
  s=ACTIVE[key] if PLAN else s
 o=Text(s,font='Microsoft YaHei',font_size=size,color=color,weight=BOLD if bold else NORMAL)
 if PLAN and key and s != original:
  # Check real glyph bounds, not the length of the original example string.
  safe=slot_width(PLAN['scenes'][len(CAPTURE)-1]['layout'],key,width)
  if o.width > safe:
   if safe/o.width < .90:
    raise ValueError(f'排版空间不足：第{len(CAPTURE)}页 {key}，请精简文案。')
   o.scale_to_fit_width(safe)
 if width and o.width>width:o.scale_to_fit_width(width)
 return o
def text(s,x,y,size=25,color=INK,bold=False,width=None):return tx(s,size,color,bold,width).move_to([x,y,0])
def box(x,y,w,h,fill=WHITE,color=LINE):return RoundedRectangle(width=w,height=h,corner_radius=.17,fill_color=fill,fill_opacity=1,stroke_color=color,stroke_width=1.4).move_to([x,y,0])
def arrow(a,b,color=BLUE):return Arrow(a,b,buff=.12,color=color,stroke_width=3,max_tip_length_to_length_ratio=.18)
def tile(x,y,w,h,rows,number=None):
 g=VGroup(box(x,y,w,h));top=y+h/2-.45
 for i,s in enumerate(rows):g.add(text(s,x,top-i*.58,28 if i==0 else 22,BLUE if i==0 else MUTED,i==0,width=w-.35))
 return g
class AutoReview(Scene):
 def begin(self,i):
  global ACTIVE
  CAPTURE.append({})
  ACTIVE=PLAN['scenes'][i]['texts'] if PLAN else {}
  print(f'MANIM_REVIEW_PROGRESS={i+1}/{len(STORY)}',flush=True)
  start=self.time
  if self.mobjects:self.play(*[FadeOut(m)for m in list(self.mobjects)],run_time=.15)
  s=STORY[i];head=tx(s['title'],39,INK,True,14.2).to_edge(LEFT,buff=.7).to_edge(UP,buff=.98)
  sub=tx(s['subtitle'],20,MUTED,width=14.4).next_to(head,DOWN,buff=.22).align_to(head,LEFT)
  self.add(tx(s['section'],14,MUTED).to_corner(UL,buff=.7).shift(UP*.14),tx('MANIM / 教学版',14,MUTED).to_corner(UR,buff=.7))
  cap=VGroup(box(0,-3.4,14.5,.64,PALE,PALE),text(s['caption'],0,-3.4,20,BLUE,True,width=13.9))
  self.add(cap,text(s['note'],0,-3.96,13,MUTED,width=14.2))
  self.play(FadeIn(head,shift=UP*.05),FadeIn(sub),run_time=.20)
  return start,s['durations']['manim']
 def hold(self,clock):
  r=clock[0]+clock[1]-self.time
  if r>0:self.wait(r)
 def reveal(self,objects,time=2,lag=.18):self.play(LaggedStart(*[FadeIn(o,shift=UP*.12)for o in objects],lag_ratio=lag),run_time=time*.45)
 def construct(self):
  for i,s in enumerate(STORY):
   clock=self.begin(i);kind=s['type']
   if kind=='intro':
    cards=[tile(-4.9+j*4.9,-.18,4.3,2.6,[a,b])for j,(a,b)in enumerate(s['cards'])]
    self.reveal(cards,1.7)
    self.play(*[GrowArrow(arrow([-2.65+j*4.9,-.18,0],[-2.25+j*4.9,-.18,0]))for j in range(2)],run_time=.25)
    self.play(FadeIn(VGroup(box(0,-2.25,12.8,.72,BLUE,BLUE),text('目标：把“感觉不错”，变成可以核对的依据',0,-2.25,25,WHITE,True,width=12.1))),run_time=.25)
   elif kind=='principles':
    cards=[]
    for j,rows in enumerate(s['cards']):
     x=-5.4+j*3.6;g=tile(x,-.12,3.15,4.2,rows);cards.append(g)
     if j==0:
      g.add(*[Circle(radius=r,fill_color=BLUE if k==0 else '#B8CCF8',fill_opacity=1,stroke_width=0).move_to([x+dx,-1.34+dy,0])for k,(dx,dy,r)in enumerate([(-.4,0,.28),(.35,.25,.14),(.35,-.25,.14)])])
     elif j==1:
      g.add(VMobject(stroke_color=BLUE,stroke_width=4).set_points_as_corners([[x-.9,-1.8,0],[x-.4,-1.55,0],[x,-1.65,0],[x+.8,-.95,0]]))
     elif j==2:
      g.add(box(x,-1.32,1.1,.80,'#FFE1BB','#C99963'),Line([x,-1.72,0],[x,-.92,0],color='#BC8C57'))
     else:
      g.add(*[RoundedRectangle(width=.35,height=h,corner_radius=.04,fill_color=BLUE,fill_opacity=1,stroke_width=0).move_to([x-.6+k*.6,-1.85+h/2,0])for k,h in enumerate([.4,.65,.95])])
    self.reveal(cards,3.5,.35)
    for g in cards:self.play(Indicate(g[1],color=BLUE,scale_factor=1.06),run_time=.25)
   elif kind=='overview':
    prompt=text('先在心里回答，再看答案。',0,0,34,BLUE,True)
    self.add(prompt);self.wait(1.7);self.play(FadeOut(prompt),run_time=.2)
    cards=[]
    for j,(a,b)in enumerate(s['cards']):
     x=-5.4+(j%4)*3.6;y=.8-(j//4)*2.15
     cards.append(tile(x,y,3.15,1.8,[f'{j+1:02d}  {a}',b]))
    self.reveal(cards,4,.20)
   elif kind=='demand':
    specs=[('① 销量','≥50 件 / 日','类目 BSR + 日均销量'),('⑤ 需求','≥10 万','关键词搜索量；周期待明'),('⑤ 需求','>1.5','供需比；需求 ÷ 竞争')]
    cards=[]
    for j,(a,n,b)in enumerate(specs):
     x=-4.9+j*4.9;cards.append(VGroup(box(x,-.3,4.45,4.05),text(a,x,1.16,26,BLUE,True),text(n,x,.2,36,BLUE,True,width=4.0),text(b,x,-.72,20,MUTED,width=4.05)))
    self.reveal(cards,3)
    questions=VGroup(text('站点',-3,-2.67,22,ORANGE,True),text('类目',-1,-2.67,22,ORANGE,True),text('周期',1,-2.67,22,ORANGE,True),text('指标定义',3,-2.67,22,ORANGE,True))
    self.play(FadeIn(questions),run_time=.25)
   elif kind=='competition':
    cards=[tile(-4.9+j*4.9,.15,4.45,2.5,rows)for j,rows in enumerate(s['cards'])]
    self.reveal(cards,2.4)
    ambiguity=VGroup(box(0,-2.08,13.6,1.14,'#FFF5E8','#E8C9A5'),text('原文“≤500 件”：对应指标与单位未明确',0,-2.08,28,ORANGE,True,width=12.9))
    self.play(FadeIn(ambiguity,shift=UP*.1),run_time=.3)
    self.play(Indicate(ambiguity,color=ORANGE,scale_factor=1.01),run_time=.4)
   elif kind=='profit':
    cards=[VGroup(box(-4.65,-.08,4.3,3.45),text('原文毛利率目标',-4.65,1,25,BLUE,True),text('≥30%',-4.65,-.15,55,BLUE,True),text('先明确成本范围',-4.65,-1.13,20,MUTED)),VGroup(box(0,-.08,4.3,3.45),text('原文谨慎区间',0,1,25,ORANGE,True),text('<20%',0,-.15,55,ORANGE,True),text('原文提示“慎选”',0,-1.13,20,MUTED)),VGroup(box(4.65,-.08,4.3,3.45),text('比较之前',4.65,1,25,BLUE,True),text('统一口径',4.65,-.15,36,INK,True),text('毛利 ≠ 扣齐费用后的利润',4.65,-1.13,18,MUTED,width=3.9))]
    self.reveal(cards,3)
    self.play(FadeIn(text('产品成本：至少包含出厂价与包装费',0,-2.55,24,MUTED)),run_time=.25)
   elif kind=='reputation':
    vals=['≥4.0','≤5%','≤10%'];cards=[]
    for j,(a,_,b)in enumerate(s['cards']):
     x=-4.9+j*4.9;cards.append(VGroup(box(x,-.3,4.45,4.05),text(a,x,1.14,25,BLUE,True,width=4.0),text(vals[j],x,.18,52,BLUE,True),text(b,x,-.85,22,ORANGE if j==0 else MUTED,width=4.0)))
    self.reveal(cards,3)
    self.play(FadeIn(text('评价反馈 + 使用结果：两边都看',0,-2.68,23,MUTED)),run_time=.25)
   elif kind=='logistics':
    package=VGroup(Polygon([-5.9,-1.6,0],[-3.8,-1.6,0],[-3.8,.1,0],[-5.9,.1,0],fill_color='#FFE1BA',fill_opacity=1,stroke_color='#C79C6C'),Polygon([-5.9,.1,0],[-5.2,.62,0],[-3.1,.62,0],[-3.8,.1,0],fill_color='#FFF0D6',fill_opacity=1,stroke_color='#C79C6C'),Polygon([-3.8,-1.6,0],[-3.1,-1.05,0],[-3.1,.62,0],[-3.8,.1,0],fill_color='#F2D1A6',fill_opacity=1,stroke_color='#C79C6C'))
    self.play(FadeIn(package,shift=UP*.15),run_time=.25)
    weight=VGroup(text('重量参考 ≤2kg',-4.5,1.27,29,BLUE,True),text('长',-4.85,-1.95,22,ORANGE),text('宽',-3.08,-1.55,22,ORANGE),text('高',-6.22,-.7,22,ORANGE))
    self.play(FadeIn(weight),run_time=.3)
    rows=[('包装后长 × 宽 × 高',.85),('核对实际尺寸分段',-.12),('配送费 + 仓储费',-1.09)]
    self.reveal([VGroup(box(3.4,y,6.4,.72),text(a,3.4,y,25,BLUE,True))for a,y in rows],2)
    self.play(FadeIn(text('仓储：占用体积、存放时间等',3.4,-2.2,21,MUTED,width=6.5)),run_time=.25)
   elif kind=='compliance':
    left=VGroup(box(-3.7,-.3,6.9,4.2),text('⑦ 合规：先核实准入与风险',-3.7,1.16,27,BLUE,True,width=6.4),text('是否需要强制认证？',-3.7,.35,25),text('商标、专利等侵权风险？',-3.7,-.45,25),text('结合产品与目标站点核查',-3.7,-1.5,21,MUTED))
    right=VGroup(box(3.7,-.3,6.9,4.2),text('⑧ 趋势：类目销量增长率',3.7,1.16,27,BLUE,True,width=6.4),text('≥10%',3.7,.22,54,BLUE,True),text('原文参考；统计周期未说明',3.7,-.78,21,MUTED),text('同比？环比？比较哪一期？',3.7,-1.5,21,ORANGE))
    self.reveal([left,right],2.2)
   elif kind=='recap':
    cards=[]
    for j,(a,b)in enumerate(s['cards']):
     x=-5.4+j*3.6;cards.append(tile(x,-.18,3.15,3.5,[f'0{j+1}  {a}',b]))
    self.reveal(cards,3)
    self.play(FadeIn(VGroup(box(0,-2.65,13.4,.62,BLUE,BLUE),text('四原则定方向 → 八指标找依据 → 口径明确再判断',0,-2.65,23,WHITE,True,width=12.8))),run_time=.25)
   self.hold(clock)

  if os.environ.get('MANIM_CAPTURE_TEXTS'):
   Path(os.environ['MANIM_CAPTURE_TEXTS']).write_text(json.dumps(CAPTURE,ensure_ascii=False,indent=2),encoding='utf8')
