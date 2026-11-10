"""Subtle, word-timed emphasis edits; original TTS and edit evidence retained."""
from .core import normalize, number, require, run, duration


def emphasis_spans(unit, transcript):
    words = transcript['words']
    text, ranges = '', []
    for w in words:
        token = normalize(w['text'])
        text += token
        ranges.extend([(w['start'], w['end'])] * len(token))
    result=[]
    for row in unit.get('voice_emphasis', []):
        cue = normalize(row['cue'])
        require(cue and text.count(cue) == 1, '强调词必须完整、唯一地定位到实测音频')
        i=text.index(cue)
        start,end=ranges[i][0],ranges[i+len(cue)-1][1]
        gain=row.get('gain_db',1.5);speed=row.get('speed',.94);pause=row.get('pause_before',.1)
        number(gain,0,3,'emphasis.gain_db');number(speed,.85,1,'emphasis.speed');number(pause,0,.25,'emphasis.pause_before')
        result.append(dict(cue=row['cue'],start=start,end=end,gain_db=gain,speed=speed,pause_before=pause))
    require(all(a['end'] <= b['start'] for a,b in zip(result,result[1:])), '强调片段不能重叠或倒序')
    return result


def perform(audio, spans, output):
    length=duration(audio);pieces=[];cursor=0
    for row in spans:
        require(cursor <= row['start'] < row['end'] <= length, '强调区间超出音频')
        if row['start'] > cursor:pieces.append(dict(start=cursor,end=row['start'],speed=1,gain_db=0))
        if row['pause_before']:pieces.append(dict(pause=row['pause_before']))
        pieces.append(row);cursor=row['end']
    if cursor < length:pieces.append(dict(start=cursor,end=length,speed=1,gain_db=0))
    filters=[];labels=[]
    for i,p in enumerate(pieces):
        label=f'p{i}';labels.append(f'[{label}]')
        if 'pause' in p:
            filters.append(f'anullsrc=r=48000:cl=mono,atrim=duration={p["pause"]}[{label}]')
        else:
            end=(p['end']-p['start'])/p['speed']
            filters.append(f'[0:a]atrim=start={p["start"]}:end={p["end"]},asetpts=PTS-STARTPTS,atempo={p["speed"]},volume={p["gain_db"]}dB,afade=t=in:d=0.004,afade=t=out:st={max(0,end-.008)}:d=0.008[{label}]')
    filters.append(''.join(labels)+f'concat=n={len(labels)}:v=0:a=1[out]')
    run(['ffmpeg','-y','-v','error','-i',audio,'-filter_complex',';'.join(filters),'-map','[out]','-ar','48000','-ac','1','-c:a','pcm_s16le',output])
    expected=length+sum(p['pause_before']+(p['end']-p['start'])*(1/p['speed']-1) for p in spans)
    require(abs(duration(output)-expected)<.15, '强调剪辑时长偏差异常')
