"""Measured Whisper attention/DTW timings, with separate unconstrained ASR evidence."""
import difflib
from pathlib import Path

from .core import duration, file_hash, normalize, read, require, write
from . import providers


def align_reference(config, audio, text, output):
    from faster_whisper.audio import decode_audio
    from faster_whisper.tokenizer import Tokenizer

    length = duration(audio)
    require(0 < length <= 29, '强制对齐单元需在29秒以内；按语义拆分长段落，不按字数编造时间')
    asr_config = {**config, 'provider': 'faster-whisper'}
    independent_path = output.with_suffix('.independent-asr.json')
    providers.transcribe(asr_config, audio, independent_path)
    independent = read(independent_path)
    actual = ''.join(w['text'] for w in independent['words'])
    expected, recognized = normalize(text), normalize(actual)
    matcher = difflib.SequenceMatcher(None, expected, recognized, autojunk=False)
    differences = [{'operation':tag, 'expected':expected[a:b], 'recognized':recognized[c:d]}
                   for tag,a,b,c,d in matcher.get_opcodes() if tag != 'equal']
    model = providers._models[(config.get('model', 'small'), config.get('allow_download', False))]
    tokenizer = Tokenizer(model.hf_tokenizer, model.model.is_multilingual, task='transcribe', language='zh')
    samples = decode_audio(str(audio), sampling_rate=16000)
    features = model.feature_extractor(samples)
    raw = model.find_alignment(tokenizer, [tokenizer.encode(text)], model.encode(features),
                               [min(features.shape[-1],3000)])[0]
    measured, pending, records = [], '', []
    for word in raw:
        records.append({k:float(v) if k in {'start','end','probability'} else v for k,v in word.items() if k != 'tokens'})
        token = word['word']
        if not normalize(token):
            continue
        start, end = max(0, float(word['start'])), min(length, float(word['end']))
        if end <= start:
            # Attach zero-duration tokens to a measured neighbour, not invented time.
            if measured: measured[-1]['text'] += token
            else: pending += token
            continue
        measured.append({'text':pending+token, 'start':start, 'end':end, 'probability':float(word['probability'])})
        pending = ''
    require(measured and not pending, '声学对齐没有返回可用的词时间')
    write(output, {'method':'faster-whisper/'+config.get('model','small')+' cross-attention DTW forced alignment',
          'reference_constrained':True, 'reference_text':text, 'audio_sha256':file_hash(audio),
          'words':measured, 'raw_alignment':records,
          'independent_asr':{'model':independent.get('model'), 'text':actual,
                             'match_ratio':matcher.ratio(), 'differences':differences,
                             'words':independent['words']},
          'note':'对齐文本受原稿约束；覆盖率不代表独立识别准确率。独立ASR差异另存，待审听。'})
