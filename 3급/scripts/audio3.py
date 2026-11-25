"""Generate and check Level 3 listening and speaking tracks."""
import argparse
import asyncio
from collections import Counter
from pathlib import Path

import numpy as np

from audio import decode, encode, normal, recognize, recognizer, synthesize, trim, RATE
from level3 import EX, PARTS, parse

NUMBERS = '一 二 三 四 五 六 七 八 九 十 十一 十二 十三 十四 十五 十六 十七 十八 十九 二十 二十一 二十二 二十三 二十四 二十五 二十六 二十七 二十八 二十九 三十'.split()


def listening_events(number, blocks):
    welcome = '大家好！欢迎参加HSK三级考试。'
    intro = [('f', text, gap) for text, gap in [
        ('中文水平考试。HSK三点零三级。',.57),
        (f'全真模拟试卷{NUMBERS[number-1]}。',1.93),
        (welcome,1.7),(welcome,1.7),(welcome,1.8),
        ('HSK三级听力考试分三部分，共三十题。',1.18),
        ('请大家注意，听力考试现在开始。',1.54)]]
    groups = [([], 1, 10), ([], 11, 20), ([], 21, 30)]
    for part, (events, first, last) in enumerate(groups):
        events.append(('f', PARTS[part]+'。',1.1))
        for start, stop in [(first,15),(16,last)] if part==1 else [(first,last)]:
            instruction = ('听对话，选择最匹配的图片。','听对话和问题，选择正确答案。','听一段话，选择正确答案。')[part]
            events.extend([('f',f'第{NUMBERS[start-1]}到{NUMBERS[stop-1]}题。',.95),
                           ('f',instruction,1.05),('f','每题听两次。',1.8),('f','例如。',1.4)])
            example = EX[f'listening{part+1}']
            if start == 16:
                example = EX['listening2b']
            for n in (0,*range(start,stop+1)):
                if n:
                    if n == start:
                        events.append(('f',f'现在开始第{NUMBERS[n-1]}题。',1.9))
                    events.append(('f',NUMBERS[n-1]+'。',1.8))
                lines = blocks[n] if n else example
                for repeat in range(2):
                    for i, line in enumerate(lines):
                        prefix, sep, sentence = line.partition('：')
                        voice = {'女':'f','男':'m','问':'f'}.get(prefix,'m' if n%2 else 'f')
                        if not sep:
                            sentence = line
                        if i+1 == len(lines):
                            gap = 2.45 if not repeat or n==0 else 13.95
                        else:
                            gap = 1.9 if lines[i+1].startswith('问：') else 1.25
                        events.append((voice,sentence,gap))
    return intro, [group[0] for group in groups]


def speaking_events(oral):
    events = [('f','现在开始口语考试。口语考试约十五分钟，含六分钟准备时间。',1.5),
              ('f','第一部分，听后重复。请听句子并重复。每题十秒。',1.5)]
    for n in range(1,9):
        events.extend([('f',f'第{NUMBERS[n-1]}题。',1.2),('m' if n%2 else 'f',oral[n][0],10)])
    events.extend([('f','下面是准备时间，共六分钟。请阅读看图说话和回答问题。现在开始准备。',360),
                   ('f','准备时间结束。第二部分，看图说话。请用汉语描述图片中的人物、地点和动作。每题十五秒。',1.5)])
    events.extend(('f',f'第{NUMBERS[n-1]}题。',15) for n in range(9,14))
    events.append(('f','第三部分，回答问题。请用汉语回答。每题一分三十秒。',1.5))
    for n in range(14,16):
        events.extend([('f',f'第{NUMBERS[n-1]}题。',1.2),('m' if n%2 else 'f',oral[n][0],90)])
    return [*events,('f','口语考试结束。',1.4)]


def build(number, model):
    data=parse(number)
    intro, parts=listening_events(number,data[3])
    speaking=speaking_events(data[4])
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
        for label, events in zip(('전체','part1','part2','part3','part4'),(full,*parts,speaking)):
            path=out/f'HSK3.0_3급_제{number:02}회_{label}.mp3'
            timeline,size=encode(events,clips,path,1.05 if label=='전체' else .35)
            samples,_=decode(path)
            assert abs(len(samples)-size)<RATE*.06
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
    import json
    Path('tmp').mkdir(exist_ok=True)
    Path('tmp/audio-stats.json').write_text(json.dumps(tallies,ensure_ascii=False),encoding='utf8')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--level',required=True,type=int,choices=[3])
    ap.add_argument('--set',required=True,type=int,choices=range(1,11))
    ap.add_argument('--model',required=True,type=Path)
    args=ap.parse_args()
    build(args.set,args.model)
