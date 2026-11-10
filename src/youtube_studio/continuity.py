"""Persistent, voice-anchored shop objects across narration unit boundaries.

A deliberately scoped mechanism scene, not a generic slide DSL. Customers and
copied objects preserve their identities; every event is reversible under seek.
"""
import html
import json

from .core import require

ACTIONS = {'establish', 'rival', 'demand', 'profitable', 'entry', 'capacity',
           'pressure', 'focus', 'claim', 'product', 'imitate', 'systems', 'talent',
           'management', 'copy', 'question'}
GLYPHS = '手中的小票代表订单原店隔壁新店新进入者同一批顾客订单利润承压扩产做得好还要守得住什么难以复制特色服务制度人才管理情境实拍假设街区总需求不变单价和成本条件不变可模仿的优势'
CSS = """
.continuous .caption span{background:#202724;color:#fff;border-radius:0}
.footage-panel{position:absolute;left:0;top:0;width:1920px;height:1080px;object-fit:cover}
.film-shade{position:absolute;inset:0;background:linear-gradient(0deg,rgba(9,16,19,.80),transparent 24%),linear-gradient(165deg,rgba(12,20,24,.65),transparent 45%)}
.film-annotation{position:absolute;top:135px;left:115px;max-width:1350px;white-space:pre-line;color:#fff9e9;font-size:66px;font-weight:600;line-height:1.32;text-shadow:0 2px 7px #101819,0 1px 22px #101819}
.film-annotation.paired{left:0;width:1920px;max-width:none;display:grid;grid-template-columns:1fr 1fr;text-align:center}
.film-credit{position:absolute;top:48px;right:65px;font-size:24px;color:white;text-shadow:0 1px 5px #102124,0 0 9px #102124}
.caption.on-film span{background:transparent;color:white;text-shadow:0 2px 5px #111,0 1px 12px #111}
.footage-question{position:absolute;right:120px;top:120px;font-size:72px;font-weight:700;background:#f4f0e4;padding:18px 30px}
.footage-credit{position:absolute;left:120px;top:824px;font-size:24px;color:#53594e;background:#f4f0e4;padding:8px 16px}
.street-layer{position:absolute;inset:0;width:1920px;height:1080px;overflow:hidden}
.street-world{position:absolute;inset:0;width:1920px;height:1080px;transform-origin:0 0}
.street-ground{position:absolute;left:120px;top:620px;width:1680px;height:3px;background:#aaa696}
.street-building{position:absolute;top:340px;width:360px;height:280px;transform-origin:50% 100%}
.street-wall{position:absolute;top:64px;left:0;width:360px;height:216px;background:#e4dfcf;border:3px solid #202724}
.street-awning{position:absolute;left:-8px;top:45px;width:376px;height:50px;background:repeating-linear-gradient(90deg,#2c5953 0,#2c5953 47px,#f4f0e4 47px,#f4f0e4 94px);border:3px solid #202724}
.street-building.rival .street-awning{background:repeating-linear-gradient(90deg,#ae3d2f 0,#ae3d2f 47px,#f4f0e4 47px,#f4f0e4 94px)}
.street-window{position:absolute;left:24px;top:122px;width:192px;height:130px;background:#bdcec5;border:3px solid #202724}
.street-door{position:absolute;left:251px;top:122px;width:83px;height:158px;background:#faf7ee;border:3px solid #202724}
.street-name{position:absolute;left:0;top:-16px;width:360px;text-align:center;font-size:38px;font-weight:700}
.street-person{position:absolute;left:0;top:0;width:38px;height:70px;color:#2c5953}
.street-person svg{width:38px;height:70px}
.street-queue{position:absolute;left:0;top:0;width:1920px;height:1080px}
.street-order{position:absolute;left:24px;top:37px;width:18px;height:22px;background:#f3ce78;border:2px solid #202724}
.street-demand-note{position:absolute;left:150px;top:210px;font-size:34px;color:#53594e}
.street-condition{position:absolute;left:120px;top:850px;font-size:26px;color:#53594e}
.street-message{position:absolute;left:150px;top:128px;width:1620px;font-size:69px;line-height:1.35;font-weight:700}
.street-message strong{color:#ae3d2f;font-weight:700}
.street-flag{position:absolute;left:32px;top:105px;background:#202724;color:#fff;padding:10px 20px;font-size:29px}
.street-capacity{position:absolute;left:360px;top:95px;width:100px;height:185px;background:#bdcec5;border:3px solid #202724}
.street-product{position:absolute;left:47px;top:139px;width:145px;height:98px;text-align:center;background:#faf7ee;border:2px solid #202724;padding:6px;font-size:22px}
.street-cup{width:40px;height:34px;border:3px solid #202724;border-radius:0 0 12px 12px;margin:0 auto 6px;background:#ddb05b;position:relative}
.street-cup:after{content:'';position:absolute;right:-13px;top:4px;width:10px;height:15px;border:3px solid #202724;border-left:0;border-radius:0 8px 8px 0}
.street-feature{position:absolute;left:0;top:305px;width:112px;padding:8px 0;text-align:center;background:#e5ddca;font-size:26px;border-bottom:3px solid #2c5953}
.street-feature.copy{border-color:#ae3d2f}
.street-copy-line{position:absolute;left:645px;top:472px;width:135px;height:3px;background:#ae3d2f;transform-origin:left}
.street-copy-line:after{content:'';position:absolute;right:0;top:-5px;width:12px;height:12px;border-right:3px solid #ae3d2f;border-top:3px solid #ae3d2f;transform:rotate(45deg)}
"""


def render(shots):
    """One DOM world for one contiguous shop sequence, even over multiple units."""
    require(shots and all(s['scene'] == 'shop-competition/v1' for s in shots), '不支持的连续场景')
    require(all(abs(a['end']-b['start']) < .001 for a,b in zip(shots,shots[1:])), '连续场景不能被其他镜头打断')
    events = [e for s in shots for e in s['events']]
    names = [e['action'] for e in events]
    require(len(names) == len(set(names)), '同一连续场景动作不得重复')
    required = ['establish','rival','demand','profitable','entry','capacity','pressure','focus','claim','product','imitate','systems','talent','management','copy','question']
    require(names == required, 'shop-competition/v1 需要完整、有序的进入—分流—复制事件')
    at = {e['action']:e['at'] for e in events}
    start, end = shots[0]['start'], shots[-1]['end']
    require(at['question']+1.2 <= end, '结尾问题至少留 1.2 秒')
    tween = []
    def ft(selector, before, after, when, duration=.6):
        tween.append(f'tl.fromTo({json.dumps(selector)},{json.dumps(before)},{json.dumps(dict(after,duration=duration,ease="power2.inOut",immediateRender=False))},{when});')
    def enter(selector, when, x=0, y=0, duration=.6):
        ft(selector,dict(opacity=0,x=x,y=y),dict(opacity=1,x=0,y=0),when,duration)
    def hide(selector, when, duration=.35):
        ft(selector,dict(opacity=1),dict(opacity=0),when,duration)
    body = '<div class="street-world" id="street-world"><div class="street-ground"></div>'
    for i,label in enumerate(['原店','隔壁新店','新进入者']):
        body += f'<div id="street-shop-{i}" class="street-building {"rival" if i else ""}" style="left:{260+i*540}px;opacity:0"><div class="street-wall"></div><div class="street-window"></div><div class="street-door"></div><div class="street-awning"></div><div class="street-name">{label}</div>'
        if i == 0:
            body += '<div id="street-profit" class="street-flag" style="opacity:0">订单</div><div id="street-pressure" class="street-flag" style="opacity:0">利润承压</div>'
        if i == 1:
            body += '<div id="street-capacity" class="street-capacity" style="opacity:0"></div><div id="street-expand" class="street-flag" style="opacity:0">扩产</div>'
        if i < 2:
            body += f'<div id="street-product-{i}" class="street-product" style="opacity:0"><div class="street-cup"></div>特色服务</div>'
            for n,feature in enumerate(['制度','人才','管理']):
                body += f'<div id="street-feature-{i}-{n}" class="street-feature {"copy" if i else ""}" style="left:{n*124}px;opacity:0">{feature}</div>'
        body += '</div>'
    body += '<div id="street-queue" class="street-queue">'
    for i in range(12):
        x,y = 280+(i%6)*54,690+(i//6)*85
        body += f'<div id="street-customer-{i}" class="street-person" style="left:{x}px;top:{y}px;opacity:0"><svg viewBox="0 0 38 70" aria-label="顾客"><circle cx="17" cy="10" r="9" fill="currentColor"/><path d="M7 66V28Q7 22 17 22Q27 22 27 28V66M4 48V29M31 48V29" stroke="currentColor" stroke-width="7" fill="none"/></svg><div class="street-order"></div></div>'
        enter(f'#street-customer-{i}', at['demand']+(i%6)*.055, y=25,duration=.45)
        # Same people move. Total count is fixed; no new demand is fabricated.
        if i >= 4:
            dest = 1 if i < 8 else 2
            j = i-4 if dest == 1 else i-8
            target_x = 820+(dest-1)*540+j*54
            target_y = 720
            when = at['entry']+.6 if dest == 2 else at['capacity']+.4
            ft(f'#street-customer-{i}',dict(x=0,y=0),dict(x=target_x-x,y=target_y-y),when+(j*.09),1.15)
    body += '</div><div id="street-demand-note" class="street-demand-note" style="opacity:0">同一批顾客 · 手中的小票代表订单</div><div id="street-copy-line" class="street-copy-line" style="opacity:0"></div></div>'
    body += '<div id="street-question-start" class="street-message" style="opacity:0">隔壁，也能开一家？</div><div id="street-claim" class="street-message" style="opacity:0">做得好，<strong>还要守得住。</strong></div><div id="street-question-end" class="street-message" style="opacity:0">什么，<strong>难以复制？</strong></div>'
    # Conditions switch with the explanation; remain visible and are not a page footer stack.
    for i,s in enumerate(shots):
        body += f'<div id="street-condition-{i}" class="street-condition" style="opacity:0">{html.escape(s["note"])}</div>'
        enter(f'#street-condition-{i}',s['start'],duration=.25)
        if i < len(shots)-1: hide(f'#street-condition-{i}',s['end']-.2,duration=.2)
    enter('#street-shop-0',start,y=24)
    enter('#street-shop-1',at['rival'],x=100)
    enter('#street-shop-2',at['entry'],x=100)
    enter('#street-question-start',start,y=-15)
    hide('#street-question-start',at['demand']-.3)
    enter('#street-demand-note',at['demand'])
    enter('#street-profit',at['profitable'])
    enter('#street-capacity',at['capacity'],y=-30)
    enter('#street-expand',at['capacity'])
    hide('#street-profit',at['pressure'])
    enter('#street-pressure',at['pressure'],y=-15)
    hide('#street-expand',at['focus'])
    hide('#street-pressure',at['focus'])
    hide('#street-shop-2',at['focus'])
    hide('#street-queue',at['focus'])
    hide('#street-demand-note',at['focus'])
    ft('#street-world',dict(x=0,y=0,scale=1),dict(x=-60,y=-30,scale=1.12),at['focus'],1.0)
    enter('#street-claim',at['claim'],x=-30)
    hide('#street-claim',at['product']-.25)
    enter('#street-product-0',at['product'],y=20)
    # First copy physically travels from the original shop to its competitor.
    enter('#street-product-1',at['imitate'],x=-540,duration=.85)
    enter('#street-copy-line',at['imitate'],duration=.25)
    hide('#street-copy-line',at['imitate']+1.0)
    for n,key in enumerate(['systems','talent','management']):
        enter(f'#street-feature-0-{n}',at[key],y=10,duration=.3)
        # Preserve row spacing while copying through a separate lower lane.
        # Independent straight-line staggers cross other words at the source.
        target = f'#street-feature-1-{n}'
        ft(target,dict(opacity=0,x=-540,y=0),dict(opacity=1,x=-540,y=65),at['copy'],.15)
        ft(target,dict(x=-540,y=65),dict(x=0,y=65),at['copy']+.15,.65)
        ft(target,dict(y=65),dict(y=0),at['copy']+.8,.18)
    enter('#street-question-end',at['question'],y=-12,duration=.45)
    return f'<section id="street" class="clip street-layer" data-start="{start}" data-duration="{end-start}" data-track-index="50"><div class="canvas">{body}</div></section>', tween
