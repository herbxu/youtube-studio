"""Incremental export invariants: timestamps, cache scope, and unchanged video on audio edits."""
import copy
import math
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from youtube_studio.core import StudioError, read, run, write, file_hash
from youtube_studio.incremental import bundle_hash, frame_windows, visual_slice, window_markup, render_incremental
from youtube_studio.pipeline import Pipeline, REPO


def timeline(audio):
    return {'duration':4.03,'audio':str(audio),'chapters':[], 'captions':[], 'shots':[
        {'id':'one','kind':'claim','start':0,'end':2.01,'headline':'第一观点'},
        {'id':'two','kind':'claim','start':2.01,'end':4.03,'headline':'第二观点'}]}


class Incremental(unittest.TestCase):
    def test_svg_clipping_bytes_invalidate_visual_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project/'media').mkdir()
            (project/'index.html').write_text('<svg><image href="media/product.png"/></svg>')
            clipping = project/'media/product.png'
            clipping.write_bytes(b'first revision')
            previous = bundle_hash(project)
            clipping.write_bytes(b'second revision')
            self.assertNotEqual(previous, bundle_hash(project))

    def test_no_frame_gaps_or_accumulating_rounding_drift(self):
        t={'duration':93.08548,'shots':[{'start':x} for x in (0,6.86,20.152542,39.510771,57.252438,76.936376)]}
        rows=frame_windows(t,30)
        frames=[n for r in rows for n in range(r['first_frame'],r['first_frame']+r['frames'])]
        self.assertEqual(frames,list(range(2793)))
        self.assertLess(rows[-1]['end']-t['duration'],1/30)
        for selection in [(-1,3),(3,2),(0,94),(0,float('nan'))]:
            with self.assertRaises(StudioError):frame_windows(t,30,selection)

    def test_window_rebases_crossing_media_and_captions(self):
        text=window_markup('<video class="clip" data-start="3" data-duration="4" src="x" data-media-start="2"></video><div data-start="6" data-duration="3">文&amp;字</div>',5,8)
        self.assertIn('data-media-start="4.0"',text)
        self.assertIn('data-duration="2.0"',text)
        self.assertIn('data-start="1.0"',text)
        self.assertIn('文&amp;字',text)

    def test_preceding_dissolve_and_world_history_are_preserved(self):
        t=timeline('unused');t['shots'] += [{'id':'three','kind':'claim','start':4.03,'end':6,'headline':'第三'}];t['duration']=6
        t['branding']={'path':'channel.svg','sha256':'original'}
        s=visual_slice(t,2.033,4.0)
        self.assertEqual(s['branding'],t['branding'])
        s['branding']['sha256']='modified'
        self.assertEqual(t['branding']['sha256'],'original')
        self.assertEqual([r['id'] for r in s['shots']],['one','two'])
        self.assertEqual(s['shots'][1]['_global_index'],1)
        t['shots'][0].update(kind='object_scene',scene_id='world')
        t['shots'][1].update(kind='object_scene',scene_id='world')
        self.assertEqual(len(visual_slice(t,3,3.5)['shots']),2)

    def test_final_refuses_partial_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(StudioError):Pipeline(Path(tmp),selection=(0,1))

    def test_hard_cut_beyond_window_does_not_fade_outgoing_text(self):
        from youtube_studio.composition import compile_html
        source = timeline('unused')
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            for transition, fades in [('cut', False), ('dissolve', True)]:
                source['shots'][1]['transition'] = transition
                view = visual_slice(source, 0, 2)
                compile_html(view, project, REPO, {}, 'final', silent=True)
                html = (project / 'index.html').read_text()
                self.assertEqual('duration:.18,ease:"none"' in html, fades)

    def test_audio_edit_reuses_all_visuals_and_mismatched_cache_is_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);write(root/'config.json',{'render':{'fps':30},'style':{}})
            audio=root/'voice.wav'
            def voice(hz):run(['ffmpeg','-y','-v','error','-f','lavfi','-i',f'sine=frequency={hz}:duration=4.03','-ar','48000','-ac','2',audio])
            voice(440)
            calls=[]
            def hf(args,project,**kwargs):
                if args[0]=='check':return '{"ok":true}'
                doc=(project/'index.html').read_text()
                length=float(re.search(r'data-composition-id="main" data-start="0" data-duration="([^"]+)"',doc)[1])
                calls.append(project.name)
                run(['ffmpeg','-y','-v','error','-f','lavfi','-i',f'color=c=beige:s=1920x1080:r=30:d={length}',
                     '-frames:v',str(math.ceil(length*30-1e-7)),'-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',args[args.index('--output')+1]])
            def render(t):
                p=Pipeline(root);p.timeline=t;p.images={}
                out=render_incremental(p,hf,REPO,'fake','test-browser')
                return p,out
            a,first=render(timeline(audio));self.assertEqual(len(calls),2)
            before=file_hash(first);visual=a.render_report['visual_master']
            voice(880)
            b,second=render(timeline(audio));self.assertEqual(len(calls),2)
            self.assertEqual(b.render_report['visual_master'],visual)
            self.assertNotEqual(file_hash(second),before)
            c=copy.deepcopy(timeline(audio));c['shots'][1]['headline']='修改第二观点'
            d,_=render(c)
            self.assertEqual(d.render_report['rendered'],1)
            cached=Path(d.render_report['segments'][-1]['movie']);cached.write_bytes(b'corrupt')
            e,_=render(c);self.assertEqual(e.render_report['rendered'],1)
