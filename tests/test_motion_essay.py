import copy
import unittest
from youtube_studio.core import StudioError
from youtube_studio.essay import validate, render

class MotionEssay(unittest.TestCase):
    def setUp(self):
        self.shot={'id':'price-example','layout':'motion','variant':'valuation','hypothetical':True,'start':0,'end':8,
          'motion_objects':[
            {'id':'price','type':'value','x':200,'y':300,'w':500,'h':300,'value':200,'initial':True},
            {'id':'cost','type':'bar','x':200,'y':650,'w':500,'h':10,'initial':True}],
          'events':[{'target':'price','action':'count','cue':'降价','at':3,'from':200,'to':100},
                    {'target':'cost','action':'bar','cue':'降价','at':3,'from':1,'to':.5}]}

    def test_count_cannot_start_at_invented_value(self):
        validate(self.shot,'降价',set())
        s=copy.deepcopy(self.shot);s['events'][0]['from']=500
        with self.assertRaises(StudioError):validate(s,'降价',set())

    def test_count_and_bar_cannot_target_text(self):
        for action in ['count','bar']:
            s=copy.deepcopy(self.shot);s['motion_objects'][0]['type']='text';s['events'][0]['action']=action
            with self.assertRaises(StudioError):validate(s,'降价',set())

    def test_motion_does_not_bypass_hypothesis_or_sources(self):
        s={**self.shot,'hypothetical':False}
        with self.assertRaises(StudioError):validate(s,'降价',set())
        s={**self.shot,'variant':'record','source_id':'missing'}
        with self.assertRaises(StudioError):validate(s,'降价',set())

    def test_renderer_keeps_authored_values_without_template_copy(self):
        s={**self.shot,'headline':'不要自动显示这个标题'}
        body,motion=render(s,None,{})
        self.assertNotIn(s['headline'],body)
        self.assertIn('>200</span>',body)
        self.assertTrue(any('snap:{innerText:1}' in m for m in motion))
        self.assertTrue(any('scaleX' in m and '0.5' in m for m in motion))

    def test_bar_uses_authored_fill_and_retains_default(self):
        body,_=render(self.shot,None,{})
        self.assertIn('background:#b65b3c',body)
        s=copy.deepcopy(self.shot);s['motion_objects'][1]['color']='#aeb5a8'
        body,_=render(s,None,{})
        self.assertIn('background:#aeb5a8',body)
