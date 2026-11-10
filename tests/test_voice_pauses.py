import tempfile
import unittest
import wave
from pathlib import Path
import numpy as np
from youtube_studio.voice_pauses import plan, apply
from youtube_studio.core import StudioError


class ThoughtPauses(unittest.TestCase):
    def fixture(self,path,quiet=True):
        rate=48000;t=np.arange(rate*2)/rate
        samples=(5000*np.sin(2*np.pi*220*t)).astype('<i2')
        if quiet:samples[int(.9*rate):int(1.1*rate)]=0
        with wave.open(str(path),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate);f.writeframes(samples.tobytes())
        return samples,{'words':[{'text':'想一想','start':0,'end':.9},{'text':'再回答','start':1.1,'end':1.9}]}

    def test_quiet_gap_extended_without_losing_spoken_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'voice.wav';out=Path(tmp)/'pause.wav';samples,transcript=self.fixture(source)
            edits=plan(source,[{'after':'想一想','seconds':.7}],transcript)
            self.assertAlmostEqual(edits[0]['insert_seconds'],.5)
            self.assertTrue(.9<=edits[0]['at']<=1.1)
            apply(source,edits,out)
            with wave.open(str(out),'rb') as f:actual=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2')
            self.assertEqual(len(actual),len(samples)+24000)
            np.testing.assert_array_equal(actual[:40000],samples[:40000])
            np.testing.assert_array_equal(actual[-40000:],samples[-40000:])
            self.assertEqual(plan(source,[{'after':'想一想','seconds':.2}],transcript),[])

    def test_no_quiet_seam_and_final_padding_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'voice.wav';_,transcript=self.fixture(source,False)
            with self.assertRaises(StudioError):plan(source,[{'after':'想一想','seconds':.7}],transcript)
            with self.assertRaises(StudioError):plan(source,[{'after':'再回答','seconds':.7}],transcript)
