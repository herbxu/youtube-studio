import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from youtube_studio.core import StudioError, validate_script
from youtube_studio import aliyun_voice as av
from youtube_studio.essay import validate, render

class EssayProduction(unittest.TestCase):
    def test_clean_diagram_has_no_media_dependency_and_preserves_prior_income(self):
        shot={'id':'risk','variant':'risk','layout':'clean','headline':'同一份股权','credit':'',
              'hypothetical':True,'price':100,'income':5,'previous_income':10,'note':'假设',
              'start':20,'end':30,'events':[{'action':'reveal','target':'income','cue':'降为五元','at':24}]}
        validate(shot,'降为五元',set())
        body,motion=render(shot,None,{})
        self.assertNotIn('<img',body)
        self.assertNotIn('coin-row',body)
        self.assertIn('risk-income-before',body)
        self.assertIn('>10<small>',body)
        self.assertIn('>5<small>',body)
        self.assertTrue(any('risk-income-before' in m and ',24)' in m for m in motion))
        with self.assertRaises(StudioError):validate({**shot,'asset':'unrelated.jpg'},'降为五元',set())
        with self.assertRaises(StudioError):validate({**shot,'events':[{'target':'coins','action':'reveal'}]},'',set())

    def test_record_needs_real_source_and_value_needs_hypothesis(self):
        record={'variant':'record','asset':'photo.jpg','provenance':{'kind':'licensed'},'headline':'我的复盘','credit':'作者','quote':'过去的教训','record_date':'2024年之前','source_id':'missing'}
        with self.assertRaises(StudioError):validate(record,'',{'actual'})
        record['source_id']='actual';validate(record,'',{'actual'})
        value={**record,'variant':'valuation','price':100,'income':10}
        with self.assertRaises(StudioError):validate(value,'',{'actual'})
        value['hypothetical']=True;validate(value,'',{'actual'})

    def test_real_payload_contains_delivery_without_polluting_spoken_text(self):
        c={'settings':{'model':'qwen-audio-3.0-tts-plus','voice_id':'qwen-audio-3.0-tts-plus-test','instruction':'自然讲述','use_unit_delivery':True}}
        u={'text':'我以前犯过错误。','delivery':'坦然回忆，不逐字停顿。'}
        data={'output':{'audio':{'data':'YXVkaW8='}},'request_id':'local-test'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(av,'api',return_value=data) as call,patch.object(av,'duration',return_value=1):
            out=Path(tmp)/'result.wav';av.speech(c,u,out)
            inp=call.call_args.args[2]['input'];self.assertEqual(inp['text'],u['text']);self.assertIn(u['delivery'],inp['instruction'])
            self.assertTrue(json.loads(out.with_suffix('.receipt.json').read_text())['unit_delivery_enabled'])
            # Recovering exactly the same accepted request never creates a second billable POST.
            av.speech(c,u,out);self.assertEqual(call.call_count,1)
