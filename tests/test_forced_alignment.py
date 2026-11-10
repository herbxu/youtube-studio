import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from youtube_studio.core import StudioError, read, write
from youtube_studio.forced_alignment import align_reference


class ForcedAlignment(unittest.TestCase):
    def test_measured_timings_keep_independent_recognition_errors(self):
        model = MagicMock()
        model.feature_extractor.return_value.shape = (80, 250)
        model.find_alignment.return_value = [[
            {'word': '增', 'start': 0, 'end': 0, 'probability': .8},
            {'word': '发', 'start': .3, 'end': .6, 'probability': .9},
            {'word': '后', 'start': .6, 'end': .6, 'probability': .9},
            {'word': '。', 'start': .6, 'end': .6, 'probability': .9},
        ]]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / 'input.wav'
            audio.write_bytes(b'fixture audio')
            output = root / 'aligned.json'
            def independent(config, source, destination):
                write(destination, {'model': 'small', 'words': [
                    {'text': '蒸发后', 'start': .2, 'end': .7}]})
            with patch('youtube_studio.forced_alignment.duration', return_value=2.5), \
                 patch('youtube_studio.forced_alignment.providers.transcribe', side_effect=independent), \
                 patch.dict('youtube_studio.providers._models', {('small', False): model}), \
                 patch('faster_whisper.audio.decode_audio'), \
                 patch('faster_whisper.tokenizer.Tokenizer'):
                align_reference({'model': 'small'}, audio, '增发后。', output)
            result = read(output)
            self.assertTrue(result['reference_constrained'])
            self.assertEqual(result['words'][0]['text'], '增发后')
            self.assertEqual((result['words'][0]['start'], result['words'][0]['end']), (.3, .6))
            self.assertEqual(result['independent_asr']['text'], '蒸发后')
            self.assertEqual(result['independent_asr']['differences'][0]['recognized'], '蒸')
            self.assertLess(result['independent_asr']['match_ratio'], 1)

    def test_long_audio_is_rejected_before_transcription(self):
        with patch('youtube_studio.forced_alignment.duration', return_value=30), \
             patch('youtube_studio.forced_alignment.providers.transcribe') as transcribe:
            with self.assertRaises(StudioError):
                align_reference({}, Path('input.wav'), '不能均分时间', Path('output.json'))
            transcribe.assert_not_called()

    def test_empty_acoustic_result_is_not_fabricated(self):
        model = MagicMock()
        model.feature_extractor.return_value.shape = (80, 100)
        model.find_alignment.return_value = [[]]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'aligned.json'
            with patch('youtube_studio.forced_alignment.duration', return_value=1), \
                 patch('youtube_studio.forced_alignment.providers.transcribe',
                       side_effect=lambda c, a, p: write(p, {'words': []})), \
                 patch.dict('youtube_studio.providers._models', {('small', False): model}), \
                 patch('faster_whisper.audio.decode_audio'), \
                 patch('faster_whisper.tokenizer.Tokenizer'):
                with self.assertRaises(StudioError):
                    align_reference({}, Path('input.wav'), '测试', output)
            self.assertFalse(output.exists())
