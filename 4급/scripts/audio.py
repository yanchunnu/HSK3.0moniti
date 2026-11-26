"""Synthesize and encode the numbered exam recordings."""
import asyncio
import hashlib
from pathlib import Path
import re
import subprocess

import edge_tts
import numpy as np

from reference import FF, RATE, decode, recognize, recognizer

VOICES = {'m':('zh-CN-YunxiNeural','-14Hz'), 'f':('zh-CN-XiaoxiaoNeural','-19Hz')}
async def synthesize(events,cache):
    cache.mkdir(parents=True,exist_ok=True)
    sem=asyncio.Semaphore(5)
    async def create(voice,text):
        model,pitch = VOICES[voice]
        key=hashlib.sha256(f'{model}|{pitch}|+0%|{text}'.encode()).hexdigest()[:20]
        path=cache/(key+'.mp3')
        if path.is_file() and path.stat().st_size>1000:
            return (voice,text),path
        async with sem:
            for retry in range(4):
                try:
                    temp = path.with_suffix('.tmp')
                    await edge_tts.Communicate(text,model,rate='+0%',pitch=pitch).save(str(temp))
                    temp.replace(path)
                    return (voice,text),path
                except Exception:
                    if retry==3:
                        raise
                    await asyncio.sleep(2**retry)
    return dict(await asyncio.gather(*(create(*item) for item in sorted({(v,t) for v,t,_ in events}))))

def trim(path):
    samples,_=decode(path)
    peak = np.flatnonzero(np.abs(samples.astype('int32'))>300)
    assert peak.size, path
    return samples[max(0,peak[0]-320):min(len(samples),peak[-1]+321)]

def encode(events,clips,path,lead):
    pieces = [np.zeros(round(lead*RATE),dtype='<i2')]
    timeline = []
    cursor=len(pieces[0])
    for voice,text,gap in events:
        samples=clips[voice,text]
        timeline.append((cursor,cursor+len(samples),voice,text))
        silence=np.zeros(round(gap*RATE),dtype='<i2')
        pieces.extend((samples,silence))
        cursor+=len(samples)+len(silence)
    subprocess.run([FF,'-v','error','-y','-f','s16le','-ar',str(RATE),'-ac','1','-i','-',
                    '-c:a','libmp3lame','-b:a','64k',str(path)],
                   input=np.concatenate(pieces).tobytes(),check=True)
    return timeline,cursor

def normal(text):
    return ''.join(re.findall(r'[\u3400-\u9fff]|[a-z0-9]',text.lower())).translate(str.maketrans('妳她','你他'))

if __name__ == '__main__':
    from audio4 import main
    main()
