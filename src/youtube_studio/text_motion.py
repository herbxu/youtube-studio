"""Voice-anchored phrase reveals; glyph staggering is design, not ASR timing."""
import html

CSS = """
.motion-phrase{position:relative;display:inline-block;vertical-align:bottom;white-space:nowrap;overflow:hidden;padding-bottom:.12em}
.motion-glyph{display:inline-block;opacity:0;min-width:.05em}
.motion-accent{color:#a33629}
.motion-underline{position:absolute;left:0;bottom:.05em;width:100%;height:.055em;background:#a33629;transform-origin:left center}
"""


def headline(s, class_name):
    esc = lambda t: html.escape(t, quote=True)
    parts = s.get('headline_parts')
    if not parts:
        return f'<div class="{class_name}">{esc(s["headline"])}</div>', []
    fragments, tweens = [], []
    for n, (part, at) in enumerate(zip(parts, s['headline_times'])):
        pid = f'{s["id"]}-phrase-{n}'
        chars = part['text']
        # Entire phrase resolves within 0.6s, leaving a measured reading hold.
        stagger = min(.035, .24/max(1,len(chars)-1))
        fragments.append(f'<span id="{pid}" class="motion-phrase{" motion-accent" if part.get("emphasis") else ""}" data-phrase-at="{at}">' +
                         ''.join(f'<span class="motion-glyph">{esc(c)}</span>' for c in chars) +
                         (f'<span id="{pid}-line" class="motion-underline"></span>' if part.get('emphasis') else '') + '</span>')
        tweens += [f'tl.set("#{pid} .motion-glyph",{{opacity:1,stagger:{stagger}}},{at});',
                   f'tl.fromTo("#{pid} .motion-glyph",{{yPercent:115}},{{yPercent:0,duration:.36,stagger:{stagger},ease:"power3.out"}},{at});']
        if part.get('emphasis'):
            tweens.append(f'tl.fromTo("#{pid}-line",{{scaleX:0}},{{scaleX:1,duration:.35,ease:"power2.out"}},{at+.4});')
    return f'<div class="{class_name}">'+''.join(fragments)+'</div>', tweens
