import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from youtube_studio.core import StudioError, validate_script, write, file_hash
from youtube_studio.explain import validate_shot, validate_scenes, render_objects
from youtube_studio.planning import quality_report, input_refs
from youtube_studio.library import audit, freeze, search
from youtube_studio.timing import align


def scene():
    return {'id':'s-one','kind':'object_scene','cue':'','purpose':'保持身份解释关系','headline':'同一个对象','note':'关系示意',
            'scene_id':'test','variant':'relation','objects':[{'id':'a','label':'公司','x':200,'y':400},{'id':'b','label':'项目','x':1000,'y':400}],
            'events':[{'action':'reveal','target':'a','cue':''},{'action':'reveal','target':'b','cue':'项目'},{'action':'connect','target':'a','to':'b','cue':'连接'}]}


class Explain(unittest.TestCase):
    def test_persistent_scene_rejects_resets_and_noncontiguous_use(self):
        first=scene();second=copy.deepcopy(first);second['id']='s-two';second['events']=[{'action':'emphasize','target':'b','cue':''}]
        validate_scenes([first,second])
        with self.assertRaises(StudioError):validate_scenes([first,{'kind':'claim'},second])
        second['events']=[{'action':'reveal','target':'b','cue':''}]
        with self.assertRaises(StudioError):validate_scenes([first,second])

    def test_invalid_event_and_outside_highlight_fail(self):
        s=scene();s['events']=[{'action':'move','target':'a','cue':'','x':1900,'y':400}]
        with self.assertRaises(StudioError):validate_shot(s,'公司项目连接',set())
        e={'id':'s-evidence','kind':'evidence','headline':'原文','note':'原文','asset':'a.png','provenance':{'source':'test'},'credit':'来源','source_id':'src','page':1,'source_sha256':'a'*64,'events':[{'action':'highlight','cue':'','rect':[.8,.2,.5,.1],'label':'超界'}]}
        with self.assertRaises(StudioError):validate_shot(e,'原文',{'src'})

    def test_connected_objects_cannot_move_and_unknown_targets_fail(self):
        s=scene();s['events'].append({'action':'move','target':'b','x':1200,'y':400,'cue':''})
        with self.assertRaises(StudioError):validate_scenes([s])
        s['events']=[{'action':'emphasize','target':'b','cue':''}]
        with self.assertRaises(StudioError):validate_scenes([s])

    def test_render_once_across_units(self):
        first=scene();first.update(start=0,end=5);first['events']=[dict(e,at=i) for i,e in enumerate(first['events'])]
        second=copy.deepcopy(first);second.update(id='s-two',start=5,end=10,events=[{'action':'emphasize','target':'b','cue':'','at':6}])
        with tempfile.TemporaryDirectory() as tmp:
            html,motion=render_objects([first,second],Path(tmp),{})
        self.assertEqual(html.count('id="world-test-a"'),1)
        self.assertEqual(html.count('id="world-test-b"'),1)
        self.assertIn('data-duration="10"',html)

    def test_event_needs_real_time_and_hold(self):
        s=scene();s['events']=[{'action':'reveal','target':'a','cue':'连接','duration':1.5}]
        unit={'id':'u-one','text':'公司项目连接','shots':[s]}
        data={'words':[{'text':c,'start':i*.5,'end':(i+1)*.5} for i,c in enumerate(unit['text'])]}
        with self.assertRaises(StudioError):align(unit,data,3)
        self.assertEqual(input_refs({'shots':[dict(s,objects=[{'id':'a','asset':'photo.png'}])]}),['photo.png'])

    def test_quality_requires_current_bound_evidence_and_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);doc={'units':[]};qa={'machine_checks':'passed','movie_sha256':'new','input_signature':'current'}
            checks={k:{'status':'passed','evidence':['reviewed at actual times']} for k in ['content','audio','visual','engineering','efficiency']}
            write(root/'review.json',{'movie_sha256':'old','input_signature':'current','checks':checks})
            self.assertEqual(quality_report(root,doc,qa=qa)['status'],'needs_review')
            write(root/'review.json',{'movie_sha256':'new','input_signature':'current','checks':checks})
            self.assertEqual(quality_report(root,doc,qa=qa)['status'],'reviewed')
            self.assertEqual(quality_report(root,doc,qa=qa,mode='preview')['status'],'needs_review')

    def test_library_missing_changed_freeze_and_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'photo.png';src.write_bytes(b'original');index=root/'index.json'
            row={'id':'asset','type':'image','path':'photo.png','sha256':file_hash(src),'subject':'公司','action':'融资','usage':'illustrative','license_name':'user provided','recovery':'user original'}
            write(index,{'schema':'opinion-library/v1','assets':[row]})
            self.assertTrue(audit(index,root)['ok']);self.assertEqual(len(search('融资',index)),1)
            result=freeze('asset',root/'episode',index,root);dest=root/'episode'/result['path']
            self.assertEqual(dest.read_bytes(),b'original');src.write_bytes(b'changed')
            self.assertEqual(audit(index,root)['assets'][0]['status'],'changed')
            with self.assertRaises(StudioError):freeze('asset',root/'episode',index,root)
            src.unlink();self.assertEqual(audit(index,root)['assets'][0]['status'],'missing')
            self.assertEqual(dest.read_bytes(),b'original')
