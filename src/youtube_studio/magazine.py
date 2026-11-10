"""Magazine layouts: photographic context and voice-anchored mechanism diagrams."""
import html
import json
import shutil
from .text_motion import headline

CSS = """
.magazine{color:#202724}
.magazine .question{border:0;border-radius:0;background:transparent;padding:0;left:120px;top:135px;font-weight:700;font-size:66px;max-width:1660px}
.magazine .headline{left:170px;top:320px;width:1580px;font-size:94px;text-align:left;line-height:1.5}
.magazine .claim-mark{background:#ae3d2f;height:9px}
.magazine .note{left:120px;bottom:160px;padding:0;border-radius:0;background:#f4f0e4;font-size:27px;color:#53594e}
.magazine .caption span{border-radius:0;background:#202724;color:#fff;padding:12px 28px}
.mast{position:absolute;left:120px;right:120px;top:62px;border-bottom:2px solid #202724;padding-bottom:18px;font-size:24px;letter-spacing:4px}
.folio{float:right;letter-spacing:1px}
.photo-panel{position:absolute;overflow:hidden;background:#ddd4c1}
.photo-panel img{width:100%;height:100%;object-fit:cover}
.hero-photo{left:1050px;top:165px;width:690px;height:620px}
.hero-copy{position:absolute;left:120px;top:225px;width:820px;font-size:82px;font-weight:700;line-height:1.4}
.hero-deck{position:absolute;left:125px;top:600px;width:760px;font-size:36px;line-height:1.6;border-left:7px solid #ae3d2f;padding-left:24px}
.photo-credit{position:absolute;left:120px;top:857px;font-size:20px;color:#53594e}
.photo-label{position:absolute;left:0;bottom:0;padding:16px 28px;background:#202724;color:#fff;font-size:38px}
.duo-photo{top:315px;width:740px;height:465px}
.duo-left{left:120px}.duo-right{left:1040px}
.vs{position:absolute;left:900px;top:505px;font-size:56px;color:#ae3d2f}
.mechanism-stage{position:absolute;left:120px;top:315px;width:1660px;height:460px}
.shop-object{position:absolute;top:30px;width:260px;height:330px}.shop{position:absolute;top:0;width:240px;height:220px;border:4px solid #202724;background:#e6dfd0;transform-origin:bottom center}
.awning{position:absolute;left:-4px;right:-4px;top:-4px;height:45px;background:repeating-linear-gradient(90deg,#ae3d2f 0px,#ae3d2f 30px,#f4f0e4 30px,#f4f0e4 60px);border:4px solid #202724}
.shop-window{position:absolute;left:20px;top:70px;width:110px;height:110px;background:#b6c7c0;border:3px solid #202724}
.shop-door{position:absolute;right:20px;top:70px;width:60px;height:146px;border:3px solid #202724;background:#faf7ef}
.shop-tag{position:absolute;top:265px;width:260px;font-size:30px;text-align:center}
.pressure{position:absolute;left:1190px;top:25px;width:400px;height:360px;border-left:2px solid #202724;padding-left:50px}
.pressure-title{font-size:33px}.pressure-track{position:absolute;left:52px;top:85px;width:290px;height:190px;background:#ddd7c9}
.pressure-fill{width:290px;height:190px;background:#ae3d2f;transform-origin:bottom}
.pressure-note{position:absolute;top:295px;font-size:28px}
.stage-label{position:absolute;top:415px;font-size:36px;font-weight:600;color:#933628}
.race-row{position:absolute;left:0;width:1660px;height:145px}
.race-name{position:absolute;top:25px;left:0;font-size:40px;width:280px}
.race-track{position:absolute;left:330px;top:30px;width:1250px;height:65px;background:#ded8cb}
.race-fill{width:1250px;height:65px;background:#202724;transform-origin:left}
.race-row.second .race-fill{background:#ae3d2f}
.race-features{position:absolute;left:330px;top:110px;font-size:29px;color:#53594e}
"""


def render_shot(s, media, assets):
    esc = lambda text: html.escape(str(text), quote=True)
    sid, start, end = s['id'], s['start'], s['end']
    body, tweens = '', []
    times = s.get('label_times', [])
    def reveal(selector, at, x=0):
        tweens.append(f'tl.fromTo("{selector}",{{opacity:0,x:{x},y:16}},{{opacity:1,x:0,y:0,duration:.4,ease:"power2.out"}},{at});')
    if s['kind'] == 'collage':
        src = assets[sid]
        name = sid + src.suffix.lower()
        shutil.copy2(src, media / name)
        if s.get('layout', 'hero') == 'hero':
            title, motion = headline(s, "hero-copy")
            body += title + f'<div id="{sid}-deck" class="hero-deck">{esc(s.get("deck", ""))}</div>'
            tweens.extend(motion)
            reveal(f'#{sid}-deck', min(start+.9, end-.65), -24)
            body += f'<div class="photo-panel hero-photo"><img id="{sid}-photo" src="media/{name}" /></div>'
            # A bounded push follows the subject; typography stays still.
            tweens.append(f'tl.fromTo("#{sid}-photo",{{scale:1}},{{scale:1.035,duration:{end-start},ease:"none"}},{start});')
        else:
            title, motion = headline(s, "question")
            body += title + '<div class="vs">/</div>'
            tweens.extend(motion)
            for n, label in enumerate(s['labels']):
                current = name
                if n and s.get('secondary_asset'):
                    secondary = assets[sid+'-secondary']
                    current = sid+'-secondary'+secondary.suffix.lower()
                    shutil.copy2(secondary, media / current)
                body += f'<div id="{sid}-label-{n}" class="photo-panel duo-photo duo-{"left" if n==0 else "right"}"><img src="media/{current}" style="object-position:50% 70%"/><div class="photo-label">{esc(label)}</div></div>'
                reveal(f'#{sid}-label-{n}', times[n], 30 if n else -30)
        if s.get('show_credit', True):
            body += f'<div class="photo-credit">{esc(s["credit"])}</div>'
    else:
        title, motion = headline(s, "question")
        body += title + '<div class="mechanism-stage">'
        tweens.extend(motion)
        if s['variant'] == 'competition':
            for n, label in enumerate(['原有店铺','新进入者','新增供给']):
                body += f'<div id="{sid}-object-{n}" class="shop-object" style="left:{n*350}px"><div class="shop"><div class="awning"></div><div class="shop-window"></div><div class="shop-door"></div></div><div class="shop-tag">{label}</div></div>'
                if n:
                    reveal(f'#{sid}-object-{n}', times[n-1], 45)
            body += f'<div class="pressure"><div class="pressure-title">利润空间</div><div class="pressure-track"><div id="{sid}-pressure" class="pressure-fill"></div></div><div class="pressure-note">方向示意 · 无量纲</div></div>'
            tweens.append(f'tl.fromTo("#{sid}-pressure",{{scaleY:1}},{{scaleY:.38,duration:.8,ease:"power2.inOut"}},{times[2]});')
        else:
            for n, label in enumerate(['当前领先者','竞争对手']):
                body += f'<div id="{sid}-row-{n}" class="race-row {"second" if n else ""}" style="top:{n*200}px"><div class="race-name">{label}</div><div class="race-track"><div id="{sid}-bar-{n}" class="race-fill"></div></div><div class="race-features">{esc(s["features"])}</div></div>'
                reveal(f'#{sid}-row-{n}', times[n], -30)
                reveal(f'#{sid}-row-{n} .race-features', times[2], 20)
            tweens.append(f'tl.set("#{sid}-bar-0",{{scaleX:.85}},0);tl.fromTo("#{sid}-bar-1",{{scaleX:.25}},{{scaleX:.85,duration:{min(2,end-times[2]-.3)},ease:"power2.inOut"}},{times[2]});')
        for n, label in enumerate(s['labels']):
            body += f'<div id="{sid}-label-{n}" class="stage-label" style="left:{n*550}px">{esc(label)}</div>'
            reveal(f'#{sid}-label-{n}', times[n])
        body += '</div>'
    return body, tweens
