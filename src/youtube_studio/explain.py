"""Bounded, reusable explanations: source highlights and persistent objects."""
import html
import json
import math
import re
import shutil
from collections import defaultdict

from .core import require, number, normalize

KINDS = {'evidence', 'object_scene', 'essay_scene'}
CSS = '''
.explain-title{position:absolute;left:140px;top:90px;font-size:54px;font-weight:600;max-width:1640px}
.explain-world{position:absolute;inset:0;background:#f4f0e4}
.explain-object{position:absolute;width:300px;height:180px;border:3px solid #50634d;border-radius:24px;background:#faf7ef;display:flex;align-items:center;justify-content:center;flex-direction:column;padding:18px;font-size:40px;text-align:center;color:#202724}
.explain-object.token{border-radius:90px;background:#e2e9d9}.explain-object img{width:230px;height:95px;object-fit:contain;margin-bottom:8px}.explain-object:has(img){height:240px}
.explain-object.company,.explain-object.cash,.explain-object.person,.explain-object.document{height:270px;border:0;background:transparent;gap:14px}.object-drawing{width:220px;height:155px;flex-shrink:0}
.explain-context{position:absolute;left:140px;top:210px;font-size:38px;color:#994027;max-width:1640px}
.explain-link{position:absolute;height:6px;background:#50634d;transform-origin:left center}
.explain-link:after{content:'';position:absolute;right:-2px;top:-9px;border-left:18px solid #50634d;border-top:12px solid transparent;border-bottom:12px solid transparent}
.evidence-page{position:absolute;object-fit:contain;border:1px solid #a9a99d}
.evidence-mark{position:absolute;border:4px solid #ae3d2f;transform-origin:left center;pointer-events:none}
.evidence-label{position:absolute;left:160px;top:660px;width:1500px;font-size:46px;line-height:1.5;color:#202724;border-left:6px solid #ae3d2f;padding-left:24px}
.evidence-credit{position:absolute;left:140px;top:810px;width:1640px;font-size:25px;color:#53594e}
'''


def asset_refs(shot):
    refs = [(shot.get('asset'), shot.get('provenance'), shot['id'])]
    refs += [(o.get('asset'), o.get('provenance'), f"{shot['id']}-{o['id']}") for o in shot.get('objects', [])]
    return [(p, provenance, key) for p, provenance, key in refs if p]


def validate_shot(s, text, sources):
    if s['kind'] == 'essay_scene':
        from .essay import validate
        return validate(s, text, sources)
    sid = s['id']
    require(isinstance(s.get('headline'), str) and 0 < len(s['headline']) <= 26, f'{sid} headline 须为 1–26 字')
    require(bool(s.get('note')), f'{sid} 需要表达边界 note')
    if s['kind'] == 'evidence':
        require(s.get('layout', 'stacked') in {'stacked', 'beside'}, '证据布局无效')
        require(s.get('source_id') in sources and bool(s.get('page')), f'{sid} 证据需 source_id 与原文页码/位置')
        require(isinstance(s.get('asset'),str) and s['asset'] and bool(s.get('provenance')), f'{sid} 需要真实原始材料截图及来源')
        require(isinstance(s.get('credit'),str) and 0 < len(s['credit']) <= 90, f'{sid} 需要来源署名')
        require(re.fullmatch(r'[a-f0-9]{64}', s.get('source_sha256','')), f'{sid} 需要截图 SHA-256')
    else:
        require(re.fullmatch(r'[a-z][a-z0-9-]{0,40}', s.get('scene_id','')), f'{sid} scene_id 无效')
        require(s.get('variant') in {'context','relation'}, f'{sid} variant 无效')
        objects = s.get('objects', [])
        require(isinstance(objects,list) and 1 <= len(objects) <= 6, f'{sid} 需 1–6 个对象')
        ids = set()
        for o in objects:
            require(isinstance(o,dict) and re.fullmatch(r'[a-z][a-z0-9-]{0,30}',o.get('id','')) and o['id'] not in ids, f'{sid} 对象 ID 无效/重复')
            ids.add(o['id'])
            require(isinstance(o.get('label'),str) and 0 < len(o['label']) <= 14, f'{sid} 对象标签过长')
            require(o.get('shape','card') in {'card','token','company','cash','person','document'}, f'{sid} shape 无效')
            number(o.get('x'),140,1480,'object.x');number(o.get('y'),310,540,'object.y')
            if o.get('asset'):require(isinstance(o['asset'],str) and bool(o.get('provenance')), f'{sid} 对象图片需要来源')
    events=s.get('events',[])
    require(isinstance(events,list) and events, f'{sid} 缺少 events')
    for e in events:
        require(isinstance(e,dict) and isinstance(e.get('cue'),str) and (not e['cue'] or (normalize(e['cue']) and text.count(normalize(e['cue']))==1)),f'{sid} 动作锚点不唯一')
        number(e.get('duration',.55),.1,1.5,'event.duration')
        if s['kind']=='evidence':
            require(e.get('action')=='highlight', f'{sid} 证据只支持 highlight')
            rect=e.get('rect',[]);require(isinstance(rect,list) and len(rect)==4,f'{sid} rect 为归一化 x,y,w,h')
            for v in rect:number(v,0,1,'rect')
            require(rect[2]>0 and rect[3]>0 and rect[0]+rect[2]<=1 and rect[1]+rect[3]<=1,f'{sid} 高亮越出原始截图')
            require(isinstance(e.get('label'),str) and 0<len(e['label'])<=36,f'{sid} 证据解释须在 36 字内')
        else:
            require(e.get('action') in {'reveal','move','emphasize','context','connect'},f'{sid} action 无效')
            if e['action']=='context':
                require(isinstance(e.get('label'),str) and 0<len(e['label'])<=36,f'{sid} 情境文字过长')
            else:
                require(e.get('target') in ids,f'{sid} 对象不存在')
                if e['action']=='move':number(e.get('x'),140,1480,'move.x');number(e.get('y'),310,540,'move.y')
                if e['action']=='connect':require(e.get('to') in ids and e['to']!=e['target'],f'{sid} 连接目标无效')


def validate_scenes(shots):
    """One declaration and a continuous interval per scene; no invisible actions."""
    groups=defaultdict(list)
    for i,s in enumerate(shots):
        if s['kind']=='object_scene':groups[s['scene_id']].append((i,s))
    for key,group in groups.items():
        require([i for i,_ in group]==list(range(group[0][0],group[-1][0]+1)),f'{key} 场景被其他镜头打断')
        first=group[0][1];shown=set();linked=set()
        for _,s in group:
            require(s['objects']==first['objects'] and s['variant']==first['variant'],f'{key} 跨单元对象声明不一致')
            for e in s['events']:
                action=e['action'];target=e.get('target')
                if action=='reveal':require(target not in shown,f'{key} 对象重复入场');shown.add(target)
                elif action in {'move','emphasize','connect'}:
                    require(target in shown,f'{key} 动作引用尚未出现的对象')
                    if action=='move':require(target not in linked,f'{key} 已连线对象暂不支持移动')
                    if action=='connect':
                        require(e['to'] in shown,f'{key} 连线目标尚未出现');linked.update([target,e['to']])


def freeze(media, src, name):
    filename=name+src.suffix.lower();shutil.copy2(src, media/filename)
    return 'media/'+filename


def render_evidence(s,media,assets):
    esc=html.escape;sid=s['id'];w,h=s['image_size'];scale=min(1640/w,430/h)
    width,height=w*scale,h*scale;x,y=140+(1640-width)/2,230+(390-height)/2
    beside=s.get('layout')=='beside'
    if beside:
        scale=min(1070/w,640/h)
        width,height=w*scale,h*scale
        x,y=120+(1070-width)/2,155+(640-height)/2
    label_style=' style="left:1250px;top:350px;width:500px;white-space:pre-line;font-size:56px"' if beside else ''
    src=freeze(media,assets[sid],sid)
    body=f'<div class="explain-title">{esc(s["headline"])}</div><img class="evidence-page" src="{src}" style="left:{x}px;top:{y}px;width:{width}px;height:{height}px"/>'
    motion=[]
    for i,e in enumerate(s['events']):
        a,b,c,d=e['rect'];mark=f'{sid}-mark-{i}';label=f'{sid}-explanation-{i}';at=e['at'];duration=e.get('duration',.55)
        body+=f'<div id="{mark}" class="evidence-mark" data-layout-allow-overlap style="left:{x+a*width}px;top:{y+b*height}px;width:{c*width}px;height:{d*height}px"></div><div id="{label}" class="evidence-label"{label_style}>{esc(e["label"])}</div>'
        motion += [f'tl.fromTo("#{mark}",{{opacity:0,scaleX:0}},{{opacity:1,scaleX:1,duration:{duration},ease:"power2.out"}},{at});',f'tl.fromTo("#{label}",{{opacity:0,y:12}},{{opacity:1,y:0,duration:{duration}}},{at});']
        if i+1<len(s['events']):
            nxt=s['events'][i+1]['at'];motion.append(f'tl.to("#{mark},#{label}",{{opacity:0,duration:.15}},{nxt-.15});')
    body+=f'<div class="evidence-credit">{esc(s["credit"])} · {esc(str(s["page"]))}</div>'
    return body,motion


def object_drawing(shape):
    """Code-native explanation objects, not stock photos or event evidence."""
    pieces={
        'company':'<path d="M20 60L110 10L200 60V145H20Z" fill="#e2e9d9" stroke="#50634d" stroke-width="5"/><path d="M80 145V90H140V145" fill="#faf7ef" stroke="#50634d" stroke-width="4"/><path d="M40 70H65M155 70H180M40 100H65M155 100H180" stroke="#50634d" stroke-width="10"/>',
        'cash':'<rect x="16" y="40" width="180" height="100" rx="8" fill="#c9d7bd" stroke="#50634d" stroke-width="4"/><rect x="30" y="24" width="180" height="100" rx="8" fill="#e2e9d9" stroke="#50634d" stroke-width="4"/><circle cx="120" cy="74" r="28" fill="#faf7ef" stroke="#50634d" stroke-width="3"/><path d="M60 58V90M180 58V90" stroke="#50634d" stroke-width="6"/>',
        'person':'<circle cx="110" cy="40" r="28" fill="#e2e9d9" stroke="#50634d" stroke-width="4"/><path d="M50 145V113C50 65 170 65 170 113V145" fill="#e2e9d9" stroke="#50634d" stroke-width="4"/>',
        'document':'<path d="M55 10H145L175 40V145H55Z" fill="#faf7ef" stroke="#50634d" stroke-width="4"/><path d="M145 10V40H175M78 65H150M78 88H150M78 111H130" fill="none" stroke="#50634d" stroke-width="5"/>'}
    if shape not in pieces:return ''
    return '<svg class="object-drawing" viewBox="0 0 220 155" aria-hidden="true">'+pieces[shape]+'</svg>'


def render_objects(shots,media,assets):
    groups=defaultdict(list)
    for s in shots:groups[s['scene_id']].append(s)
    body=[];motion=[]
    for scene,group in groups.items():
        first=group[0];prefix='world-'+scene;start=first['start'];end=group[-1]['end']
        fragment=f'<section id="{prefix}-clip" class="clip shot" data-start="{start}" data-duration="{end-start}" data-track-index="40"><div id="{prefix}" class="explain-world"><div class="explain-title">{html.escape(first["headline"])}</div>'
        positions={o['id']:(o['x'],o['y']) for o in first['objects']};orig=dict(positions)
        for o in first['objects']:
            oid=prefix+'-'+o['id'];art=object_drawing(o.get('shape','card'))
            if o.get('asset'):
                src=freeze(media,assets[first['id']+'-'+o['id']],oid)
                art=f'<img src="{src}"/>'
            fragment+=f'<div id="{oid}" class="explain-object {o.get("shape","card")}" style="left:{o["x"]}px;top:{o["y"]}px">{art}<span>{html.escape(o["label"])}</span></div>'
        contexts=[];notes=[]
        for s in group:
            if s.get('show_note', True):
                note_id=prefix+'-note-'+s['id'];notes.append((note_id,s['start']))
                fragment+=f'<div id="{note_id}" class="note">{html.escape(s["note"])}</div>'
            for e in s['events']:
                at=e['at'];dur=e.get('duration',.55);target=e.get('target');oid=prefix+'-'+str(target);action=e['action']
                if action=='reveal':motion.append(f'tl.fromTo("#{oid}",{{opacity:0,scale:.92}},{{opacity:1,scale:1,duration:{dur},ease:"power2.out"}},{at});')
                elif action=='move':
                    x,y=positions[target];ox,oy=orig[target]
                    motion.append(f'tl.fromTo("#{oid}",{{x:{x-ox},y:{y-oy}}},{{x:{e["x"]-ox},y:{e["y"]-oy},duration:{dur},immediateRender:false,ease:"power2.inOut"}},{at});');positions[target]=(e['x'],e['y'])
                elif action=='emphasize':motion.append(f'tl.fromTo("#{oid}",{{borderColor:"#50634d"}},{{borderColor:"#ae3d2f",duration:{dur},immediateRender:false}},{at});')
                elif action=='context':
                    cid=prefix+'-context-'+str(len(contexts));contexts.append((cid,at));fragment+=f'<div id="{cid}" class="explain-context">{html.escape(e["label"])}</div>'
                elif action=='connect':
                    ax,ay=positions[target];bx,by=positions[e['to']];dx,dy=bx-ax,by-ay;length=math.hypot(dx,dy)-320
                    require(length>30,'连线对象距离太近')
                    angle=math.atan2(dy,dx);x=ax+150+160*math.cos(angle);y=ay+90+160*math.sin(angle)
                    lid=prefix+'-link-'+str(len(motion));fragment+=f'<div id="{lid}" class="explain-link" style="left:{x}px;top:{y}px;width:{length}px;rotate:{math.degrees(angle)}deg"></div>'
                    motion.append(f'tl.fromTo("#{lid}",{{scaleX:0,opacity:0}},{{scaleX:1,opacity:1,duration:{dur}}},{at});')
        for items in [contexts,notes]:
            for i,(cid,at) in enumerate(items):
                motion.append(f'tl.fromTo("#{cid}",{{opacity:0}},{{opacity:1,duration:.2}},{at});')
                if i+1<len(items):motion.append(f'tl.to("#{cid}",{{opacity:0,duration:.15}},{items[i+1][1]-.15});')
        body.append(fragment+'</div></section>')
    return ''.join(body),motion
