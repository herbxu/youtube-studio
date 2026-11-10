"""Cue-driven editorial objects. No template headings or decorative body copy."""
import html
import json
import re
from functools import lru_cache
from pathlib import Path
from .core import require, number, normalize

CSS='''
@font-face{font-family:StudioMotion;src:url('media/font.ttf');font-weight:100 900}
@font-face{font-family:StudioNoteSerif;src:local("Songti SC Bold"),local("STSongti-SC-Bold");font-weight:600}
.motion-essay{position:absolute;inset:0;background:#f4f0e4;color:#203b36;font-family:StudioMotion,sans-serif}
.me-object{position:absolute;display:flex;align-items:center;justify-content:center;flex-direction:column;line-height:1.3;transform-origin:center center;opacity:0;text-align:center;font-weight:550}
.me-object.ticket{background:#fffcf4;border:2px solid #9ea99b;border-radius:5px;box-shadow:0 12px 0 #dfddcf}
.me-object.ticket:before,.me-object.ticket:after{content:'';position:absolute;width:12px;height:12px;border:2px solid #9ea99b;border-radius:50%;background:#f4f0e4;top:calc(50% - 6px)}
.me-object.ticket:before{left:-7px}.me-object.ticket:after{right:-7px}
.me-object.stamp{border:7px solid #a84631;color:#a84631;letter-spacing:0}
.me-box-text{position:relative;display:block;line-height:1;white-space:nowrap;flex:none}
.me-object.value{border-bottom:2px solid #b7c1b3}
.me-label{font-size:35px;line-height:1.4;font-weight:400;color:#53655c;margin-bottom:20px}
.me-amount{display:flex;align-items:baseline;gap:15px;line-height:1.15}
.me-amount small{font-size:39px;font-weight:400}
.me-object.bar{background:#b65b3c;transform-origin:left center;border-radius:4px}
.me-object.text{white-space:pre-line}
.motion-essay.notepaper{background:linear-gradient(120deg,#1e3938,#354d46 70%,#243b37)}
.notepaper:before{content:"";position:absolute;inset:76px 105px 190px 112px;transform:rotate(-.8deg);background:linear-gradient(95deg,#e0d3b9,#faf4e5 3%,#fcf6e9 82%,#f1e8d7);box-shadow:10px 22px 34px #122b2840}
.notepaper .me-object.text{align-items:flex-start;text-align:left;font-family:StudioNoteSerif,StudioMotion,serif;font-weight:600}
.notepaper .me-object.text:first-child{font-family:StudioMotion,sans-serif;font-weight:450}
.motion-essay.accountbook{background:#f7f3e9}
.motion-essay.notepaper.tone-neutral{background:linear-gradient(120deg,#2d3537,#3b4242 70%,#303839)}
.notepaper.tone-neutral:before{background:linear-gradient(95deg,#deded9,#f3f3ee 3%,#f7f7f3 82%,#eeefeb);box-shadow:8px 16px 28px #1a20232e}
.motion-essay.accountbook.tone-neutral{background:#f4f4ef}
.accountbook.paper-art:before{display:none}
.accountbook:before{content:"";position:absolute;left:200px;right:216px;top:228px;height:600px;border-top:3px solid #677970;background:linear-gradient(to bottom,transparent 205px,#bbc2b5 205px,#bbc2b5 207px,transparent 207px,transparent 384px,#849487 384px,#849487 388px,transparent 388px)}
.accountbook .me-object.text{align-items:flex-start;text-align:left;font-variant-numeric:tabular-nums}
.accountbook .me-object.text[data-align="right"]{align-items:flex-end;text-align:right;font-family:"Menlo",StudioMotion,monospace}
'''

@lru_cache(maxsize=128)
def box_ink_offset(text):
    """Center actual glyph bounds, not the font's asymmetric line box.

    The local variable font and CSS weight are paired; no runtime font measurement
    or asynchronous layout changes are needed during seeking/rendering.
    """
    from fontTools.ttLib import TTFont
    from fontTools.pens.boundsPen import BoundsPen
    path=Path(__file__).resolve().parents[2]/'resources/fonts/noto-sans-sc.ttf'
    with TTFont(path) as font:
        glyphs=font.getGlyphSet(location={'wght':550});cmap=font.getBestCmap();advance=0;bounds=[]
        for char in text:
            require(ord(char) in cmap,'框内文字缺少本地字形')
            glyph=glyphs[cmap[ord(char)]];pen=BoundsPen(glyphs);glyph.draw(pen)
            if pen.bounds:
                x0,y0,x1,y1=pen.bounds;bounds.append((advance+x0,y0,advance+x1,y1))
            advance+=glyph.width
        require(bounds,'框内文字不可为空')
        x0=min(b[0] for b in bounds);x1=max(b[2] for b in bounds)
        y0=min(b[1] for b in bounds);y1=max(b[3] for b in bounds);em=font['head'].unitsPerEm
        return ((advance-x0-x1)/(2*em),(y0+y1-font['hhea'].ascent-font['hhea'].descent)/(2*em))

def validate(s,text,sources):
    require(s.get('surface','plain') in {'plain','notepaper','accountbook'},'motion surface无效')
    require(s.get('variant') in {'record','question','business','valuation','risk','closing'},'motion variant无效')
    require(not s.get('asset'),'motion布局不接收无动作的装饰背景图')
    if s['variant'] in {'business','valuation','risk'}:
        require(s.get('hypothetical') is True,'数值示意必须明确为假设')
    if s['variant']=='record':require(s.get('source_id') in sources,'个人记录需真实来源')
    require(s.get('source_id') is None or s['source_id'] in sources,'动态图解来源ID无效')
    objects=s.get('motion_objects',[])
    require(isinstance(objects,list) and 1<=len(objects)<=14,'motion_objects需1–14个有明确作用的对象')
    ids=set()
    for o in objects:
        require(o.get('align','center') in {'center','right'},'motion align无效')
        require(isinstance(o.get('id'),str) and re.fullmatch('[a-z][a-z0-9-]{0,30}',o['id']) and o['id'] not in ids,'motion object ID无效/重复');ids.add(o['id'])
        require(o.get('type') in {'text','ticket','stamp','value','bar'},'motion object类型无效')
        for key,lo,hi in [('x',80,1750),('y',50,850),('w',10,1760),('h',5,750),('font',24,190)]:number(o.get(key,60 if key=='font' else 0),lo,hi,'object.'+key)
        require(o['x']+o['w']<=1840 and o['y']+o['h']<=890,'对象超出安全画面')
        require(isinstance(o.get('text',''),str) and len(o.get('text',''))<=32,'对象文字过长')
        require(isinstance(o.get('label',''),str) and len(o.get('label',''))<=14,'对象标签过长')
        require(isinstance(o.get('initial',False),bool),'initial须为布尔')
        require(re.fullmatch('#[0-9a-fA-F]{6}',o.get('color','#203b36')),'对象颜色须为hex')
        if o['type']=='value':number(o.get('value'),0,100000,'object.value')
        if o.get('portion') is not None:number(o['portion'],0,1,'object.portion')
    require(s.get('events'),'动态图解需要真实动作')
    values={o['id']:o['value'] for o in objects if o['type']=='value'}
    portions={o['id']:o.get('portion',1) for o in objects if o['type']=='bar'}
    for e in s['events']:
        require(e.get('target') in ids and e.get('action') in {'reveal','hide','move','focus','dim','restore','count','bar','strike'},'动态图解动作/目标无效')
        cue=e.get('cue','');require(isinstance(cue,str) and (not cue or text.count(normalize(cue))==1),'动作cue须唯一')
        number(e.get('duration',.6),.1,1.5,'motion.duration')
        if e['action'] in {'move','reveal'}:
            for k in ['x','y']:number(e.get(k,0),-1700,1700,'motion.'+k)
        if e['action']=='count':
            require(next(o for o in objects if o['id']==e['target'])['type']=='value','count只能用于数值对象')
            number(e.get('from'),0,100000,'count.from');number(e.get('to'),0,100000,'count.to')
            require(e['from']==values[e['target']],'count起值须与已有数值一致');values[e['target']]=e['to']
        if e['action']=='bar':
            require(next(o for o in objects if o['id']==e['target'])['type']=='bar','bar动作只能用于数量条')
            number(e.get('from'),0,1,'bar.from');number(e.get('to'),0,1,'bar.to')
            require(e['from']==portions[e['target']],'数量条起始比例与已有状态不一致');portions[e['target']]=e['to']

def render(s):
    sid=s['id'];at=s['start'];surface=s.get('surface','plain')
    body=f'<div class="motion-essay {surface}">';motion=[];esc=html.escape
    for o in s['motion_objects']:
        oid=f'{sid}-{o["id"]}';typ=o['type'];color=o.get('color','#203b36')
        style=f'left:{o["x"]}px;top:{o["y"]}px;width:{o["w"]}px;height:{o["h"]}px;font-size:{o.get("font",60)}px;color:{color}'
        if typ=='bar':style+=f';background:{o.get("color", "#b65b3c")}'
        content=esc(o.get('text',''))
        if typ in {'ticket','stamp'}:
            dx,dy=box_ink_offset(o.get('text',''))
            content=f'<span class="me-box-text" style="left:{dx:.7f}em;top:{dy:.7f}em">{content}</span>'
        if typ=='value':content=f'<div class="me-label">{esc(o.get("label",""))}</div><div class="me-amount"><span id="{oid}-number">{o["value"]:g}</span><small>元</small></div>'
        overlap=' data-layout-allow-overlap="true" data-layout-allow-occlusion="true"' if typ=='stamp' else ''
        body+=f'<div id="{oid}" class="me-object {typ}" data-align="{o.get("align","center")}" style="{style}"{overlap}>{content}</div>'
        init={'opacity':1 if o.get('initial') else 0,'x':0,'y':0,'scale':1,'rotation':0}
        if typ=='bar':
            # GSAP's scale shorthand also writes scaleX; do not set both.
            init.pop('scale')
            init.update(scaleX=o.get('portion',1),scaleY=1)
        motion.append(f'tl.set("#{oid}",{json.dumps(init)},{at});')
        if typ=='value':motion.append(f'tl.set("#{oid}-number",{{innerText:"{o["value"]:g}"}},{at});')
    portions={o['id']:o.get('portion',1) for o in s['motion_objects'] if o['type']=='bar'}
    opacities={o['id']:1 if o.get('initial') else 0 for o in s['motion_objects']}
    for e in s['events']:
        oid=f'#{sid}-{e["target"]}';t=e['at'];d=e.get('duration',.6);action=e['action']
        base={'duration':d,'ease':'power2.out','immediateRender':False}
        if action=='reveal':
            start={'opacity':0,'x':e.get('x',0),'y':e.get('y',35),'scale':.96};end={**base,'opacity':1,'x':0,'y':0,'scale':1}
            if e['target'] in portions:
                start.pop('scale');end.pop('scale')
                start.update(scaleX=portions[e['target']]*.96,scaleY=.96)
                end.update(scaleX=portions[e['target']],scaleY=1)
        elif action=='hide':start={'opacity':opacities[e['target']]};end={**base,'opacity':0}
        elif action=='dim':start={'opacity':opacities[e['target']]};end={**base,'opacity':.28}
        elif action=='restore':start={'opacity':.28};end={**base,'opacity':1}
        elif action=='move':
            motion.append(f'tl.to("{oid}",{json.dumps({**base,"x":e.get("x",0),"y":e.get("y",0)})},{t});');continue
        elif action=='focus':
            start={'scale':1};end={**base,'scale':1.08,'color':'#a84631'}
        elif action=='strike':
            start={'opacity':0,'scale':1.5,'rotation':-16};end={**base,'opacity':1,'scale':1,'rotation':-7,'ease':'power3.out'}
        elif action=='count':
            motion.append(f'tl.fromTo("{oid}-number",{{innerText:{e["from"]}}},{{innerText:{e["to"]},snap:{{innerText:1}},duration:{d},ease:"power2.out",immediateRender:false}},{t});');continue
        else:
            start={'scaleX':e['from']};end={**base,'scaleX':e['to']}
            portions[e['target']]=e['to']
        if 'opacity' in end:opacities[e['target']]=end['opacity']
        motion.append(f'tl.fromTo("{oid}",{json.dumps(start)},{json.dumps(end)},{t});')
    return body+'</div>',motion
