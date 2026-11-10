import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

from youtube_studio import aliyun_voice as av
from youtube_studio.core import Blocked, StudioError
from youtube_studio.local_env import load_local_env


class AliyunVoice(unittest.TestCase):
    def test_env_is_literal_and_existing_environment_wins(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'ALIYUN_TTS_API_KEY':'existing'}, clear=True):
            p=Path(tmp)/'.env.local';p.write_text('ALIYUN_TTS_API_KEY=file\nDASHSCOPE_API_KEY="literal$(echo hi)"\nPATH=bad\n')
            load_local_env(p)
            self.assertEqual(os.environ['ALIYUN_TTS_API_KEY'],'existing')
            self.assertEqual(os.environ['DASHSCOPE_API_KEY'],'literal$(echo hi)')
            self.assertNotIn('PATH',os.environ)

    def test_key_never_sent_to_arbitrary_or_redirected_endpoint(self):
        for url in ['https://example.org/api/v1','https://cn-beijing.maas.qianwenaiapi.com.evil.org/api/v1',
                    'http://cn-beijing.maas.qianwenaiapi.com/api/v1','https://user@dashscope.aliyuncs.com/api/v1']:
            with self.assertRaises(StudioError):av.endpoint({'base_url':url})
        self.assertIsNone(av.NoRedirect().redirect_request(None,None,302,'',{},'https://example.org'))

    def test_post_timeout_not_retried_and_error_does_not_expose_key(self):
        opener=MagicMock();opener.open.side_effect=TimeoutError('private-detail')
        with patch.object(av,'credentials',return_value='private-key'), patch.object(av.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(StudioError) as raised:av.api({'base_url':av.DEFAULT_BASE},av.CUSTOMIZATION,{})
        self.assertEqual(opener.open.call_count,1)
        self.assertNotIn('private',str(raised.exception))

    def test_http_auth_failure_is_blocked(self):
        opener=MagicMock();opener.open.side_effect=urllib.error.HTTPError(av.DEFAULT_BASE,401,'denied',{},None)
        with patch.object(av,'credentials',return_value='private-key'), patch.object(av.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(Blocked):av.api({'base_url':av.DEFAULT_BASE},av.CUSTOMIZATION,{})

    def test_tts_payload_and_download_do_not_share_credentials(self):
        response=MagicMock();response.__enter__.return_value.read.return_value=b'audio'
        opener=MagicMock();opener.open.return_value=response
        config={'settings':{'model':'cosyvoice-v3.5-plus','voice_id':'cosyvoice-v3.5-plus-author-test','instruction':'自然解释'}}
        data={'output':{'audio':{'url':'https://assets.aliyuncs.com/audio.wav'}},'request_id':'test'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(av,'api',return_value=data) as call, patch.object(av.urllib.request,'build_opener',return_value=opener),patch.object(av,'duration',return_value=1):
            out=Path(tmp)/'out.wav';av.speech(config,{'text':'原稿','spoken_text':'百分之十'},out)
            self.assertEqual(out.read_bytes(),b'audio')
            self.assertEqual(call.call_args.args[2]['input']['text'],'百分之十')
            self.assertEqual(opener.open.call_args.args,('https://assets.aliyuncs.com/audio.wav',))
            self.assertNotIn('url',out.with_suffix('.receipt.json').read_text())

    def test_voice_cannot_switch_models_silently(self):
        with self.assertRaises(StudioError):
            av.speech({'settings':{'model':'cosyvoice-v3.5-plus','voice_id':'qwen-audio-3.0-tts-flash-author-x'}},{'text':'测试'},Path('/unused.wav'))

    def test_saved_response_recovers_download_without_second_post(self):
        config={'base_url':av.DEFAULT_BASE,'settings':{'model':'cosyvoice-v3.5-plus','voice_id':'cosyvoice-v3.5-plus-author-test'}}
        data={'output':{'audio':{'url':'http://bucket.oss-cn-beijing.aliyuncs.com/audio.wav'}},'request_id':'test'}
        opener=MagicMock();opener.open.side_effect=TimeoutError()
        with tempfile.TemporaryDirectory() as tmp, patch.object(av,'api',return_value=data) as post,patch.object(av.urllib.request,'build_opener',return_value=opener),patch.object(av,'duration',return_value=1):
            out=Path(tmp)/'pending.wav'
            with self.assertRaises(StudioError):av.speech(config,{'text':'测试'},out)
            self.assertTrue(out.with_suffix('.response.json').exists())
            response=MagicMock();response.__enter__.return_value.read.return_value=b'audio'
            opener.open.side_effect=None;opener.open.return_value=response
            av.speech(config,{'text':'测试'},out)
            self.assertEqual(post.call_count,1)
            self.assertEqual(opener.open.call_args.args[0],'https://bucket.oss-cn-beijing.aliyuncs.com/audio.wav')
