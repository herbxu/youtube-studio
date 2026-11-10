"""Paper diagrams with measured voice cues. Only declarative SVG primitives are accepted."""
import html
import json
import re
import shutil

from .core import normalize, number, require

SHAPES = {
    'g': set(), 'text': {'x','y','font-size','font-weight','text-anchor','letter-spacing','font-family'},
    'rect': {'x','y','width','height','rx'}, 'path': {'d','stroke-dasharray'},
    'circle': {'cx','cy','r'}, 'image': {'x','y','width','height','preserveAspectRatio'},
}
PAINT = {'fill','stroke','stroke-width','opacity','stroke-linecap','stroke-linejoin'}
TWEENS = {'opacity','x','y','rotation','scaleX','scaleY','strokeDashoffset'}

def validate(s, text, sources):
    require(s.get('paper_tone','warm') in {'warm','neutral'}, '纸色无效')
    require(s.get('surface') in {'notepaper','accountbook'}, '纸面背景无效')
    if s.get('variant')=='record':
        require(s.get('source_id') in sources and s.get('asset') and s.get('provenance'), '笔记需要原文来源与证据剪贴')
        require(s.get('chart_source_id') in sources and re.fullmatch('[a-f0-9]{64}',s.get('source_sha256','')),
                '证据剪贴需要来源和原图指纹')
    elif s.get('variant') == 'analysis':
        require(s.get('source_id') in sources, '研究纸页需要注明材料来源')
        if s.get('asset'):
            require(s.get('provenance') and re.fullmatch('[a-f0-9]{64}', s.get('source_sha256', '')),
                    '研究剪贴需要出处和素材指纹')
    else:
        require(s.get('hypothetical') is True, '账本算例须注明假设')
    clippings = {}
    for clipping in s.get('objects', []):
        key = clipping.get('id','')
        require(re.fullmatch(r'[a-z][a-z0-9-]{0,48}',key) and key not in clippings, '纸面剪贴标识无效或重复')
        require(clipping.get('asset') and clipping.get('provenance') and re.fullmatch('[a-f0-9]{64}',clipping.get('source_sha256','')), '纸面剪贴需要文件、来源和指纹')
        clippings[key] = clipping
    seen = set()
    def visit(n):
        kind = n.get('shape')
        require(kind in SHAPES, '纸面图元无效')
        key=n.get('id','')
        require(re.fullmatch(r'[a-z][a-z0-9-]{0,48}',key) and key not in seen,'纸面对象标识无效')
        seen.add(key)
        attrs=n.get('attrs',{})
        require(isinstance(attrs,dict) and set(attrs)<=SHAPES[kind]|PAINT, '纸面属性无效')
        for prop in ('fill','stroke'):
            if prop in attrs:
                require(re.fullmatch(r'#[0-9a-fA-F]{6}|none',str(attrs[prop])), '纸面颜色无效')
        if kind=='image':
            if 'clipping' in n:require(n['clipping'] in clippings,'图片引用了未知剪贴')
            else:require(s.get('asset') and s.get('provenance'), '剪贴图片缺少来源')
        if kind=='text':require(isinstance(n.get('text'),str) and len(n['text'])<=100, '纸面文字过长')
        if n.get('children'):require(kind=='g', '仅图组可包含子图元')
        for child in n.get('children',[]):visit(child)
    require(isinstance(s.get('drawing'),list) and s['drawing'], '缺少纸面图元')
    require(isinstance(s.get('events'),list) and s['events'], '缺少纸面动作')
    for node in s['drawing']:visit(node)
    for e in s['events']:
        require(e.get('target') in seen and e.get('action')=='animate','纸面动作的对象无效')
        cue=normalize(e.get('cue',''))
        require(not cue or text.count(cue)==1,'纸面动作需要唯一语音锚点')
        a,b=e['from'],e['to']
        require(a and set(a)==set(b) and set(a)<=TWEENS,'动画起止属性须匹配')
        for values in (a,b):
            for key,value in values.items():
                if key in ('opacity','strokeDashoffset'):number(value,0,1,key)
                elif key.startswith('scale'):number(value,0,10,key)
                else:number(value,-4000,4000,key)
        number(e.get('duration',.65),.1,1.5,'纸面动画时长')

def render(s, media, assets):
    sid=s['id']
    filename=''
    if s.get('asset'):
        source=assets[sid]
        filename=f'{sid}-clipping{source.suffix}'
        shutil.copy2(source,media/filename)
    clippings = {}
    for clipping in s.get('objects', []):
        key = f'{sid}-{clipping["id"]}'
        source = assets[key]
        clippings[clipping['id']] = key+source.suffix
        shutil.copy2(source,media/clippings[clipping['id']])
    def svg(n):
        kind=n['shape']
        attrs={**n.get('attrs',{}),'id':sid+'-'+n['id']}
        if kind=='image':attrs['href']='media/'+(clippings[n['clipping']] if 'clipping' in n else filename)
        if n.get('trace'):
            attrs.update(pathLength='1',**{'stroke-dasharray':'1','stroke-dashoffset':'1'})
        properties=' '.join(f'{k}="{html.escape(str(v),quote=True)}"' for k,v in attrs.items())
        content=html.escape(n.get('text',''))+''.join(svg(c) for c in n.get('children',[]))
        return f'<{kind} {properties}>{content}</{kind}>'
    surface=s['surface']
    tone=s.get('paper_tone','warm')
    body=f'<div class="motion-essay {surface} paper-art tone-{tone}"><svg width="1920" height="900" viewBox="0 0 1920 900" style="position:absolute;top:0;left:0;overflow:hidden;font-family:StudioMotion,sans-serif">'
    body+=''.join(svg(n) for n in s['drawing'])+'</svg></div>'
    motion=[]
    for e in s['events']:
        start=dict(e['from']);end=dict(e['to'],duration=e.get('duration',.65),ease='sine.inOut',immediateRender=False)
        if 'scaleX' in start or 'scaleY' in start:
            start['transformOrigin']='0% 50%';end['transformOrigin']='0% 50%'
        # SVG pathLength units must stay numeric in the attribute domain.
        if 'strokeDashoffset' in start:
            start['attr']={'stroke-dashoffset':start.pop('strokeDashoffset')}
            end['attr']={'stroke-dashoffset':end.pop('strokeDashoffset')}
        motion.append(f'tl.fromTo("#{sid}-{e["target"]}",{json.dumps(start)},{json.dumps(end)},{e["at"]});')
    return body,motion
