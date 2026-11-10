import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from youtube_studio.chapters import chapter_times, navigation, player_page
from youtube_studio.core import StudioError, duration
from youtube_studio.voice_performance import emphasis_spans, perform


class ChaptersAndPerformance(unittest.TestCase):
    def test_player_uses_and_escapes_current_episode_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            player_page(Path(tmp),[{'start':0,'label':'为何现在买'}],title='熊市 & <买入>')
            page=(Path(tmp)/'navigation.html').read_text()
            self.assertIn('<title>熊市 &amp; &lt;买入&gt; · 章节导航</title>',page)
            self.assertIn('<h1>熊市 &amp; &lt;买入&gt;</h1>',page)
            self.assertNotIn('企业再融资',page)

    def test_short_opening_keeps_proportional_width_with_compact_label(self):
        body, _ = navigation([{'start':0,'end':43,'label':'开场'},
                              {'start':43,'end':620,'label':'正文'}],620)
        widths = [float(x) for x in re.findall(r'style="width:([\d.]+)px"',body)]
        self.assertAlmostEqual(widths[0]/widths[1],43/577)
        self.assertIn('01 · 开场',body)
        with self.assertRaises(StudioError):
            navigation([{'start':0,'end':1,'label':'开场'},
                        {'start':1,'end':620,'label':'正文'}],620)

    def test_nav_uses_measured_duration_not_equal_columns(self):
        doc={'narrative':{'chapters':[{'id':'a','question':'问题','units':['u1']},
            {'id':'b','question':'分析','units':['u2','u3']}]}}
        units=[{'id':'u1','start':0,'end':10},{'id':'u2','start':10,'end':20},{'id':'u3','start':20,'end':40}]
        chapters=chapter_times(doc,units)
        body,motion=navigation(chapters,40)
        widths=[float(x) for x in re.findall(r'style="width:([\d.]+)px"',body)]
        self.assertAlmostEqual(widths[1]/widths[0],3)
        self.assertAlmostEqual(sum(widths)+5,1760)
        self.assertEqual(chapters[1]['start'],10)
        self.assertIn('duration:30', ''.join(motion))
        doc['narrative']['chapters'][1]['units']=['u3','u2']
        with self.assertRaises(StudioError):chapter_times(doc,units)

    def test_mid_width_chapter_keeps_ordinal(self):
        body,_=navigation([{'start':0,'end':70,'label':'等待的代价'},
                           {'start':70,'end':620,'label':'怎样开始买'}],620)
        self.assertIn('01 · 等待的代价',body)

    def test_narrow_chapter_stacks_without_losing_identity(self):
        body,_=navigation([{'start':0,'end':30,'label':'开场'},
                           {'start':30,'end':620,'label':'正文'}],620)
        self.assertIn('chapter-label stacked',body)
        self.assertIn('01\n开场',body)

    def test_emphasis_uses_whole_measured_words_and_rejects_missing_cue(self):
        words={'words':[{'text':'不等于','start':.3,'end':.8},{'text':'损失','start':.9,'end':1.5}]}
        spans=emphasis_spans({'voice_emphasis':[{'cue':'等于'}]},words)
        self.assertEqual((spans[0]['start'],spans[0]['end']),(.3,.8))
        with self.assertRaises(StudioError):emphasis_spans({'voice_emphasis':[{'cue':'盈利'}]},words)
        with self.assertRaises(StudioError):emphasis_spans({'voice_emphasis':[{'cue':'损失'},{'cue':'不等于'}]},words)

    def test_emphasis_audio_keeps_all_source_and_adds_measured_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.wav';out=Path(tmp)/'performed.wav'
            subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=3','-ac','1',str(source)],check=True)
            perform(source,[{'start':1,'end':2,'speed':.94,'gain_db':1.6,'pause_before':.12}],out)
            self.assertAlmostEqual(duration(out),3+.12+1/.94-1,delta=.04)
            self.assertAlmostEqual(duration(source),3,places=4)
