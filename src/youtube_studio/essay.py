"""Photo-led personal records and a bounded price/income comparison."""
import html
import json
from .core import require, number, normalize
from .explain import freeze

CSS='''
.essay{position:absolute;inset:0;background:#f0eee7;color:#153e3a}
.essay .eyebrow{position:absolute;left:105px;top:85px;font-size:26px;letter-spacing:4px;color:#536663}
.essay .rule{position:absolute;left:105px;top:141px;width:1710px;height:2px;background:#b6c2b8}
.essay .photo{position:absolute;object-fit:cover}
.essay .credit{position:absolute;left:105px;top:850px;font-size:23px;color:#566460;max-width:1680px}
.essay .record{position:absolute;left:105px;top:211px;width:1080px}
.essay .date{font-size:38px;color:#947451;letter-spacing:3px;margin-bottom:38px}
.essay .quote{font-size:66px;font-weight:550;line-height:1.55;margin:0;max-width:1040px}
.essay .subline{font-size:34px;color:#566460;margin-top:30px;line-height:1.5}
.essay .marker{height:13px;background:#d6b65b;width:790px;margin-top:8px;transform-origin:left center}
.essay .photo-frame{position:absolute;left:1285px;top:200px;width:530px;height:595px;overflow:hidden;border:15px solid #fffdf7;box-shadow:0 16px 38px #17383120}
.essay .photo-frame .photo{width:100%;height:100%}
.essay .full-photo{position:absolute;inset:0;width:1920px;height:1080px;object-fit:cover}
.essay .shade{position:absolute;inset:0;background:linear-gradient(90deg,rgba(8,30,29,.95),rgba(8,30,29,.64) 60%,rgba(8,30,29,.15))}
.essay .question-copy{position:absolute;left:125px;top:235px;width:1260px;text-wrap:balance;font-size:94px;line-height:1.4;font-weight:650;color:#fff8e5}
.essay .question-small{position:absolute;left:130px;top:660px;width:1300px;font-size:41px;color:#e4d4ad;line-height:1.5}
.essay .company{position:absolute;left:105px;top:220px;width:625px;height:500px;overflow:hidden;border:14px solid #fffdf7;box-shadow:0 12px 30px #17383120}
.essay .company .photo{width:100%;height:100%;object-position:72% 50%}
.essay .company-label{position:absolute;left:105px;top:745px;font-size:30px;letter-spacing:2px}
.essay .title{position:absolute;left:105px;top:75px;width:1620px;font-size:52px;font-weight:550}
.essay .price-zone{position:absolute;left:820px;top:234px;width:450px}
.essay .cash-zone{position:absolute;left:1350px;top:234px;width:470px}
.essay .label{font-size:32px;color:#65726a;margin-bottom:12px}
.essay .number{font-size:142px;line-height:1.15;font-weight:550;letter-spacing:-5px}
.essay .number small{font-size:40px;letter-spacing:0;margin-left:10px}
.essay .old-price{height:62px;font-size:45px;color:#9b8174;text-decoration:line-through;text-decoration-thickness:3px}
.essay .rate{position:absolute;left:820px;top:710px;width:980px;padding:20px 28px;background:#dae3d7;font-size:42px;line-height:1.4;border-left:6px solid #6c8a76}
.essay .coin-row{position:absolute;left:1350px;top:540px;width:450px;display:grid;grid-template-columns:repeat(5,65px);gap:14px}
.essay .coin{width:65px;height:65px;border-radius:50%;background:#d9ba6b;border:3px solid #ac8943;box-shadow:inset 0 0 0 5px #eedbaa;display:flex;align-items:center;justify-content:center;font-size:27px;color:#775626}
.essay .coin.lost{opacity:.16}
.essay .value-note{position:absolute;left:105px;top:836px;font-size:25px;color:#5a675f}
.essay.clean{background:#f4f0e4;color:#202724}
.essay.clean .eyebrow{left:150px;top:110px;font-size:28px;letter-spacing:2px}
.essay.clean .record{left:150px;top:250px;width:1600px}
.essay.clean .date{font-size:36px;margin-bottom:45px}
.essay.clean .quote{font-size:82px;line-height:1.6;max-width:1560px}
.essay.clean .marker{width:840px;height:8px;background:#ae3d2f;margin-top:26px}
.essay.clean .credit{left:150px;top:815px;font-size:27px}
.essay.clean .question-copy{left:150px;top:300px;width:1620px;color:#202724;font-size:106px;line-height:1.5}
.essay.clean .question-small{left:155px;top:710px;font-size:38px;color:#536663}
.essay.clean .title{left:150px;top:110px;font-size:44px;color:#536663}
.essay.clean .price-zone{left:220px;top:280px;width:600px}
.essay.clean .cash-zone{left:1090px;top:280px;width:620px}
.essay.clean .label{font-size:42px;color:#536663;margin-bottom:35px}
.essay.clean .number{font-size:200px;font-weight:550;color:#202724;letter-spacing:-4px}
.essay.clean .number small{font-size:48px;margin-left:18px}
.essay.clean .old-price{height:60px;font-size:34px}
.essay.clean .divider{position:absolute;left:950px;top:300px;width:2px;height:320px;background:#c7c8ba}
.essay.clean .rate{left:220px;top:710px;width:1490px;padding:0;background:transparent;border:0;font-size:56px;color:#ae3d2f}
.essay.clean .value-note{left:220px;top:830px;font-size:28px}
'''

GLYPHS='个人投资复盘原文节选排版本期判断同一家公司假设示例买下这份股权每年可分配的收入买入价格每年收入原价原来持续元0123456789%÷=→'

VARIANTS={'record','question','business','valuation','risk','closing'}

def validate(s,text,sources):
    if s.get('layout')=='paper-animation':
        from . import paper_animation
        return paper_animation.validate(s,text,sources)
    if s.get('layout')=='motion':
        from .motion_essay import validate as validate_motion
        return validate_motion(s,text,sources)
    require(s.get('variant') in VARIANTS,'essay_scene variant 无效')
    require(s.get('layout','photo') in {'photo','clean'},'essay_scene layout 无效')
    if s.get('layout') == 'clean':
        require(not s.get('asset'),'clean 布局不接收装饰图片；需要摄影时使用 photo 布局')
        require(not any(e.get('target') in {'photo','coins'} for e in s.get('events',[])), 'clean 布局不支持照片或金币动作')
    else:
        require(bool(s.get('asset')) and bool(s.get('provenance')),'essay_scene 需要实际摄影素材')
    require(isinstance(s.get('headline'),str) and 0<len(s['headline'])<=38,'essay_scene headline 过长')
    require(isinstance(s.get('credit'),str) and len(s['credit'])<=100,'essay_scene 需要简短来源')
    if s.get('headline_lines'):
        require(isinstance(s['headline_lines'],list) and all(isinstance(x,str) and x for x in s['headline_lines']) and ''.join(s['headline_lines'])==s['headline'],'headline_lines须完整保留标题')
    if s['variant'] in {'record','closing'}:
        require(s.get('source_id') in sources and bool(s.get('record_date')),'个人记录需要来源与历史日期')
        require(isinstance(s.get('quote'),str) and 0<len(s['quote'])<=80,'个人原文节选须不超过80字')
        if s.get('quote_lines'):
            require(isinstance(s['quote_lines'],list) and all(isinstance(x,str) and x for x in s['quote_lines']) and ''.join(s['quote_lines'])==s['quote'], 'quote_lines须完整保留原文节选')
    if s['variant'] in {'business','valuation','risk'}:
        require(s.get('hypothetical') is True,'价格收入例子必须明确为假设')
        number(s.get('price'),1,100000,'price');number(s.get('income'),1,10000,'income')
        require(s['income'] == (5 if s['variant']=='risk' else 10),'当前金币示意只支持正常收入10元、风险收入5元')
        if s.get('previous_price') is not None:number(s['previous_price'],1,100000,'previous_price')
        if s.get('previous_income') is not None:number(s['previous_income'],1,10000,'previous_income')
        if s.get('previous_comparison') is not None:
            require(isinstance(s['previous_comparison'],str) and 0<len(s['previous_comparison'])<=60,'previous_comparison须为简短说明')
    for e in s.get('events',[]):
        require(e.get('action') in {'mark','focus','reveal'} and e.get('target') in {'photo','marker','price','income','rate','coins'},'essay_scene 动作无效')
        cue=e.get('cue','');require(isinstance(cue,str) and (not cue or text.count(normalize(cue))==1),'essay_scene cue须唯一')
        number(e.get('duration',.4),.1,1.5,'essay.duration')

def render(s,media,assets):
    if s.get('layout')=='paper-animation':
        from . import paper_animation
        return paper_animation.render(s,media,assets)
    if s.get('layout')=='motion':
        from .motion_essay import render as render_motion
        return render_motion(s)
    if s.get('layout') == 'clean':
        return render_clean(s)
    sid=s['id'];esc=html.escape;at=s['start'];length=s['end']-at;src=freeze(media,assets[sid],sid)
    variant=s['variant'];body='<div class="essay">';motion=[]
    if variant in {'record','closing'}:
        body+=f'<div class="eyebrow">个人投资复盘 · 原文节选排版</div><div class="rule"></div><div class="record"><div class="date">{esc(s["record_date"])}</div><p class="quote">{esc(s["quote"])}</p><div id="{sid}-marker" class="marker"></div><div class="subline">{esc(s.get("subline",""))}</div></div><div class="photo-frame"><img id="{sid}-photo" class="photo" src="{src}"/></div><div class="credit">{esc(s["credit"])}</div>'
        motion.append(f'tl.fromTo("#{sid}-marker",{{scaleX:0}},{{scaleX:0,duration:.01}},{at});')
    elif variant=='question':
        title=''.join('<div>'+esc(x)+'</div>' for x in s.get('headline_lines',[s['headline']]))
        body+=f'<img id="{sid}-photo" class="full-photo" src="{src}"/><div class="shade"></div><div class="eyebrow" style="color:#d5c8a7">{esc(s.get("record_date","本期判断"))}</div><div class="question-copy">{title}</div><div class="question-small">{esc(s.get("subline",""))}</div><div class="credit" style="color:#e2dbca">{esc(s["credit"])}</div>'
    else:
        price=s['price'];income=s['income'];risk=variant=='risk';old=s.get('previous_price')
        body+=f'<div class="title">{esc(s["headline"])}</div><div class="rule" style="top:159px"></div><div class="company"><img id="{sid}-photo" class="photo" src="{src}"/></div><div class="company-label">同一家公司 · 假设示例</div>'
        oldtext=f'原价 {old:g}' if old else ''
        body+=f'<div id="{sid}-price" class="price-zone"><div class="label">买下这份股权</div><div class="old-price">{oldtext}</div><div class="number">{price:g}<small>元</small></div></div>'
        body+=f'<div id="{sid}-income" class="cash-zone"><div class="label">每年可分配的收入</div><div class="old-price">{"原来 10 元" if risk else "假设持续"}</div><div class="number" style="color:{"#a44f3b" if risk else "#153e3a"}">{income:g}<small>元</small></div></div>'
        if old and any(e['action']=='reveal' and e['target']=='price' for e in s.get('events',[])):
            body+=f'<div id="{sid}-price-before" class="price-zone"><div class="label">买下这份股权</div><div class="old-price"></div><div class="number">{old:g}<small>元</small></div></div>'
            change=next(e['at'] for e in s['events'] if e['action']=='reveal' and e['target']=='price')
            motion.append(f'tl.fromTo("#{sid}-price-before",{{opacity:1}},{{opacity:0,duration:.15}},{change});')
        coins=''.join(f'<div class="coin{" lost" if risk and i>=5 else ""}">1</div>' for i in range(10))
        body+=f'<div id="{sid}-coins" class="coin-row">{coins}</div><div id="{sid}-rate" class="rate">{esc(s.get("comparison",f"{income:g} ÷ {price:g} = {income/price*100:g}%"))}</div><div class="value-note">{esc(s["note"])}</div>'
    body+='</div>'
    # Restrained photo drift supplies depth; meaningful state changes follow measured words.
    if variant in {'record','closing','question'}:
        motion.append(f'tl.fromTo("#{sid}-photo",{{scale:1}},{{scale:1.025,duration:{length},ease:"none"}},{at});')
    for e in s.get('events',[]):
        target=f'#{sid}-{e["target"]}';t=e['at'];d=e.get('duration',.4)
        if e['action']=='mark':motion.append(f'tl.fromTo("{target}",{{scaleX:0}},{{scaleX:1,duration:{d},ease:"power2.out",immediateRender:false}},{t});')
        elif e['action']=='reveal':motion.append(f'tl.fromTo("{target}",{{opacity:0,y:16}},{{opacity:1,y:0,duration:{d},ease:"power2.out"}},{t});')
        else:motion.append(f'tl.fromTo("{target}",{{scale:1}},{{scale:1.06,duration:{d},ease:"power2.out",immediateRender:false}},{t});')
    return body,motion


def render_clean(s):
    """Evidence and aligned numerical changes without decorative stock media."""
    sid=s['id'];esc=html.escape;at=s['start'];variant=s['variant'];motion=[]
    body='<div class="essay clean">'
    if variant in {'record','closing'}:
        quote=''.join(f'<span style="display:block">{esc(line)}</span>' for line in s.get('quote_lines',[s['quote']]))
        body+=f'<div class="eyebrow">个人投资复盘 · 原文节选排版</div><div class="record"><div class="date">{esc(s["record_date"])}</div><p class="quote">{quote}</p><div id="{sid}-marker" class="marker"></div></div><div class="credit">{esc(s["credit"])}</div>'
        motion.append(f'tl.fromTo("#{sid}-marker",{{scaleX:0}},{{scaleX:0,duration:.01}},{at});')
    elif variant=='question':
        title=''.join('<div>'+esc(x)+'</div>' for x in s.get('headline_lines',[s['headline']]))
        body+=f'<div class="question-copy">{title}</div>'
        if s.get('subline'):body+=f'<div class="question-small">{esc(s["subline"])}</div>'
    else:
        body+=f'<div class="title">{esc(s["headline"])}</div><div class="divider"></div>'
        for target,zone,label,value,old in [('price','price-zone','买入价格',s['price'],s.get('previous_price')),('income','cash-zone','每年收入',s['income'],s.get('previous_income'))]:
            oldtext=f'原来 {old:g} 元' if old else ''
            body+=f'<div id="{sid}-{target}" class="{zone}"><div class="label">{label}</div><div class="old-price">{oldtext}</div><div class="number">{value:g}<small>元</small></div></div>'
            reveal=next((e for e in s.get('events',[]) if e['action']=='reveal' and e['target']==target),None)
            if old is not None and reveal:
                body+=f'<div id="{sid}-{target}-before" class="{zone}"><div class="label">{label}</div><div class="old-price"></div><div class="number">{old:g}<small>元</small></div></div>'
                motion.append(f'tl.fromTo("#{sid}-{target}-before",{{opacity:1}},{{opacity:0,duration:.15}},{reveal["at"]});')
        body+=f'<div id="{sid}-rate" class="rate">{esc(s.get("comparison",""))}</div><div class="value-note">{esc(s["note"])}</div>'
        previous=s.get('previous_comparison')
        reveal=next((e for e in s.get('events',[]) if e['action']=='reveal' and e['target']=='rate'),None)
        if previous and reveal:
            body+=f'<div id="{sid}-rate-before" class="rate">{esc(previous)}</div>'
            motion.append(f'tl.fromTo("#{sid}-rate-before",{{opacity:1}},{{opacity:0,duration:.25}},{reveal["at"]});')
    for e in s.get('events',[]):
        target=f'#{sid}-{e["target"]}';t=e['at'];d=e.get('duration',.35)
        if e['action']=='mark':motion.append(f'tl.fromTo("{target}",{{scaleX:0}},{{scaleX:1,duration:{d},ease:"power2.out",immediateRender:false}},{t});')
        elif e['action']=='reveal':motion.append(f'tl.fromTo("{target}",{{opacity:0}},{{opacity:1,duration:{d},ease:"power2.out"}},{t});')
        else:motion.append(f'tl.fromTo("{target}",{{color:"#202724"}},{{color:"#ae3d2f",duration:{d},ease:"power2.out",immediateRender:false}},{t});')
    return body+'</div>',motion
