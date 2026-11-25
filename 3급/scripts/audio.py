"""Synthesize one numbered HSK 2 booklet and verify the encoded listening tracks."""
import argparse
import asyncio
import hashlib
from pathlib import Path
import re
import subprocess

import edge_tts
import numpy as np
import pymupdf as fitz

from reference import FF, RATE, decode, recognize, recognizer

PARTS = ('第一部分','第二部分','第三部分')
NUMBERS = '一 二 三 四 五 六 七 八 九 十 十一 十二 十三 十四 十五 十六 十七 十八 十九 二十 二十一 二十二 二十三 二十四 二十五'.split()
VOICES = {'m':('zh-CN-YunxiNeural','-14Hz'), 'f':('zh-CN-XiaoxiaoNeural','-19Hz')}
RANGES = ('第一到五题。','第六到十五题。','第十六到二十五题。')
INSTRUCTIONS = ('听一句话，选择正确图片。','听对话，选择最匹配的图片。','听对话和问题，选择正确答案。')

def parse(path):
    with fitz.open(path) as doc:
        lines = [line.strip() for page in doc[1:] for line in page.get_text().splitlines()
                 if re.fullmatch(r'[例\d.]+|[\u3400-\u9fff：，、。？！；]+',line.strip())
                 and line.strip() not in (*PARTS,'听力原文') and not line.strip().isdigit()]
    blocks = {}
    examples = 0
    for line in lines:
        if line == '例':
            examples += 1
            key = -examples
            blocks[key] = []
        elif re.fullmatch(r'\d+\.',line):
            key = int(line[:-1])
            blocks[key] = []
        else:
            blocks[key].append(line)
    assert sorted(blocks)==list(range(-3,0))+list(range(1,26))
    return blocks

def exam(number,blocks):
    intro = [('f',t,p) for t,p in [
        ('中文水平考试。',.52),('HSK三点零二级。',.85),
        (f'全真模拟试卷{NUMBERS[number-1]}。',2.1),
        ('大家好！欢迎参加HSK二级考试。',1.6),
        ('大家好！欢迎参加HSK二级考试。',1.6),
        ('大家好！欢迎参加HSK二级考试。',2.25),
        ('HSK二级听力考试分三部分，共二十五题。',1.34),
        ('请大家注意，听力考试现在开始。',2.07)]]
    parts = []
    for i,(start,stop) in enumerate([(1,6),(6,16),(16,26)]):
        events = [('f',PARTS[i]+'。',1.55),('f',RANGES[i],1),
                  ('f',INSTRUCTIONS[i],1.0),('f','每题听两次。',1.8),('f','例如。',2)]
        for n in [-i-1,*range(start,stop)]:
            if n in (1,6,11,16):
                start_text={1:'第一题',6:'第六到十题',11:'第十一到十五题',16:'第十六题'}[n]
                events.append(('f','现在开始'+start_text+'。',1.8))
            if n>0:
                events.append(('f',NUMBERS[n-1]+'。',1.7))
            for repeat in range(2):
                for j,line in enumerate(blocks[n]):
                    prefix,sep,spoken = line.partition('：')
                    if not sep:
                        spoken = line
                    voice = {'甲':'m','乙':'f','男':'m','女':'f','问':'f'}.get(prefix,
                                                                                    'm' if not repeat else 'f')
                    if j==len(blocks[n])-1:
                        gap = ([2.35,2.45,2.55][i] if not repeat else 2.45 if n<0 else 13.95)
                    else:
                        gap = 1.8 if blocks[n][j+1].startswith('问：') else 1.4
                    events.append((voice,spoken,gap))
        parts.append(events)
    return intro,parts,[('f','听力考试现在结束。',1.45)]

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

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('set_number',type=int,nargs='?',choices=range(1,11))
    parser.add_argument('--level',type=int,choices=(2,3),default=2)
    parser.add_argument('--set',dest='named_set',type=int,choices=range(1,11))
    parser.add_argument('--model',type=Path,required=True)
    args=parser.parse_args()
    args.set_number=args.named_set or args.set_number
    if args.set_number is None:
        parser.error('supply --set N')
    if args.level == 3:
        from audio3 import build as build_level3_audio
        return build_level3_audio(args.set_number,args.model)
    stem=f'HSK3.0_2급_제{args.set_number:02}회_'
    blocks=parse(Path('output')/(stem+'정답및해설.pdf'))
    intro,parts,end=exam(args.set_number,blocks)
    full=[*intro,*sum(parts,[]),*end]
    clips={key:trim(path) for key,path in asyncio.run(synthesize(full,Path('tmp/tts'))).items()}
    out=Path('output/audio')
    out.mkdir(parents=True,exist_ok=True)
    asr=recognizer(args.model)
    decoded_cache={}
    with (out/f'제{args.set_number:02}회_SenseVoice.tsv').open('w',encoding='utf8') as report:
        print('파일\t시작(초)\t음성\t대본\t전사\t결과',file=report)
        for label,events in zip(('전체',*PARTS),[full,*parts]):
            path=out/(stem+label+'.mp3')
            timeline,size=encode(events,clips,path,1.13 if label=='전체' else .35)
            samples,_=decode(path)
            assert abs(len(samples)-size)<RATE*.06
            matches = 0
            for a,b,v,t in timeline:
                # Decode every delivered file and check segment alignment before transferring the recognition.
                segment=samples[a:b]
                original=clips[v,t]
                correlation=np.corrcoef(segment.astype(float),original.astype(float))[0,1]
                assert correlation>.93,(label,t,correlation)
                # Verify the two encoded copies of the first example independently.
                if t in blocks[-1] or (v,t) not in decoded_cache:
                    decoded_cache[v,t]=recognize(asr,samples[max(0,a-1600):b+2000])
                heard=decoded_cache[v,t]
                match=normal(heard)==normal(t)
                matches+=match
                print(f'{label}\t{a/RATE:.2f}\t{v}\t{t}\t{heard}\t'+('일치' if match else '검토'),file=report)
            print(label,f'{len(samples)/RATE:.2f}s',path.stat().st_size,f'{matches}/{len(timeline)}')

if __name__=='__main__':
    main()
