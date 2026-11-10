import copy
import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import wave
from pathlib import Path
from unittest.mock import patch

from youtube_studio.core import Blocked, Cache, StudioError, normalize, read, source, validate_script, write
from youtube_studio.timing import align, srt, caption_text
from youtube_studio.pipeline import input_signature, Pipeline, master_audio, check_paper_edge
from youtube_studio import providers
from youtube_studio.editorial import review_script, storyboard_markdown


def script():
    return {"schema":"opinion-script/v1","title":"测试","sources":[],"units":[
        {"id":"u-one","text":"先看问题，再看答案。","shots":[
            {"id":"s-one","kind":"claim","cue":"","purpose":"提问","headline":"先看问题"},
            {"id":"s-two","kind":"claim","cue":"再看答案","purpose":"回答","headline":"再看答案"}]}]}


def words():
    return {"words":[{"text":c,"start":i*.5+.1,"end":i*.5+.5} for i,c in enumerate("先看问题再看答案")]}


class Contracts(unittest.TestCase):
    def test_clean_captions_preserve_numeric_meaning(self):
        self.assertEqual(caption_text('所以，不等于亏钱。','none'),'所以不等于亏钱')
        self.assertEqual(caption_text('比例为3.5%，而非35%。','none'),'比例为3.5%而非35%')
        self.assertEqual(caption_text('原稿。'),'原稿。')
        self.assertEqual(caption_text('约四点三亿。','none',{'四点三亿':'4.3 亿'}),'约4.3 亿')

    def test_headline_phrases_preserve_text_and_use_real_cues(self):
        doc = script(); unit=doc['units'][0]
        unit['shots']=[{'id':'s-title','kind':'claim','cue':'','purpose':'逐步解释','headline':'先看问题，再看答案。',
                        'headline_parts':[{'text':'先看问题，','cue':''},{'text':'再看答案。','cue':'再看答案','emphasis':True}]}]
        validate_script(doc)
        result = align(unit, words(), 4.5)
        self.assertEqual(result['shots'][0]['headline_times'],[0,2.1])
        unit['shots'][0]['headline_parts'][1]['cue']='案'
        with self.assertRaisesRegex(StudioError, '标题事件'): align(unit, words(), 4.2)
        unit['shots'][0]['headline_parts'][1]['text']='不同的意思'
        with self.assertRaises(StudioError): validate_script(doc)

    def test_mechanism_requires_qualitative_label_and_measured_order(self):
        doc = script()
        unit = doc['units'][0]
        unit['text'] = '新玩家进入，老对手扩产，利润受压。'
        unit['shots'] = [{'id':'s-market', 'kind':'mechanism', 'cue':'', 'purpose':'说明竞争',
                         'headline':'竞争进入', 'variant':'competition', 'hypothetical':True,
                         'note':'无量纲机制示意', 'labels':['进入','扩产','受压'],
                         'label_cues':['新玩家','老对手','利润']}]
        validate_script(doc)
        data = {'words':[{'text':c, 'start':i*.5, 'end':(i+1)*.5}
                         for i,c in enumerate(normalize(unit['text']))]}
        measured = align(unit, data, 7.5)['shots'][0]
        self.assertEqual(measured['label_times'], [0, 2.5, 5])
        unit['shots'][0]['hypothetical'] = False
        with self.assertRaises(StudioError): validate_script(doc)
        unit['shots'][0]['hypothetical'] = True
        unit['shots'][0]['label_cues'].reverse()
        with self.assertRaises(StudioError): align(unit, data, 7.5)

    def test_collage_secondary_asset_must_be_attributed_and_hashed(self):
        doc = script()
        shot = {'id':'s-photo','kind':'collage','cue':'','purpose':'建立场景','headline':'一个问题',
                'asset':'photo.jpg','provenance':{'source':'local'},'credit':'作者提供',
                'note':'情境示意','secondary_asset':'second.jpg','layout':'duo',
                'labels':['问题','答案'],'label_cues':['先看问题','再看答案']}
        doc['units'][0]['shots'] = [shot]
        with self.assertRaises(StudioError): validate_script(doc)
        shot['secondary_provenance'] = {'source':'local'}
        validate_script(doc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root/'script.json', doc)
            (root/'photo.jpg').write_bytes(b'photo')
            (root/'second.jpg').write_bytes(b'original')
            before = input_signature(root)
            (root/'second.jpg').write_bytes(b'replaced')
            self.assertNotEqual(before, input_signature(root))

    def test_editorial_profile_is_opt_in_but_complete_when_present(self):
        doc = script()
        validate_script(doc)
        self.assertTrue(review_script(doc)["warnings"])
        doc["editorial"] = {"question": "问题是什么？", "thesis": "先理解再回答", "takeaway": "依据是什么？"}
        with self.assertRaises(StudioError): validate_script(doc)
        doc["units"][0]["argument"] = {"role": "hook", "point": "明确问题", "basis": "先问后答", "boundary": "提问不等于证明"}
        validate_script(doc)
        report = review_script(doc)
        self.assertFalse(report["warnings"])
        self.assertTrue(all(v == "pending" for v in report["human_review"].values()))

    def test_nontext_purpose_is_rejected(self):
        doc = script(); doc["units"][0]["shots"][0]["purpose"] = {"irrelevant": True}
        with self.assertRaises(StudioError): validate_script(doc)

    def test_malformed_script_has_clear_failure(self):
        for doc in [[], {}, {"schema":"opinion-script/v1","title":"x","units":[None]}]:
            with self.assertRaises(StudioError): validate_script(doc)

    def test_simplified_and_traditional_match_without_changing_meaning(self):
        self.assertEqual(normalize("我們的選擇"),normalize("我们的选择"))
        self.assertNotEqual(normalize("不应该"),normalize("应该"))

    def test_repeated_or_backwards_cue_fails(self):
        doc=script()
        doc["units"][0]["shots"][1]["cue"]="看"
        with self.assertRaises(StudioError): validate_script(doc)
        doc=script()
        doc["units"][0]["shots"][0]["cue"]="再看答案"
        doc["units"][0]["shots"][1]["cue"]="先看问题"
        with self.assertRaises(StudioError): validate_script(doc)

    def test_fact_requires_known_source(self):
        doc=script()
        doc["units"][0]["claims"]=[{"kind":"fact","source_ids":["missing"]}]
        with self.assertRaises(StudioError): validate_script(doc)

    def test_quantity_math_and_bounds(self):
        doc=script()
        doc["units"][0]["shots"]=[{"id":"s-q","kind":"quantity","cue":"","purpose":"比例",
                                  "owned":10,"before":100,"after":120,"hypothetical":True,"change_cue":"再看答案"}]
        validate_script(doc)
        data=align(doc["units"][0],words(),4.5)
        self.assertAlmostEqual(data["shots"][0]["change_time"],2.1)
        doc["units"][0]["shots"][0]["after"]=0
        with self.assertRaises(StudioError): validate_script(doc)

    def test_source_cannot_escape_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(StudioError): source(Path(tmp),"../secret")


class Timing(unittest.TestCase):
    def test_inserted_speech_is_visible_in_review_without_overwriting_script(self):
        unit = {"id": "u-extra", "text": "我们先认真理解这个问题然后再慢慢考虑应该怎样回答", "shots": [
            {"id": "s-extra", "kind": "claim", "cue": "", "purpose": "理解", "headline": "先理解"}]}
        actual = unit["text"] + "啊"
        transcript = {"words": [{"text": c, "start": i*.2, "end": (i+1)*.2} for i,c in enumerate(actual)]}
        before = copy.deepcopy(unit)
        data = align(unit, transcript, len(actual)*.2)
        self.assertEqual(unit, before)
        self.assertEqual(data["differences"][0]["operation"], "insert")
        self.assertEqual(data["differences"][0]["recognized"], "啊")
        self.assertEqual(data["unmatched"], [])

    def test_storyboard_uses_audio_times_and_visual_purpose(self):
        doc = script(); data = align(doc["units"][0], words(), 4.5)
        board = storyboard_markdown(doc, {"units": [{"start": 0, "end": 4.5}], "shots": data["shots"]})
        self.assertIn("2.10–4.50", board)
        self.assertIn("回答", board)

    def test_label_reveals_use_measured_audio_and_stay_in_shot(self):
        unit=script()['units'][0]
        unit['shots']=[{'id':'s-pair','kind':'comparison','cue':'','purpose':'比较',
                       'labels':['问题','答案'],'label_cues':['先看问题','再看答案']}]
        self.assertEqual(align(unit,words(),4.5)['shots'][0]['label_times'],[.1,2.1])
        unit['shots'].append({'id':'s-late','kind':'claim','cue':'再看答案','purpose':'结尾','headline':'答案'})
        with self.assertRaises(StudioError): align(unit,words(),4.5)

    def test_actual_words_drive_scene_and_caption(self):
        data=align(script()["units"][0],words(),4.5)
        self.assertEqual(data["shots"][0]["start"],0)
        self.assertAlmostEqual(data["shots"][1]["start"],2.1)
        self.assertEqual(data["shots"][-1]["end"],4.5)
        self.assertIn("00:00:02,100",srt(data["captions"]))

    def test_short_caption_hold_respects_next_cue_and_unit_end(self):
        unit = {"id":"u", "text":"好。再见。", "shots":[{"id":"s","kind":"claim","cue":""}]}
        spoken = {"words":[{"text":"好","start":.1,"end":.2},
                           {"text":"再见","start":.4,"end":.55}]}
        result = align(unit, spoken, .8, minimum_display_seconds=.55)
        self.assertEqual([(c["start"], c["end"]) for c in result["captions"]], [(.1,.4),(.4,.8)])

    def test_wrong_negation_fails(self):
        unit={"id":"u-no","text":"不应该这样做","critical_terms":["不应该"],"shots":[{"id":"s-no","kind":"claim","cue":"","headline":"不应该","purpose":"结论"}]}
        with self.assertRaises(StudioError):
            align(unit,{"words":[{"text":"应该这样做","start":0,"end":3}]},3)

    def test_invalid_timestamps_fail(self):
        bad=words();bad["words"][2]["start"]=-1
        with self.assertRaises(StudioError): align(script()["units"][0],bad,4.5)

    def test_missing_event_cannot_use_interpolation(self):
        bad=words();bad["words"][4]["text"]="在"
        with self.assertRaises(StudioError): align(script()["units"][0],bad,4.5,threshold=.5)


class Recovery(unittest.TestCase):
    def test_cache_validates_bytes_and_reuses_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=Cache(tmp); calls=[]
            def action(out): calls.append(1);out.write_text("done")
            p=cache.task("voice",{"text":"hello"},".txt",action)
            self.assertEqual(p,cache.task("voice",{"text":"hello"},".txt",action))
            self.assertEqual(len(calls),1)
            p.write_text("corrupt")
            cache.task("voice",{"text":"hello"},".txt",action)
            self.assertEqual(len(calls),2)

    def test_uncertain_paid_request_does_not_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=Cache(tmp);calls=[]
            def fail(out): calls.append(1);raise TimeoutError("unknown")
            with self.assertRaises(TimeoutError): cache.task("image",{},".png",fail,paid=True)
            with self.assertRaises(Blocked): cache.task("image",{},".png",fail,paid=True)
            self.assertEqual(len(calls),1)

    def test_failed_auth_can_resume_without_uncertain_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=Cache(tmp)
            def auth(out): raise Blocked("missing credential")
            with self.assertRaises(Blocked): cache.task("voice",{},".wav",auth,paid=True)
            p=cache.task("voice",{},".wav",lambda out:out.write_text("valid"),paid=True)
            self.assertTrue(p.exists())

    def test_media_replacement_invalidates_input_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);doc=script();doc["units"][0]["audio"]="voice.wav"
            write(root/"script.json",doc);(root/"voice.wav").write_bytes(b"first")
            before=input_signature(root)
            (root/"voice.wav").write_bytes(b"second")
            self.assertNotEqual(before,input_signature(root))

    def test_failed_preflight_records_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);write(root/"config.json",{})
            with patch("youtube_studio.pipeline.doctor",return_value={"ok":False,"issues":["missing voice"]}):
                with self.assertRaises(Blocked): Pipeline(root).execute()
            self.assertEqual(read(root/"state.json")["status"],"blocked")


class ProviderErrors(unittest.TestCase):
    def test_ambiguous_post_is_not_repeated(self):
        error=urllib.error.HTTPError("https://api.openai.com",500,"error",{},None)
        with patch.dict("os.environ",{"STUDIO_TEST_KEY":"test-only"}), patch("urllib.request.urlopen",side_effect=error) as call:
            with self.assertRaises(StudioError): providers.api({"key_env":"STUDIO_TEST_KEY"},"audio/speech",{})
            self.assertEqual(call.call_count,1)

    def test_rate_limit_retry_is_bounded(self):
        error=urllib.error.HTTPError("https://api.openai.com",429,"limit",{},None)
        with patch.dict("os.environ",{"STUDIO_TEST_KEY":"test-only"}), patch("urllib.request.urlopen",side_effect=error) as call, patch("time.sleep"):
            with self.assertRaises(Blocked): providers.api({"key_env":"STUDIO_TEST_KEY"},"audio/speech",{})
            self.assertEqual(call.call_count,3)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"requires FFmpeg")
class AudioIntegration(unittest.TestCase):
    def test_export_edge_detects_white_or_black_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            for color, valid in [("0xf4f0e4", True), ("white", False), ("black", False)]:
                movie = Path(tmp) / f"{color}.mp4"
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                                f"color=c={color}:s=1920x1080:d=1:r=2", "-pix_fmt", "yuv420p", str(movie)], check=True)
                if valid:
                    self.assertEqual(len(check_paper_edge(movie, .5)["rgb"]), 3)
                else:
                    with self.assertRaises(StudioError): check_paper_edge(movie, .5)

    def test_dynamic_loudness_preserves_exact_pcm_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); raw=root/'part.wav'; output=root/'master.wav'
            subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i',
                            r'aevalsrc=if(lt(t\,6)\,0.3\,0.001)*sin(2*PI*440*t):s=48000:d=13.217979',
                            '-ac','1','-c:a','pcm_s16le',str(raw)],check=True)
            master_audio([raw],output)
            with wave.open(str(raw),'rb') as a, wave.open(str(output),'rb') as b:
                self.assertEqual(a.getnframes(),b.getnframes())
                self.assertEqual(b.getframerate(),48000)
                self.assertEqual(b.getnchannels(),2)

    def test_visual_edits_reuse_voice_and_master_preserves_channels(self):
        calls=[]
        def synth(config,unit,out,mode):
            calls.append(unit["text"])
            with wave.open(str(out),"wb") as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000)
                f.writeframes(b''.join(struct.pack('<h',int(3500*math.sin(i*2*math.pi*440/48000))) for i in range(96000)))
        with tempfile.TemporaryDirectory() as tmp, patch("youtube_studio.providers.speech",side_effect=synth):
            root=Path(tmp)
            write(root/"config.json",{"voice":{"provider":"say"},"audio":{"lufs":-18}})
            p=Pipeline(root,"preview");p.doc=script();p.voice()
            q=Pipeline(root,"preview");q.doc=script();q.doc["units"][0]["shots"][0]["headline"]="只改画面";q.voice()
            self.assertEqual(len(calls),1)
            with wave.open(str(q.master),"rb") as f:
                self.assertEqual(f.getnchannels(),2)
                self.assertAlmostEqual(f.getnframes()/f.getframerate(),2,places=3)
            measured=subprocess.run(["ffmpeg","-hide_banner","-nostats","-i",str(q.master),"-af","loudnorm=print_format=json","-f","null","-"],capture_output=True,text=True)
            data,_=json.JSONDecoder().raw_decode(measured.stderr[measured.stderr.rfind('{'):])
            self.assertLess(abs(float(data['input_i'])+18),1)
            slowed=Pipeline(root,"preview");slowed.doc=script()
            slowed.config['audio']['voice_speed']=.9
            slowed.voice()
            self.assertEqual(len(calls),1, 'Local speed changes must not resubmit TTS')
            with wave.open(str(slowed.voices[0]),'rb') as f:
                seconds=f.getnframes()/f.getframerate()
                self.assertAlmostEqual(seconds,2/.9,delta=.04)
                f.setpos(24000)
                samples=struct.unpack('<48000h',f.readframes(48000))
                crossings=sum(a<=0<b for a,b in zip(samples,samples[1:]))
                self.assertAlmostEqual(crossings,440,delta=2, msg='Time stretch must preserve pitch')
            r=Pipeline(root,"preview");r.doc=script();r.doc["units"][0]["text"]="换一句口播。";r.voice()
            self.assertEqual(len(calls),2)


if __name__ == "__main__": unittest.main()
