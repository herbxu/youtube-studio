"""Generate a synthetic layout fixture, never a narrated episode or ASR timeline.

Uses the actual canonical script/assets but intentionally synthetic test times.
Outputs root build/explain-contract; no episode delivery is touched.
"""
import copy
from pathlib import Path
import wave
from youtube_studio.core import read,write,probe
from youtube_studio.composition import compile_html

ROOT=Path(__file__).resolve().parents[1]
from youtube_studio.storage import works
EP=works()/'episodes/20260913-企业再融资-增发和发债'
OUT=ROOT/'build/explain-contract'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    doc=read(EP/'script.json');shots=[];captions=[];assets={};duration=len(doc['units'])*17
    silence=OUT/'layout-only-silence.wav'
    with wave.open(str(silence),'wb') as f:
        f.setparams((1,2,48000,0,'NONE','not compressed'));f.writeframes(b'\0\0'*48000*duration)
    for i,u in enumerate(doc['units']):
        start=i*17;s=copy.deepcopy(u['shots'][0]);s.update(start=start,end=start+17)
        if s.get('events'):
            # Same spoken cue shares one fixture time; these are NOT voice timings.
            cues=list(dict.fromkeys(e['cue'] for e in s['events']))
            for e in s['events']:e['at']=start+.5+cues.index(e['cue'])*min(3,12/max(len(cues)-1,1))
        if s.get('headline_parts'):s['headline_times']=[start+2+n*3 for n in range(len(s['headline_parts']))]
        if s['kind']=='quantity':s['change_time']=start+7
        if s.get('asset'):
            assets[s['id']]=EP/s['asset'];stream=probe(assets[s['id']])['streams'][0];s['image_size']=[stream['width'],stream['height']]
        shots.append(s);captions.append({'start':start,'end':start+17,'text':'技术检查：此处尚未接入正式语音与字幕'})
    timeline={'duration':duration,'audio':str(silence),'shots':shots,'captions':captions,'overlays':[],'units':[],
              'timing_method':'synthetic-layout-test-not-ASR','not_an_episode_delivery':True}
    write(OUT/'fixture.json',timeline)
    compile_html(timeline,OUT/'composition',ROOT,assets,'layout','opinion-explainer/v1')
    print(OUT/'composition/index.html')

if __name__=='__main__':main()
