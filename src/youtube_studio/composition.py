"""Compile measured shots to a self-contained, seek-safe HyperFrames composition."""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

from .core import require, write
from . import magazine
from . import text_motion
from . import continuity, explain, chapters, essay
from . import motion_essay


CSS = motion_essay.CSS + """
*{box-sizing:border-box}html,body{margin:0;width:1920px;height:1080px;overflow:hidden}
/* Keep full-document capture on macOS Chrome: HyperFrames otherwise downgrades
   it to viewport capture, which can truncate the lower edge of long renders.
   The authored composition and exported crop remain exactly 1920 x 1080. */
html{min-height:1082px}
@font-face{font-family:Studio;src:url('media/font.ttf')}body{font-family:Studio,sans-serif;color:#292d29}
#root{position:relative;width:1920px;height:1080px;overflow:hidden}
.paper,.shot,.canvas{position:absolute;inset:0;width:1920px;height:1080px}
.paper,.canvas{background:#f4f0e4}.shot{overflow:hidden}.canvas{overflow:hidden}
.art{position:absolute;width:1920px;height:1080px;object-fit:cover}
.headline{position:absolute;left:210px;top:360px;width:1500px;max-height:360px;font-size:86px;line-height:1.4;text-align:center;font-weight:600}
.question{position:absolute;left:140px;top:100px;max-width:1080px;padding:22px 36px;border:2px solid #6b7564;border-radius:30px;background:#faf7ef;font-size:50px;line-height:1.45}
.pair{position:absolute;left:320px;top:270px;width:1280px;display:flex;gap:90px;justify-content:center}
.concept{width:540px;height:440px;border-top:4px solid #7b826e;border-bottom:1px solid #7b826e;display:flex;align-items:center;justify-content:center;text-align:center;font-size:72px;line-height:1.5;padding:40px;background:#faf7ee}
.flow{position:absolute;left:150px;top:390px;width:1620px;display:flex;align-items:center;justify-content:space-between}
.node{width:400px;min-height:190px;border-bottom:4px solid #5c765e;display:flex;align-items:center;justify-content:center;font-size:55px;text-align:center;padding:20px}
.claim-line{position:relative;display:inline-block;max-width:1500px}.claim-mark{position:absolute;left:0;bottom:-18px;width:100%;height:6px;background:#627e5d;transform-origin:left center}
.arrow{width:150px;font-size:90px;text-align:center;color:#526b55;transform-origin:left center}
.quantity{position:absolute;left:260px;top:190px;width:1400px;text-align:center}
.qtitle{font-size:48px;color:#53674f}.equation{font-size:130px;line-height:1.5;margin-top:55px}.percent{font-size:110px;color:#45694b}
.bar{position:absolute;left:0;top:480px;width:1400px;height:40px;background:#dadccc;border-radius:8px;overflow:hidden}.share{width:1400px;height:40px;background:#5c7a59;transform-origin:left center}
.note{font-size:30px;position:absolute;left:140px;bottom:155px;max-width:1640px;color:#53594e;padding:10px 16px;background:#faf7ef;border-radius:8px}
.caption{position:absolute;left:180px;top:920px;width:1560px;height:85px;display:flex;justify-content:center;align-items:center;z-index:100}
.caption span{font-size:42px;line-height:1.3;padding:12px 25px;background:#faf7ef;color:#252a26;border-radius:8px;max-width:1560px;text-align:center}
.caption.on-cover span{background:#192521;color:#fff6e7}
.preview-label{position:absolute;right:50px;bottom:24px;font-size:22px;color:#55594f;z-index:1300}
.disclaimer{position:absolute;left:140px;bottom:170px;z-index:110}
.disclaimer-copy{display:inline-block;width:max-content;max-width:600px;padding:12px 18px;background:#faf7ef;color:#33382f;font-size:28px;line-height:1.5;white-space:pre-line;border-radius:8px}
"""


def compile_html(timeline, project, runtime, assets, mode, style=None, *, window=None, silent=False, width=1920):
    project = Path(project)
    media = project / "media"
    media.mkdir(parents=True, exist_ok=True)
    shutil.copy2(runtime / "node_modules/gsap/dist/gsap.min.js", media / "gsap.min.js")
    # Freeze only this episode's glyphs: self-contained and small enough to inline.
    from fontTools import subset
    from fontTools.ttLib import TTFont
    font = TTFont(runtime / "resources/fonts/noto-sans-sc.ttf", recalcTimestamp=False)
    sub = subset.Subsetter()
    sub.populate(text=json.dumps(timeline,ensure_ascii=False) + continuity.GLYPHS + essay.GLYPHS + "观点研究竞争优势原有店铺新进入者新增供给利润空间方向示意无量纲当前领先者竞争对手制作预览假设示例持股比例变化不等同于财富同比变化持有数量不变总量发生变化0123456789.% /→·")
    sub.subset(font)
    font.save(media / "font.ttf")
    font.close()
    duration = timeline["duration"]
    esc = lambda s: html.escape(str(s), quote=True)
    fragments, tweens = [], []
    transitions = []
    shots = timeline["shots"]
    continuous = [s for s in shots if s['kind'] == 'continuity']
    if continuous:
        body, motion = continuity.render(continuous)
        fragments.append(body)
        tweens.extend(motion)
    object_shots = [s for s in shots if s["kind"] == "object_scene"]
    if object_shots:
        body, motion = explain.render_objects(object_shots, media, assets)
        fragments.append(body)
        tweens.extend(motion)
    for local_i, s in enumerate(shots):
        i = s.get('_global_index', local_i)
        count = s.get('_global_count', len(shots))
        sid = s["id"]
        start, end = s["start"], s["end"]
        # Keep outgoing image alive under incoming fade. Audio clock never shifts.
        fade = 0 if s.get("transition") == "cut" else min(.45, (end-start)/4)
        next_cut = s.get('_next_is_cut', local_i+1 < len(shots) and shots[local_i+1].get('transition') == 'cut')
        clip_end = min(duration, end + (0 if next_cut else .45)) if i+1 < count else end
        body = ""
        kind = s["kind"]
        if kind in {'continuity', 'object_scene'}:
            continue
        if kind == 'footage':
            name = sid+'.mp4'
            shutil.copy2(assets[sid], media/name)
            focus = s.get('focus', [.5,.5])
            fragments.append(f'<video id="{sid}-video" class="clip footage-panel" src="media/{name}" data-start="{start}" data-duration="{end-start}" data-track-index="{i+1}" muted playsinline data-volume="0" style="object-position:{focus[0]*100}% {focus[1]*100}%"></video>')
            if s.get('layout') == 'film':
                fragments.append(f'<div id="{sid}-shade" class="clip film-shade" data-start="{start}" data-duration="{end-start}" data-track-index="30"></div>')
                fragments.append(f'<div id="{sid}-credit" class="clip film-credit" data-start="{start}" data-duration="{end-start}" data-track-index="31">{esc(s["credit"])} · {esc(s["note"])}</div>')
                times = s.get('label_times', [])
                for n, (label, at) in enumerate(zip(s.get('labels', []), times)):
                    until = times[n+1] if n+1 < len(times) else end
                    columns = label.split('\t', 1)
                    paired = ' paired' if len(columns) == 2 else ''
                    content = ''.join(f'<span>{esc(column)}</span>' for column in columns)
                    fragments.append(f'<div id="{sid}-annotation-{n}" class="clip film-annotation{paired}" data-start="{at}" data-duration="{until-at}" data-track-index="32">{content}</div>')
                continue
            fragments.append(f'<div id="{sid}-question" class="clip footage-question" data-start="{start}" data-duration="{end-start}" data-track-index="30">{esc(s.get("headline", ""))}</div>')
            fragments.append(f'<div class="clip footage-credit" data-start="{start}" data-duration="{end-start}" data-track-index="31">{esc(s["credit"])} · {esc(s["note"])}</div>')
            continue
        if kind == 'outro':
            require(timeline.get('branding'), '片尾落款需要真实频道 logo')
            brand_ext = Path(timeline['branding']['path']).suffix.lower()
            body = f'<div id="{sid}-signature" style="position:absolute;left:560px;top:325px;width:800px;text-align:center"><img src="media/channel-logo{brand_ext}" style="width:400px;height:200px;object-fit:contain"/><div style="height:2px;width:72px;margin:38px auto;background:#9c733b"></div><div style="font-size:42px;color:#203b36;letter-spacing:5px">{esc(s["tagline"])}</div></div>'
            tweens.append(f'tl.fromTo("#{sid}-signature",{{opacity:0,y:12}},{{opacity:1,y:0,duration:1,ease:"power2.out"}},{start+.1});')
        elif kind == 'cover':
            body, motion = chapters.cover(s, timeline.get('chapters', []), media, assets[sid])
            tweens.extend(motion)
        elif kind == "essay_scene":
            body, motion = essay.render(s, media, assets)
            tweens.extend(motion)
        elif kind == "evidence":
            body, motion = explain.render_evidence(s, media, assets)
            tweens.extend(motion)
        elif kind in {"collage", "mechanism"}:
            body, motion = magazine.render_shot(s, media, assets)
            tweens.extend(motion)
        elif kind == "illustration":
            src = assets[sid]
            name = sid + src.suffix.lower()
            shutil.copy2(src, media / name)
            focus = s.get("focus", [.5, .5])
            body = f'<img id="{sid}-art" class="art" src="media/{esc(name)}" style="object-position:{focus[0]*100}% {focus[1]*100}%;transform-origin:{focus[0]*100}% {focus[1]*100}%" />'
            if s.get("headline"):
                position = ' style="left:auto;right:140px;max-width:820px"' if s.get('headline_position')=='right' else ''
                body += f'<div class="question"{position}>{esc(s["headline"])}</div>'
            motion = s.get("motion", "push")
            begins, ends = {"push": ({"scale":1}, {"scale":1.05}), "pull": ({"scale":1.05}, {"scale":1}),
                            "left": ({"scale":1.08,"x":25}, {"scale":1.08,"x":-25}),
                            "right": ({"scale":1.08,"x":-25}, {"scale":1.08,"x":25}),
                            "hold": ({"scale":1}, {"scale":1})}[motion]
            tweens.append(f'tl.fromTo("#{sid}-art",{json.dumps(begins)},{json.dumps(dict(ends,duration=clip_end-start,ease="none"))},{start});')
        elif kind == "claim" and s.get("headline_parts"):
            body, motion = text_motion.headline(s, "headline")
            tweens.extend(motion)
        elif kind == "claim":
            body = f'<div id="{sid}-claim" class="headline"><span class="claim-line">{esc(s["headline"])}<span id="{sid}-mark" class="claim-mark"></span></span></div>'
            tweens.append(f'tl.fromTo("#{sid}-claim",{{opacity:0,y:18}},{{opacity:1,y:0,duration:.5,ease:"power2.out"}},{start+.1});')
            mark_start = start + min(.35, (end-start)*.2)
            mark_duration = min(.6, (end-start)*.3)
            tweens.append(f'tl.fromTo("#{sid}-mark",{{scaleX:0}},{{scaleX:1,duration:{mark_duration},ease:"power2.out"}},{mark_start});')
        elif kind == "comparison":
            body = '<div class="pair">' + ''.join(f'<div id="{sid}-label-{n}" class="concept">{esc(t)}</div>' for n,t in enumerate(s["labels"])) + '</div>'
            if s.get('headline'):
                body += f'<div class="question">{esc(s["headline"])}</div>'
            for n in range(len(s['labels'])):
                at=s.get('label_times',[start+.2,start+.6])[n]
                tweens.append(f'tl.fromTo("#{sid}-label-{n}",{{opacity:0,y:24}},{{opacity:1,y:0,duration:.45,ease:"power2.out"}},{at});')
        elif kind == "flow":
            body = '<div class="flow">'
            # Nodes and their incoming arrows share measured voice anchors.
            label_times = s.get('label_times', [start+.15+n*.4 for n in range(3)])
            for n, label in enumerate(s["labels"]):
                if n and s.get('layout') != 'parallel':
                    body += f'<div id="{sid}-arrow-{n}" class="arrow">→</div>'
                    tweens.append(f'tl.fromTo("#{sid}-arrow-{n}",{{scaleX:0,opacity:0}},{{scaleX:1,opacity:1,duration:.4,ease:"power2.out"}},{label_times[n]});')
                body += f'<div id="{sid}-label-{n}" class="node">{esc(label)}</div>'
                at=label_times[n]
                tweens.append(f'tl.fromTo("#{sid}-label-{n}",{{opacity:0,y:20}},{{opacity:1,y:0,duration:.4,ease:"power2.out"}},{at});')
            body += '</div>'
            if s.get('headline'):
                body += f'<div class="question">{esc(s["headline"])}</div>'
        else:
            owned, before, after = s["owned"], s["before"], s["after"]
            body = (f'<div class="quantity"><div class="qtitle">{esc(s.get("label","持有数量不变，总量发生变化"))}</div>'
                    f'<div class="equation">{owned:g} / <span id="{sid}-total">{before:g}</span></div>'
                    f'<div class="percent" id="{sid}-percent">{owned/before*100:.2f}%</div>'
                    f'<div class="bar"><div id="{sid}-share" class="share"></div></div></div>')
            if s["hypothetical"] and s.get("show_note", True):
                note = "假设示例 · 持股比例变化不等同于财富同比变化"
                if s.get("note"):
                    note += " · " + s["note"]
                body += f'<div class="note">{esc(note)}</div>'
            # One pure formula, driven by seeked tween state, updates all quantities together.
            t = s["change_time"]
            d = min(1.1, end-t-.55)
            tweens += [f'const q{i}={{total:{before}}};',
                       f'function update{i}(){{const n=Math.round(q{i}.total);document.getElementById("{sid}-total").textContent=n.toFixed(0);document.getElementById("{sid}-percent").textContent=({owned}/n*100).toFixed(2)+"%";gsap.set("#{sid}-share",{{scaleX:{owned}/n}});}}',
                       f'update{i}();tl.fromTo(q{i},{{total:{before}}},{{total:{after},duration:{d},ease:"none",onUpdate:update{i}}},{t});']
        if s.get("note") and s.get("show_note", True) and kind != "essay_scene" and not (kind == "quantity" and s["hypothetical"]):
            body += f'<div class="note">{esc(s["note"])}</div>'
        if style == "editorial-magazine/v1":
            body += f'<div class="mast">观点研究<span class="folio">{i+1:02d} / {count:02d}</span></div>'
        fragments.append(f'<section id="{sid}" class="clip shot" data-start="{start}" data-duration="{clip_end-start}" data-track-index="{i+1}"><div id="{sid}-canvas" class="canvas">{body}</div></section>')
        if i and fade:
            tweens.append(f'tl.fromTo("#{sid}-canvas",{{opacity:0}},{{opacity:1,duration:{fade},ease:"none"}},{start});')
            transitions.append({"time": start, "duration": fade})
        if i+1 < count and not next_cut:
            # Fade old text before the next scene; images can still dissolve.
            # Avoid superimposing two sets of large words during the overlap.
            selectors = {"cover":".cover-title, .cover-subtitle", "illustration":".question", "claim":".headline", "comparison":".pair, .question",
                         "flow":".flow, .question", "quantity":".quantity, .note",
                         "collage":".question, .hero-copy, .hero-deck, .photo-label, .photo-credit", "mechanism":".question, .mechanism-stage", "evidence":".explain-title, .evidence-label, .evidence-credit, .evidence-mark", "essay_scene":".motion-essay, .essay"}
            targets = ','.join(f'#{sid}-canvas {x.strip()}' for x in (selectors[kind]+', .note, .mast').split(','))
            if kind != "illustration" or s.get("headline") or s.get("note"):
                tweens.append(f'tl.to({json.dumps(targets)},{{opacity:0,duration:.18,ease:"none"}},{end-.18});')
    if timeline.get('chapters'):
        opening_cover = next((s for s in shots if s['kind']=='cover' and s['start']==0),None)
        body, motion = chapters.navigation(timeline['chapters'], timeline.get('spoken_duration',duration), timeline.get('_nav_start', opening_cover['end'] if opening_cover else 0), timeline.get('upcoming_chapters', ()), timeline.get('_nav_end', next((s['start'] for s in shots if s.get('channel_signoff')), None)))
        fragments.append(body)
        tweens.extend(motion)
    if timeline.get('branding'):
        brand = Path(timeline['branding']['path'])
        name = 'channel-logo' + brand.suffix.lower()
        shutil.copy2(brand, media/name)
        brand_width = timeline['branding'].get('width',142)
        brand_height = round(brand_width*70/142)
        fragments.append(f'<div id="channel-brand" class="clip" data-start="0" data-duration="{timeline.get("spoken_duration",duration)}" data-track-index="1300" style="position:absolute;left:{1880-brand_width}px;top:{1064-brand_height}px;width:{brand_width}px;height:{brand_height}px;z-index:1300;background:#f5f1e7;border-radius:4px;padding:5px"><img src="media/{name}" style="width:100%;height:100%;object-fit:contain"/></div>')
    for i, o in enumerate(timeline.get('overlays',[])):
        fragments.append(f'<div id="overlay-{i}" class="clip disclaimer" data-start="{o["start"]}" data-duration="{o["end"]-o["start"]}" data-track-index="1100"><span id="overlay-{i}-copy" class="disclaimer-copy">{esc(o["text"])}</span></div>')
        if o.get('fade_in'):
            tweens.append(f'tl.fromTo("#overlay-{i}-copy",{{opacity:0,y:6}},{{opacity:1,y:0,duration:{o["fade_in"]},ease:"sine.out"}},{o["start"]});')
        if o.get('fade_out'):
            tweens.append(f'tl.to("#overlay-{i}-copy",{{opacity:0,duration:{o["fade_out"]},ease:"sine.in"}},{o["end"]-o["fade_out"]});')
    for i, c in enumerate(timeline["captions"]):
        film = [s for s in shots if s['kind']=='footage' and s.get('layout')=='film']
        boundaries = sorted({c['start'], c['end'], *(t for s in film for t in (s['start'],s['end'])
                             if c['start'] < t < c['end'])})
        for part, (a,b) in enumerate(zip(boundaries,boundaries[1:])):
            cover_class = ' on-cover' if any(s['kind']=='cover' and s['start']<=a<s['end'] for s in shots) else ''
            film_class = ' on-film' if any(s['start']<=a<s['end'] for s in film) else ''
            suffix = f'-{part}' if part else ''
            fragments.append(f'<div id="caption-{i}{suffix}" class="clip caption{cover_class}{film_class}" data-start="{a}" data-duration="{b-a}" data-track-index="1000"><span>{esc(c["text"])}</span></div>')
    if not silent:
        shutil.copy2(timeline["audio"], media / "voice.master.wav")
        fragments.append(f'<audio id="voice" src="media/voice.master.wav" data-start="0" data-duration="{duration}" data-track-index="2000" data-volume="1"></audio>')
    if mode in {"preview", "layout"}:
        label = "布局验证 · 合成时序 · 无旁白" if mode == "layout" else "制作预览"
        fragments.append(f'<div class="preview-label">{label}</div>')
    require(width in (1280,1920), '画面宽度支持1280或1920')
    height = width * 9 // 16
    base_css = CSS.replace('html,body{margin:0;width:1920px;height:1080px;', f'html,body{{margin:0;width:{width}px;height:{height}px;')
    sizing = f'html,body{{width:{width}px;height:{height}px}}html{{min-height:{height+2}px}}#root{{width:{width}px;height:{height}px}}#stage{{position:absolute;width:1920px;height:1080px;transform-origin:top left;transform:scale({width/1920})}}'
    body = ''.join(fragments)
    registration = 'window.__timelines={main:tl};'
    if window:
        from .incremental import window_markup
        body = window_markup(body, *window)
        offset, stop = window
        duration = stop-offset
        # The property setter still runs when the renderer seeks with events suppressed.
        # Keep absolute animation time (including preceding transitions) seek-safe.
        registration = (f'const clock={{}};let clockTime={offset};'
                        'Object.defineProperty(clock,"time",{get(){return clockTime},set(v){clockTime=v;tl.time(v,false)}});'
                        f'tl.time({offset},false);const view=gsap.timeline({{paused:true}});'
                        f'view.fromTo(clock,{{time:{offset}}},{{time:{stop},duration:{duration},ease:"none"}},0);'
                        'window.__timelines={main:view};')
    doc = (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>Opinion studio</title>'
           f'<script src="media/gsap.min.js"></script><style>{base_css + magazine.CSS + text_motion.CSS + continuity.CSS + explain.CSS + chapters.CSS + essay.CSS + sizing}</style></head><body class="{"magazine" if style == "editorial-magazine/v1" else "continuous" if continuous else ""}">'
           f'<div id="root" data-composition-id="main" data-start="0" data-duration="{duration}" data-width="{width}" data-height="{height}">'
           '<div id="stage"><div class="paper"></div>' + body + '</div></div><script>'
           'const tl=gsap.timeline({paused:true});' + ''.join(tweens) +
           registration + '</script></body></html>')
    (project / "index.html").write_text(doc, encoding="utf-8")
    write(project / "hyperframes.json", {"authoringSkill":"general-video", "media":{"autoProxy":False}})
    if window:
        transitions = [dict(t,time=max(0,t['time']-window[0])) for t in transitions if t['time'] < window[1] and t['time']+t['duration'] > window[0]]
    write(project / "transitions.json", transitions)
    return project / "index.html"
