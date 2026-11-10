"""Add selected thought pauses at measured quiet seams, retaining original takes."""
import wave
import numpy as np
from .core import normalize, require


def plan(audio, rows, transcript):
    with wave.open(str(audio),'rb') as f:
        require(f.getnchannels()==1 and f.getsampwidth()==2,'停顿处理需要单声道PCM16')
        rate=f.getframerate(); samples=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(float)/32768
    text='';positions=[];words=transcript['words']
    for i,w in enumerate(words):
        token=normalize(w['text']);text+=token;positions.extend([i]*len(token))
    result=[]
    for row in rows:
        cue=normalize(row['after']);require(text.count(cue)==1,'停顿锚点必须唯一')
        idx=positions[text.index(cue)+len(cue)-1];word=words[idx]
        require(idx+1<len(words),'停顿必须位于句群之间，不能补片尾静音')
        end=word['end'];following=words[idx+1]['start']
        existing=max(0,following-end);extra=max(0,row['seconds']-existing)
        if extra<.02:continue
        lo=max(word['start'],end-.15);hi=min(len(samples)/rate,following+.08,end+.5)
        width=round(.02*rate);first=round(lo*rate);last=round(hi*rate)-width
        require(last>=first,'没有足够区间寻找停顿接缝')
        starts=np.arange(first,last+1,max(1,round(.005*rate)))
        rms=np.array([np.sqrt(np.mean(samples[a:a+width]**2)) for a in starts])
        k=int(np.argmin(rms));require(rms[k]<.0126,'停顿锚点附近无低能量接缝；不得切断发音')
        cut=int(starts[k]+width//2)
        result.append({'after':row['after'],'at':cut/rate,'insert_seconds':extra,'requested_gap_seconds':row['seconds'],
                       'measured_word_gap_seconds':existing,'seam_rms_dbfs':float(20*np.log10(max(rms[k],1e-10)))})
    require(all(a['at']<b['at'] for a,b in zip(result,result[1:])),'停顿顺序无效')
    return result


def apply(audio, edits, output):
    with wave.open(str(audio),'rb') as f:
        params=f.getparams();rate=f.getframerate();samples=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').copy()
    pieces=[];cursor=0
    for edit in edits:
        cut=round(edit['at']*rate);piece=samples[cursor:cut].copy();fade=min(round(.004*rate),len(piece))
        if fade:piece[-fade:]=(piece[-fade:]*np.linspace(1,0,fade)).astype('<i2')
        pieces.extend([piece,np.zeros(round(edit['insert_seconds']*rate),dtype='<i2')]);cursor=cut
        fade=min(round(.004*rate),len(samples)-cut)
        if fade:samples[cut:cut+fade]=(samples[cut:cut+fade]*np.linspace(0,1,fade)).astype('<i2')
    pieces.append(samples[cursor:])
    with wave.open(str(output),'wb') as f:
        f.setparams(params);f.writeframes(np.concatenate(pieces).astype('<i2').tobytes())
