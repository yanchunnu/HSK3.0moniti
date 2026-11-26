"""Extract the Chinese exam and answers from an original numbered PDF."""
import re
import subprocess
from pathlib import Path

import pymupdf as fitz

def compact(text):
    return re.sub(r'\s+', '', text)

def choices(text):
    return tuple(s.strip() for s in re.split(r'(?<!\S)[A-F]\s+', text)[1:])

def parse(number):
    path, = Path('input/sets').glob(f'*제{number:02}회*.pdf')
    doc = fitz.open(path)
    from os import environ
    tool = environ.get('PDFTOTEXT', 'pdftotext')
    raw = subprocess.check_output([tool, '-layout', '-enc', 'UTF-8', str(path), '-'],
                                  stderr=subprocess.DEVNULL).decode('utf8')
    pages = raw.split('\f')
    questions = '\n'.join(pages[1:10])
    solutions = '\n'.join(pages[10:])
    grid = solutions.split('빠른 정답표')[1].split('65–69')[0]
    keys = {int(n): a for n,a in re.findall(r'\b(\d{1,2})\s*([A-F])\b', grid)}
    marked = {int(n): a for n,a in re.findall(r'(?m)^\s*(\d+)\. 정답 ([A-F])',solutions)}
    assert list(sorted(keys)) == list(range(1,65))
    assert all(marked.get(n) == a for n,a in keys.items()), set(keys.items())-set(marked.items())
    transcripts = {}
    for n,end,body in re.findall(r'(?ms)^\s*(\d+)(?:[–-](\d+))?번 · 듣기 대본\s*\n(.*?)^\s*한국어 해석',solutions):
        lines = [line.strip() for line in body.strip().splitlines()]
        transcripts[int(n)] = lines if all(re.match(r'[男女]：', line) for line in lines) else [compact(body)]
    asks = {int(n): q.strip() for n,q in re.findall(r'(?m)^\s*(\d+)\. 정답 [A-D]\s*\n\s*(问：.+)',solutions) if int(n)<=32}
    assert sorted(transcripts) == [*range(1,22),23,25,27,29,31], sorted(transcripts)
    assert sorted(asks) == list(range(1,33))
    listen = {}
    for n in range(1,33):
        row = re.search(rf'(?m)^\s*{n}\.\s*\n\s*(A .+)\n\s*(C .+)', questions)
        listen[n] = choices(' '.join(row.groups()))
        assert len(listen[n])==4
    bank = re.findall(r'(?m)^\s*(A [^\n]+ / F [^\n]+)',questions)
    words = [choices(v.replace(' / ', ' ')) for v in bank]
    fill = {}
    for n,body in re.findall(r'(?ms)^\s*(3[3-9]|4[0-2])\. (.*?)(?=^\s*(?:\d+\.|A 提前 /|阅读 第二部分)|\Z)',questions):
        fill[int(n)] = tuple(line.strip() for line in body.strip().splitlines() if line.strip())
    reading = []
    for scope, body in re.findall(r'(?ms)^\s*第(4[3-9]|5[0-6](?:[–-]5[1-7])?)题\s*\n(.*?)(?=^\s*第\d+[–-]?\d*题\s*$|^\s*阅读 第三部分|\Z)', questions):
        clean = re.sub(r'(?m)^.*(?:HSK 3\.0|^\s+\d+\s*$).*\n?', '', body)
        first = re.search(r'(?m)^\s*\d+\. ',clean)
        passage = compact(clean[:first.start()])
        rows = []
        for n,q,a,c in re.findall(r'(?m)^\s*(\d+)\. (.+)\n\s*(A .+)\n\s*(C .+)',clean):
            rows.append((int(n),q.strip(),choices(a+' '+c)))
        reading.append((scope,passage,rows))
    assert [n for _,_,rows in reading for n,_,_ in rows] == list(range(43,58)), reading
    blocks = []
    for body in re.findall(r'(?ms)([^\n]*（(?:58|61)）_+.*?)(?=^\s*A )', questions):
        blocks.append(body)
    sentence_section = questions.split('第58–64题')[1].split('写作 第一部分')[0]
    sentence_section = '\n'.join(line.strip() for line in sentence_section.splitlines()
                                 if re.match(r'^\s*(?:[\u3400-\u9fff，]|[A-D] )',line))
    sentences = [(compact(p),tuple(v.strip() for v in a.splitlines()))
                 for p,a in re.findall(r'(?ms)(.+?)\n(A .+?\n(?:B .+?\n)(?:C [^\n]+)(?:\nD [^\n]+)?)\s*(?=\n|\Z)',sentence_section)]
    assert len(words)==len(sentences)==2 and sorted(fill)==list(range(33,43)), (words,sentences,fill)
    hints = dict((int(n),w) for n,w in re.findall(r'(6[5-9])\. 提示词：(\S+)', questions))
    essay = re.search(r'请写一篇不少于80字的短文，[^\n]+',questions)[0].strip()
    writing = {}
    for n,a,b in re.findall(r'(?m)^\s*(6[5-9])\. [^\n]+\n\s*([^\n]+)\n[^\n]+\n\s*([^\n]+)', solutions):
        writing[int(n)] = [a.strip(),b.strip()]
    writing[70] = [compact(re.search(r'(?s)모범답안 · 한자 [^\n]+\n(.*?)한국어 해석',solutions)[1])]
    oral = {}
    for n in (71,72,73,74,75):
        segment = re.split(rf'口语 第[一二三]部分 · {n}번\s*\n',solutions)[1]
        start = {71:'낭독 대본',72:'낭독 대본',73:'사진 연결 이야기 · 2분',74:'2분 답변 모범 예시',75:'2분 답변 모범 예시'}[n]
        end = {71:'한국어 해석',72:'한국어 해석',73:'사진 순서:',74:'구성 ',75:'구성 '}[n]
        answer = compact(segment.split(start,1)[1].split(end,1)[0])
        if n>=74:
            question = re.search(rf'(?m)^\s*{n}\. (.+)',questions)[1].strip()
            assert segment.strip().startswith(question)
            oral[n] = [question,answer]
        else:
            oral[n] = [answer]
    assert sorted(writing)==list(range(65,71))
    assert all(not re.search('[가-힣]',v) for data in [writing,oral,transcripts] for vs in data.values() for v in vs), oral
    return doc, keys, transcripts, asks, listen, words, fill, reading, sentences, hints, essay, writing, oral

