"""Duration-proportional navigation and a photographic chapter title card."""
import html
import shutil
from pathlib import Path

from .core import require

CSS = """
.chapter-nav{position:absolute;top:0;left:0;width:1920px;height:76px;background:#eee7d8;z-index:1200;padding:0 80px;display:flex;gap:5px}
.chapter-section{height:76px;position:relative;flex-shrink:0;overflow:hidden;color:#353b31}
.chapter-label{position:absolute;left:0;top:20px;width:100%;font-size:24px;line-height:36px;white-space:nowrap;text-align:center;opacity:.85}
.chapter-label.stacked{top:6px;line-height:30px;white-space:pre-line}
.chapter-nav.excerpt-nav{height:58px;background:#e9ece6}
.excerpt-nav .chapter-section{height:58px}
.excerpt-nav .chapter-label{top:10px}
.excerpt-nav .chapter-label.stacked{top:1px;line-height:26px}
.chapter-track{position:absolute;bottom:0;left:0;width:100%;height:4px;background:#d8cfbd}
.chapter-progress{height:100%;width:100%;background:#9c733b;transform-origin:left center}
.cover-title{position:absolute;left:140px;top:220px;color:#27342c;font-size:142px;font-weight:700;letter-spacing:4px;line-height:1.2;white-space:pre-line}
.cover-subtitle{position:absolute;left:147px;top:410px;color:#27342c;font-size:48px;border-left:5px solid #9c682d;padding-left:25px;line-height:1.4}
"""


def chapter_times(doc, units):
    chapters = doc.get('narrative', {}).get('chapters', [])
    if not chapters:
        return []
    require([uid for c in chapters for uid in c['units']] == [u['id'] for u in units],
            '导航章节须连续、按序覆盖全部口播单元')
    by_id = {u['id']: u for u in units}
    return [dict(id=c['id'], label=c.get('nav_label', c['question']),
                 start=by_id[c['units'][0]]['start'], end=by_id[c['units'][-1]]['end']) for c in chapters]


def navigation(chapters, duration, visible_start=0, upcoming=(), visible_end=None):
    require(chapters and duration > 0, '导航需要已测量的章节时间')
    require(all(isinstance(label, str) and 0 < len(label) <= 8 for label in upcoming), '后续章节需要短标题')
    future_widths = [max(165, len(label)*24+74) for label in upcoming]
    available = 1760 - 5 * (len(chapters)+len(upcoming)-1) - sum(future_widths)
    fragments, motion = [], []
    for n, c in enumerate(chapters):
        span = c['end'] - c['start']
        width = available * span / duration
        font_size = 24
        compact = width < len(c['label']) * font_size + 72
        if compact:
            font_size = max(20,min(font_size,int((width-12)/max(1,len(c['label'])))))
        label = f'{n+1:02d}\n{c["label"]}' if compact else f'{n+1:02d} · {c["label"]}'
        # Keep every ordinal. A genuinely short section stacks its label;
        # neither its measured share nor the chapter identity is discarded.
        required = len(c['label']) * font_size + (12 if compact else 72)
        require(width >= required and len(c['label']) <= 8, '导航标题放不下，请缩短标题')
        pid = f'chapter-{n}'
        fragments.append(f'<div class="chapter-section" data-chapter-start="{c["start"]}" data-chapter-end="{c["end"]}" style="width:{width:.6f}px"><span id="{pid}-label" class="chapter-label{" stacked" if compact else ""}" style="font-size:{font_size}px">{html.escape(label)}</span><div class="chapter-track"><div id="{pid}-progress" class="chapter-progress"></div></div></div>')
        motion += [f'tl.fromTo("#{pid}-progress",{{scaleX:0}},{{scaleX:1,duration:{span},ease:"none"}},{c["start"]});',
                   f'tl.set("#{pid}-label",{{opacity:1,color:"#875e29"}},{c["start"]});',
                   f'tl.set("#{pid}-label",{{opacity:.8,color:"#353b31"}},{c["end"]});']
    for n,(label,width) in enumerate(zip(upcoming,future_widths),len(chapters)+1):
        fragments.append(f'<div class="chapter-section" style="width:{width}px;color:#777b75"><span class="chapter-label">{n:02d} · {html.escape(label)}</span><div class="chapter-track"></div></div>')
    style = ' excerpt-nav' if upcoming else ''
    return f'<nav id="chapter-nav" class="clip chapter-nav{style}" data-start="{visible_start}" data-duration="{(duration if visible_end is None else visible_end)-visible_start}" data-track-index="1200">'+''.join(fragments)+'</nav>', motion


def stamp(t):
    seconds = int(t)
    return f'{seconds//60:02}:{seconds%60:02}'


def cover(s, chapters, media, asset):
    name = s['id'] + Path(asset).suffix.lower()
    shutil.copy2(asset, media/name)
    sid = s['id']
    body = f'<img id="{sid}-art" class="art" src="media/{name}"/>'
    placement = ' style="left:108px;top:288px;color:#fff9eb;font-size:122px;line-height:1.23;text-shadow:0 2px 18px #14171280"' if s.get('title_style') == 'photo-left' else ''
    if s.get('title_style') == 'photo-left-light':
        placement = ' style="left:98px;top:280px;color:#263831;font-size:112px;line-height:1.23"'
    body += f'<div id="{sid}-title" class="cover-title"{placement}>{html.escape(s["headline"])}</div>'
    subtitle = s.get('subtitle', '').strip()
    if subtitle:
        subtitle_top = 410 + 142 * 1.2 * (len(s['headline'].splitlines()) - 1)
        body += f'<div id="{sid}-subtitle" class="cover-subtitle" style="top:{subtitle_top:g}px">{html.escape(subtitle)}</div>'
    motion = [f'tl.fromTo("#{sid}-art",{{scale:1}},{{scale:1.035,duration:{s["end"]-s["start"]},ease:"none"}},{s["start"]});']
    start = s['start']
    title_delay = .12
    if s.get('intro_ink'):
        body += f'<svg aria-hidden="true" width="1920" height="1080" style="position:absolute;inset:0;pointer-events:none"><path id="{sid}-ink" d="M 329 315 C 278 268 94 278 74 352 S 269 476 341 396 Q 378 340 325 307" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1" fill="none" stroke="#934916" stroke-width="4"/></svg>'
        motion.append(f'tl.fromTo("#{sid}-ink",{{attr:{{"stroke-dashoffset":1}}}},{{attr:{{"stroke-dashoffset":0}},duration:1.15,ease:"sine.inOut"}},{start+.22});')
        title_delay = .62
    for sel, delay in [('title',title_delay)] + ([('subtitle',.3)] if subtitle else []):
        motion.append(f'tl.fromTo("#{sid}-{sel}",{{opacity:0,y:20}},{{opacity:1,y:0,duration:.65,ease:"power2.out"}},{s["start"]+delay});')
    return body,motion


def player_page(directory, chapters, movie='output.mp4', title='视频'):
    buttons = ''.join(f'<button data-at="{c["start"]}"><span>{stamp(c["start"])}</span>{html.escape(c["label"])}</button>' for c in chapters)
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DOCUMENT_TITLE · 章节导航</title><style>body{margin:0;background:#f4f0e4;color:#353b31;font-family:system-ui,sans-serif}main{max-width:1280px;margin:36px auto;padding:0 24px}h1{font-size:30px}video{width:100%;display:block}nav{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap}button{flex:1;min-width:160px;padding:16px;background:#eee7d8;color:#353b31;border:1px solid #d0c4af;border-radius:6px;cursor:pointer;font:inherit}button span{display:block;color:#875e29;margin-bottom:7px}button[aria-current=true]{background:#e1d4bb;border-color:#9c733b}</style><main><h1>DOCUMENT_TITLE</h1><video id="movie" src="MOVIE_PATH" poster="navigation.png" controls preload="metadata"></video><nav>'''+buttons+'''</nav></main><script>const v=document.getElementById('movie'),bs=[...document.querySelectorAll('button')];bs.forEach(b=>b.onclick=()=>{v.currentTime=Number(b.dataset.at);v.play().catch(()=>{});});v.ontimeupdate=()=>{bs.forEach((b,i)=>b.setAttribute('aria-current',v.currentTime>=Number(b.dataset.at)&&(i===bs.length-1||v.currentTime<Number(bs[i+1].dataset.at))));};</script></html>'''
    (directory/'navigation.html').write_text(document.replace('MOVIE_PATH',html.escape(movie,quote=True)).replace('DOCUMENT_TITLE',html.escape(title)),encoding='utf-8')
