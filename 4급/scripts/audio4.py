"""Assemble one set of listening and speaking audio."""
import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

import numpy as np

from audio import decode, encode, normal, recognize, recognizer, synthesize, trim, RATE
from source4 import parse

EX = json.loads(Path(__file__).with_name('例01.json').read_text(encoding='utf-8-sig'))
DIGITS = '零一二三四五六七八九'

def chinese(n):
    if n < 10:
        return DIGITS[n]
    tens, ones = divmod(n, 10)
    return (DIGITS[tens] if tens > 1 else '') + '十' + (DIGITS[ones] if ones else '')

def listening_events(level, number, blocks, questions):
    grade = chinese(level) + '级'
    welcome = f'大家好！欢迎参加HSK{grade}考试。'
    intro = [('f', text, gap) for text, gap in [
        (f'中文水平考试。HSK三点零{grade}。',.5),
        (f'全真模拟试卷{chinese(number)}。',1.9),
        (welcome,1.7),(welcome,1.6),(welcome,2.0),
        (f'HSK{grade}听力考试分两部分，共三十二题。',1.1),
        ('请大家注意，听力考试现在开始。',1.6)]]
    parts = [[], []]
    def announce(events, text, gap=1.8):
        events.append(('f',text,gap))
    def speak(events, lines, n, gap):
        for i,line in enumerate(lines):
            prefix, sep, sentence = line.partition('：')
            voice = {'女':'f','男':'m','问':'f'}.get(prefix,'m' if n%2 else 'f')
            next_gap = 1.85 if i+1<len(lines) and lines[i+1].startswith('问：') else 1.05
            events.append((voice,sentence if prefix in ('女','男','问') else line,
                           gap if i+1==len(lines) else next_gap))
    for part, first, last, example in [(0,1,7,'l1'),(0,8,14,'l1b'),(1,15,20,'l2'),(1,21,32,'l2b')]:
        events = parts[part]
        if first in (1,15):
            announce(events,('第一部分。','第二部分。')[part],1.3)
        announce(events,f'第{chinese(first)}到{chinese(last)}题。',.9)
        announce(events,('听对话，选择正确答案。','听短文，选择正确答案。')[part],1.0)
        announce(events,'每题听一次。',1.3)
        announce(events,'例如。',1.6)
        sample = EX[example]
        speak(events,sample['lines'],1,1.8)
        if 'second' in sample:
            speak(events,[sample['second']],1,2.2)
        limit = first+1 if first==21 else first
        tail = f'到{chinese(limit)}' if limit!=first else ''
        announce(events,f'现在开始第{chinese(first)}{tail}题。')
        step = 2 if first==21 else 1
        for n in range(first,last+1,step):
            if step==1:
                announce(events,chinese(n)+'。')
                speak(events,blocks[n]+[questions[n]],n,15)
            else:
                announce(events,f'第{chinese(n)}到{chinese(n+1)}题。')
                speak(events,blocks[n],n,1.85)
                for m in (n,n+1):
                    announce(events,chinese(m)+'。',1.2)
                    speak(events,[questions[m]],m,15)
    return intro, parts

def speaking_events(oral):
    events = [('f','现在开始口语考试。口语考试分三部分，共五题。',1.5),
              ('f','第一部分，听后复述。请听一段话，然后用自己的话复述。每题四十秒。',1.5)]
    for n in (71,72):
        events.extend([('f',f'第{chinese(n)}题。',1.2),
                       ('m' if n%2 else 'f',oral[n][0],40)])
    events.extend([('f','第二部分，看图说话。请按顺序看三张图，并讲一个故事。时间为两分钟。',1.5),
                   ('f','第七十三题。',120),
                   ('f','第三部分，回答问题。请用汉语回答。每题两分钟。',1.5)])
    for n in (74,75):
        events.extend([('f',f'第{chinese(n)}题。',1.2),
                       ('m' if n%2 else 'f',oral[n][0],120)])
    return [*events,('f','口语考试结束。',1.4)]

def build(level, number, model):
    data=parse(number)
    intro, parts=listening_events(level,number,data[2],data[3])
    speaking=speaking_events(data[-1])
    transition=[('f','听力考试结束。下面进行口语考试。',2.0)]
    full=[*intro,*sum(parts,[]),*transition,*speaking]
    clips={key:trim(path) for key,path in asyncio.run(synthesize(full,Path('tmp/tts'))).items()}
    asr=recognizer(model)
    out=Path('output/audio')
    out.mkdir(parents=True,exist_ok=True)
    cache={}
    tallies={}
    with (out/f'제{number:02}회_SenseVoice.tsv').open('w',encoding='utf8') as report:
        print('파일\t시작(초)\t끝(초)\t음성\t대본\t전사\t결과',file=report)
        for label, events in zip(('전체','part1','part2','part3'),(full,*parts,speaking)):
            path=out/f'HSK3.0_{level}급_제{number:02}회_{label}.mp3'
            timeline,size=encode(events,clips,path,1.05 if label=='전체' else .35)
            samples,_=decode(path)
            assert abs(len(samples)-size)<RATE*.06
            long_gaps = []
            for event, (_,end,_,_) in zip(events,timeline):
                gap = event[2]
                if gap >= 10:
                    silence = samples[end+int(.12*RATE):end+int((gap-.12)*RATE)]
                    assert len(silence)==int((gap-.12)*RATE)-int(.12*RATE)
                    assert np.max(np.abs(silence.astype('int32'))) <= 16, (label,event)
                    long_gaps.append(gap)
            expected = {'전체':[15]*32+[40,40,120,120,120], 'part1':[15]*14,
                        'part2':[15]*18, 'part3':[40,40,120,120,120]}
            assert long_gaps==expected[label], (label,long_gaps)
            matches=Counter()
            for a,b,v,t in timeline:
                segment=samples[a:b]
                correlation=np.corrcoef(segment.astype(float),clips[v,t].astype(float))[0,1]
                assert correlation>.93,(label,t,correlation)
                if (v,t) not in cache:
                    cache[v,t]=recognize(asr,samples[max(0,a-1600):b+2000])
                heard=cache[v,t]
                match=normal(heard)==normal(t)
                matches[match]+=1
                print(f'{label}\t{a/RATE:.2f}\t{b/RATE:.2f}\t{v}\t{t}\t{heard}\t'+('일치' if match else '검토'),file=report)
            tallies[label]=(len(samples)/RATE,path.stat().st_size,matches[True],len(timeline))
            print(label,tallies[label],flush=True)
    Path('tmp').mkdir(exist_ok=True)
    Path('tmp/audio-stats.json').write_text(json.dumps(tallies,ensure_ascii=False),encoding='utf8')



def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--level', required=True, type=int, choices=[4])
    ap.add_argument('--set', required=True, type=int, choices=range(1,11))
    ap.add_argument('--model', required=True, type=Path)
    args = ap.parse_args()
    build(args.level,args.set,args.model)

if __name__ == '__main__':
    main()
