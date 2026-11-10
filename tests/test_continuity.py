"""Contract and signal regressions for timed footage, persistent scenes and audio."""
import copy
import json
import math
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
import wave
import struct

from youtube_studio.core import StudioError, validate_script, file_hash
from youtube_studio.timing import align
from youtube_studio.continuity import render
from youtube_studio.audio_mix import mix_audio
from youtube_studio.pipeline import Pipeline, input_signature

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT/'tests/fixtures/continuity-contract.json'


class Continuity(unittest.TestCase):
    def test_caption_switches_contrast_at_live_action_cut(self):
        from youtube_studio.composition import compile_html
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Compilation freezes the referenced file; decode is covered by the export check.
            src = root / 'input.mp4'
            src.touch()
            tl = {'duration':3,'shots':[
                {'id':'film','kind':'footage','layout':'film','start':0,'end':1.5,
                 'credit':'摄影','note':'情境实拍'},
                {'id':'claim','kind':'claim','start':1.5,'end':3,'transition':'cut','headline':'观点'}],
                'captions':[{'text':'跨切点的句子','start':1,'end':2}]}
            project = root / 'composition'
            compile_html(tl,project,ROOT,{'film':src},'final',silent=True)
            page = (project/'index.html').read_text()
            self.assertIn('class="clip caption on-film" data-start="1" data-duration="0.5"',page)
            self.assertIn('class="clip caption" data-start="1.5" data-duration="0.5"',page)

    def test_measured_events_and_single_world_across_units(self):
        fixture = json.loads(FIXTURE.read_text());doc = fixture['doc']
        validate_script(doc)
        offset, shots = 0, []
        for u in doc['units']:
            length=fixture['lengths'][u['id']]
            data = align(u,fixture['words'][u['id']],length)
            for s in data['shots']:
                if s['kind']=='continuity':
                    s['start']+=offset;s['end']+=offset
                    s['events']=[dict(e,at=e['at']+offset) for e in s['events']]
                    shots.append(s)
            offset+=length
        html, motion = render(shots)
        self.assertEqual(html.count('id="street-shop-0"'),1)
        self.assertEqual(html.count('class="street-person"'),12)
        self.assertAlmostEqual(shots[-1]['events'][2]['at'],28.1)
        self.assertAlmostEqual(float(re.search(r'data-duration="([^"]+)',html)[1]),29.1435)
        # A gap/repeated reset cannot silently become a new page.
        broken=copy.deepcopy(shots);broken[1]['start']+=.1
        with self.assertRaises(StudioError):render(broken)

    def test_event_cue_outside_shot_fails(self):
        fixture=json.loads(FIXTURE.read_text());doc=fixture['doc'];u=doc['units'][0]
        u['shots'][1]['events'][0]['cue']='在位企业'
        validate_script(doc)
        with self.assertRaisesRegex(StudioError,'动作须在镜头内'):
            align(u,fixture['words'][u['id']],11.13)

    def test_footage_cannot_loop_past_source_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config.json').write_text(json.dumps({'image':{}}))
            clip=root/'tiny.mp4'
            subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=c=blue:s=640x360:d=0.3','-c:v','libx264',str(clip)],check=True)
            p=Pipeline(root);p.timeline={'shots':[{'id':'s-video','kind':'footage','asset':'tiny.mp4','start':0,'end':1,'provenance':{'source':'test'}}]}
            with self.assertRaisesRegex(StudioError,'实拍区间超过源视频'):p.assets()

    def test_audio_asset_changes_invalidate_input_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'script.json').write_text(json.dumps({'units':[{'audio_tracks':[{'asset':'click.wav'}]}]}))
            (root/'click.wav').write_bytes(b'a');before=input_signature(root)
            (root/'click.wav').write_bytes(b'b')
            self.assertNotEqual(before,input_signature(root))

    def test_later_cropped_music_keeps_its_leading_silence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);voice=root/'voice.wav';bed=root/'bed.wav'
            for p,silent in [(voice,True),(bed,False)]:
                with wave.open(str(p),'wb') as w:
                    w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000)
                    samples=bytearray()
                    for n in range(48000*3):
                        value=0 if silent else round(4000*math.sin(2*math.pi*500*n/48000))
                        samples.extend(struct.pack('<hh',value,value))
                    w.writeframes(samples)
            for duck in [False,True]:
                with self.subTest(duck=duck):
                    out=root/'delayed.wav'
                    mix_audio(voice,[{'id':'later','path':str(bed),'source_in':.4,'at':1.1,'duration':.7,
                                     'gain_db':-8,'fade':.03,'duck':duck}],out,3)
                    with wave.open(str(out)) as w:
                        self.assertEqual(w.getnframes(),144000)
                        values=struct.unpack('<'+'h'*288000,w.readframes(144000))[1::2]
                    self.assertLess(max(abs(x) for x in values[:int(1.09*48000)]),2)
                    self.assertGreater(max(abs(x) for x in values[int(1.2*48000):int(1.6*48000)]),100)
                    self.assertLess(max(abs(x) for x in values[int(1.81*48000):]),2)

    def test_bgm_ducks_during_voice_and_keeps_exact_duration(self):
        # Voice in the left channel only; measure BGM in the right independently.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);voice=root/'voice.wav';bed=root/'bed.wav'
            for p,is_voice in [(voice,True),(bed,False)]:
                with wave.open(str(p),'wb') as w:
                    w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000)
                    for n in range(48000*3):
                        t=n/48000
                        if is_voice: l=.3*math.sin(2*math.pi*300*t) if .8<t<2 else 0;r=0
                        else:l=r=.15*math.sin(2*math.pi*500*t)
                        w.writeframesraw(struct.pack('<hh',round(l*32767),round(r*32767)))
            original=file_hash(voice);out=root/'mix.wav'
            mix_audio(voice,[{'id':'bgm','path':str(bed),'at':0,'duration':3,'gain_db':-8,'fade':.01,'duck':True}],out,3)
            self.assertEqual(file_hash(voice),original)
            with wave.open(str(out)) as w:
                self.assertEqual(w.getnframes(),144000)
                values=struct.unpack('<'+'h'*288000,w.readframes(144000))[1::2]
            def rms(a,b):
                v=values[int(a*48000):int(b*48000)];return math.sqrt(sum(x*x for x in v)/len(v))
            self.assertLess(rms(1.2,1.8),rms(.2,.6)*.6)
            with self.assertRaisesRegex(StudioError,'区间越界'):
                mix_audio(voice,[{'id':'bad','path':str(bed),'at':0,'duration':3.5,'gain_db':-8}],out,4)

if __name__=='__main__':unittest.main()
