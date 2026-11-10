import json
import math
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

from youtube_studio.audio_mix import mix_audio
from youtube_studio.core import StudioError
from youtube_studio.finishing import overlays, add_closing, declick
from youtube_studio.incremental import visual_slice


def tone(path, seconds, click=False):
    samples = array('h', [round(3000*math.sin(2*math.pi*300*i/48000)) for i in range(round(seconds*48000))])
    if click: samples[12000] = 30000
    with wave.open(str(path),'wb') as f:
        f.setparams((1,2,48000,len(samples),'NONE','')); f.writeframes(samples.tobytes())


class Finishing(unittest.TestCase):
    def test_overlay_checks_first_cut_not_only_unit_end(self):
        units=[dict(id='opening',start=0,end=12)]
        shots=[dict(start=0,end=4),dict(start=4,end=12)]
        row=dict(unit='opening',text='声明',offset=.25,duration=2.65,clear_before_cut=.2)
        self.assertAlmostEqual(overlays({'overlays':[row]},units,shots)[0]['end'],2.9)
        with self.assertRaises(StudioError):
            overlays({'overlays':[dict(row,duration=4)]},units,shots)

    def test_closing_does_not_stretch_narrated_chapters(self):
        t=dict(duration=10,shots=[dict(id='s',kind='claim',start=0,end=10)],
               chapters=[dict(start=0,end=10)],captions=[],audio_tracks=[dict(id='bgm',at=0,duration=10)])
        add_closing(t,dict(duration=4,tagline='落款',music_track='bgm'))
        self.assertEqual((t['duration'],t['spoken_duration'],t['chapters'][0]['end']),(14,10,10))
        self.assertEqual(t['audio_tracks'][0]['duration'],14)
        self.assertEqual(visual_slice(t,10,14)['spoken_duration'],10)

    def test_impulse_repair_preserves_timing_and_reduces_single_click(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.wav';out=Path(tmp)/'out.wav';tone(source,1,True)
            declick(source,out)
            with wave.open(str(out)) as f:
                self.assertEqual(f.getnframes(),48000)
                data=array('h');data.frombytes(f.readframes(48000))
            self.assertLess(abs(data[12000]),8000)
            self.assertGreater(json.loads((out.parent/'repair.json').read_text())['detected_impulse_samples'],0)

    def test_music_survives_beyond_narration_and_fades_at_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            voice=Path(tmp)/'voice.wav';bgm=Path(tmp)/'bgm.wav';out=Path(tmp)/'mix.wav'
            tone(voice,.5);tone(bgm,2)
            mix_audio(voice,[dict(id='bgm',path=str(bgm),at=0,duration=2,gain_db=-12,fade=.01,fade_out=.5,duck=True)],out,2)
            with wave.open(str(out)) as f:
                self.assertEqual(f.getnframes(),96000)
                data=array('h');data.frombytes(f.readframes(96000))
            def rms(a):return (sum(x*x for x in a)/len(a))**.5
            body=rms(data[48000*2:60000*2]);tail=rms(data[-480*2:])
            self.assertGreater(body,50);self.assertLess(tail,body/10)
