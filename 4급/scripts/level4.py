"""Lay out a numbered HSK exam and separate answer booklet."""
import argparse
import json
import re
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw
from reportlab.graphics.barcode import qr
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics

from booklet import CELL_WIDTH, Layout, PARTS
from content_model4 import load

EX = json.loads(Path(__file__).with_name('例01.json').read_text(encoding='utf-8-sig'))
OPTION_GAP = 14
RIGHT = 352

def width(value):
    return pdfmetrics.stringWidth(value,'CN',10)

def wrap(value, limit):
    while value:
        stop = len(value)
        while width(value[:stop]) > limit:
            stop -= 1
        while stop < len(value) and (value[stop] in '，。？！；、）：”' or value[stop-1] in '（“'):
            stop -= 1
        # Keep numbered blanks intact when a line ends near one.
        blank = re.search(r'（\d*[^）]*$',value[:stop])
        if blank and blank.start():
            stop = blank.start()
        assert stop > 0, value
        yield value[:stop]
        value = value[stop:]

def page_ranges(heights, capacity, first_extra=0):
    best = {len(heights): (0, 0, [])}
    for start in reversed(range(len(heights))):
        available = capacity - (first_extra if start == 0 else 0)
        candidates = []
        for end in range(start+1, len(heights)+1):
            spare = available - sum(heights[start:end])
            if spare >= 0 and end in best:
                pages, cost, tail = best[end]
                candidates.append((pages+1, cost+spare**2, [(start,end), *tail]))
        if candidates:
            best[start] = min(candidates)
    return best[0][2]

class Exam(Layout):
    def paragraph(self, y, value, x=36, step=15, right=RIGHT):
        for line in wrap(value,right-x):
            self.text(x,y,line)
            y += step
        return y

    def numbered(self,n,y,value,step=15):
        self.text(33,y,f'{n}.')
        return self.paragraph(y,value,x=58,step=step)

    def options(self,y,values,checked=None,cols=2,left=58,step=17):
        labels = [f'{chr(65+i)}  {v}' for i,v in enumerate(values)]
        cols = self.option_columns(labels,checked,cols,left)
        cell = (RIGHT-left)/cols
        for i,label in enumerate(labels):
            x=left+(i%cols)*cell
            baseline=y+(i//cols)*step
            assert width(label)+(18 if i==checked else 0)+OPTION_GAP<=cell,(label,cell)
            self.text(x,baseline,label)
            if i==checked:
                self.mark(x+width(label)+8,baseline-3)
        return y+((len(labels)+cols-1)//cols)*step

    def option_columns(self,labels,checked,cols,left):
        fits = all(width(label)+(18 if i==checked else 0)+OPTION_GAP <= (RIGHT-left)/cols
                   for i,label in enumerate(labels))
        return cols if fits else 1

    def option_height(self,values,cols=2,left=58,step=17):
        labels = [f'{chr(65+i)}  {v}' for i,v in enumerate(values)]
        cols = self.option_columns(labels,None,cols,left)
        return ((len(labels)+cols-1)//cols)*step

    def divider(self,section):
        self.begin()
        self.line(47,208,335,208)
        self.text(191,249,f'下面是{section}部分',23,center=True)
        self.text(191,282,f'请在{section}考试开始后作答',19,center=True)
        self.line(47,310,335,310)
        self.end()

    def example_listening(self,y,sample,show_options,step=15):
        for i,line in enumerate(sample['lines']):
            if i==0:
                self.text(33,y,'例：')
            y=self.paragraph(y,line,x=58,step=step)
        if show_options:
            y=self.options(y+2,sample['options'],sample['key'])
        if 'second' in sample:
            y=self.paragraph(y+3,sample['second'],x=58,step=step)
            if show_options:
                y=self.options(y,sample['secondOptions'],sample['secondKey'])
        return y+12

def photos(doc,page):
    return sorted((fitz.Rect(info['bbox']) for info in doc[page].get_image_info()
                   if info['width']>900),key=lambda r:(round(r.y0/10),r.x0))

def ribbon(l,x,y):
    img=Image.new('RGB',(380,175),'#eaf2f4')
    d=ImageDraw.Draw(img)
    d.rounded_rectangle((29,105,352,141),radius=7,fill='#eac86b',outline='#9e7535',width=3)
    for i in range(35,351,10):
        d.line((i,106,i,126 if (i-35)%50==0 else 116),fill='#544634',width=2)
    d.line(((45,82),(80,67),(136,75),(180,62),(286,69),(329,53)),fill='#a83f73',width=14)
    d.line(((45,82),(47,100)),fill='#a83f73',width=10)
    d.line(((329,53),(345,76)),fill='#a83f73',width=10)
    l.c.drawImage(ImageReader(img),x,540-y-47,102,47)

def cover_and_table(l):
    t=l.text
    l.begin(cover=True)
    purple='#653094'
    for y,value,size in [(87,f'HSK3.0  {l.level}급',30),(169,'모의고사',23),
                         (246,f'제{l.set}회 모의고사',16),(362,'필기 70문항  ·  말하기 5문항',10),
                         (384,'듣기 32  ·  독해 32  ·  쓰기 6  ·  말하기 5',9)]:
        t(191,y,value,size,'KR',True,purple)
    t(191,419,'QR을 스캔하면 이 회차의 듣기와 말하기 음원을 재생합니다.',7,'KR',True)
    url=f'https://yanchunnu.github.io/-/hsk-listening.html?level={l.level}&set={l.set}'
    d=Drawing(47,47)
    d.add(qr.QrCodeWidget(url,barWidth=47,barHeight=47))
    renderPDF.draw(d,l.c,167.5,64)
    t(191,485,'듣기 · 말하기',7,'KR',True)
    t(25,505,'이름',8,'KR')
    t(204,505,'날짜',8,'KR')
    l.line(50,509,171,509)
    l.line(230,509,355,509)
    l.end()
    l.begin('考试结构')
    columns=[32,95,169,222,276,351]
    rows=[('题型','部分','题量','合计','时长')]
    for title,counts,time in [('听力',(14,18),'约20分钟'),('阅读',(10,15,7),'30分钟'),
                              ('书写',(5,1),'25分钟'),('口语',(2,1,2),'约10分钟')]:
        rows.extend((title if i==0 else '',PARTS[i],str(n),
                     str(sum(counts)) if i==0 else '',time if i==0 else '')
                    for i,n in enumerate(counts))
    rows.append(('合计','','75','75',''))
    for i,row in enumerate(rows):
        y=112+i*23
        l.line(columns[0],y,columns[-1],y)
        for a,b,v in zip(columns,columns[1:],row):
            t((a+b)/2,y+15,v,9,center=True)
    bottom=112+23*len(rows)
    l.line(columns[0],bottom,columns[-1],bottom)
    for x in columns:
        l.line(x,112,x,bottom)
    t(32,423,'笔试约80分钟，含填写个人信息的时间。')
    t(32,448,'口语各题作答时间见口语考试说明。')
    l.end()

def question_booklet(level,number,data,path):
    doc,_,_,_,listen,words,fill,reading,sentences,hints,essay,_,oral,scopes=data
    l=Exam(number,level=level)
    t=l.text
    cover_and_table(l)
    for first,last,part,example in [(1,7,0,'l1'),(8,14,0,'l1b'),(15,20,1,'l2'),
                                     (21,24,1,'l2b'),(25,32,1,None)]:
        l.begin('一、听力' if first==1 else '',PARTS[part],(first,last) if part==0 else (15,32),
                continued=part==1 and first!=15)
        y=126 if first==1 else 114
        t(33,y,('听对话，选择正确答案。' if part==0 else '听短文，选择正确答案。')+'每题听一次。')
        y+=21
        if example:
            y=l.example_listening(y,EX[example],True)
        gap=min(19,(501-y-34*(last-first+1))/(last-first+1))
        spacing=max(5,gap-(7.5 if first>=21 else 0))
        option_step=17
        if number != 1 or first in (1, 8):
            options = sum(l.option_height(listen[n]) for n in range(first,last+1))
            group_titles = 15*sum(scopes.get(n,n)>n for n in range(first,last+1))
            if y+options+group_titles+4*(last-first+1)>507:
                option_step=15
                options = sum(l.option_height(listen[n],step=option_step) for n in range(first,last+1))
            if first >= 21 and y+options+group_titles+4*(last-first+1)>507:
                option_step=14
                options = sum(l.option_height(listen[n],step=option_step) for n in range(first,last+1))
            spacing = max(4,min(spacing,(507-y-options-group_titles)/(last-first+1)))
        for n in range(first,last+1):
            if n in scopes:
                height = sum(l.option_height(listen[m],step=option_step)+spacing for m in range(n,scopes[n]+1))
                if scopes[n]>n:
                    height+=15
                if y+height>=509:
                    l.end()
                    l.begin('',PARTS[part],(n,last) if part==0 else (15,32),continued=part==1)
                    t(33,114,('听对话，选择正确答案。' if part==0 else '听短文，选择正确答案。')+'每题听一次。')
                    y=135
            if scopes.get(n,n)>n:
                t(33,y,f'第{n}-{scopes[n]}题')
                y+=15
            t(33,y,f'{n}.')
            y=l.options(y,listen[n],step=option_step)+spacing
        assert y<515,(first,y)
        l.end()
    l.divider('阅读')
    for j,bank in enumerate(words):
        l.begin('二、阅读' if j==0 else '',PARTS[0],(33,42),continued=bool(j))
        y=126 if j==0 else 112
        t(33,y,'请选择合适的词语填空。每个选项只能用一次。')
        y+=25
        key,*lines=EX['r1b' if j else 'r1']
        for i,line in enumerate(lines):
            line=line.replace(key,'（　C　）')
            if i==0:
                t(33,y,'例：')
            t(58,y,line)
            y+=18
        y=l.options(y+1,('果然','互相',key),2,cols=3,left=58)+9
        y=l.options(y,bank,cols=6,left=38)+22
        for n in range(33+5*j,38+5*j):
            for i,line in enumerate(fill[n]):
                y=l.numbered(n,y,line) if i==0 else l.paragraph(y,line,x=58)
            y+=27 if j==0 else 16
        l.end()
    reading_step = 13 if number >= 5 else 14
    reading_option_step = 13 if number >= 5 else 15

    def reading_height(block):
        _,passage,rows = block
        return (17 if len(rows)>1 else 0)+reading_step*sum(1 for _ in wrap(passage,RIGHT-36))+6+sum(
            15*sum(1 for _ in wrap('★ '+question,RIGHT-58))+l.option_height(values,step=reading_option_step)+4
            for _,question,values in rows)

    def reading_example(y):
        ex=EX['r2']
        y=l.paragraph(y,'例：'+ex['passage'])
        y=l.paragraph(y,'★ '+ex['question'],x=58)
        return l.options(y,ex['options'],ex['key'],step=15)+11

    ranges = [(0,3),(3,7),(7,9),(9,11)]
    if number != 1:
        heights = [reading_height(block) for block in reading]
        ex = EX['r2']
        example_height = (15*sum(1 for _ in wrap('例：'+ex['passage'],RIGHT-36))+
                          15*sum(1 for _ in wrap('★ '+ex['question'],RIGHT-58))+
                          l.option_height(ex['options'],step=15)+11)
        ranges = page_ranges(heights,509-126,example_height)
    for start,end in ranges:
        l.begin('',PARTS[1],(43,57),continued=bool(start))
        t(33,111,'阅读短文，选出正确答案。')
        y=126
        if start==0:
            y=reading_example(y)
        for scope,passage,rows in reading[start:end]:
            if len(rows)>1:
                t(33,y,'第'+scope.replace('–','-')+'题')
                y+=17
            y=l.paragraph(y,passage,step=reading_step)
            for n,question,values in rows:
                y=l.numbered(n,y,'★ '+question)
                y=l.options(y,values,step=reading_option_step)+4
            y+=6
        assert y<=516,(start,y)
        l.end()
    l.begin('',PARTS[2],(58,64))
    t(33,110,'请选择合适的句子填空。每个选项只能用一次。')
    ex=EX['r3']
    y=l.paragraph(131,'例：'+ex['passage'])
    y=l.options(y,ex['options'],ex['key'],cols=2,left=38)+4
    for j,(passage,values) in enumerate(sentences):
        t(33,y,'第58-60题' if j==0 else '第61-64题')
        y+=16
        y=l.paragraph(y,re.sub(r'_+','____',passage))
        for value in values:
            y=l.paragraph(y,value,x=58)
        y+=5
    assert y<=515,y
    l.end()
    l.divider('写作')
    l.begin('三、书写',PARTS[0],(65,69))
    t(33,124,'看图，用词造句。')
    t(33,158,'例：')
    ribbon(l,58,135)
    t(178,151,EX['w1'][0])
    t(178,173,EX['w1'][1])
    pics=photos(doc,8)
    assert len(pics)==5
    for i,(n,clip) in enumerate(zip(range(65,70),pics)):
        x=34+i%2*161
        y=200+i//2*98
        t(x,y+16,f'{n}.')
        l.image(doc,8,clip,x+24,y,119,63)
        t(x+24,y+77,hints[n])
        l.line(x+24,y+86,x+149,y+86)
    l.end()
    l.begin('',PARTS[1],(70,70))
    y=l.paragraph(112,'例：'+EX['w2'][0])
    y=l.paragraph(y+3,EX['w2'][1])+18
    y=l.numbered(70,y,essay)+8
    for row in range(11):
        for col in range(17):
            l.box(39+CELL_WIDTH*col,y+CELL_WIDTH*row,CELL_WIDTH,CELL_WIDTH)
    l.end()
    l.begin('口语','考试说明')
    t(33,128,'口语考试分三部分，共五题。')
    t(33,158,'第一部分　听后复述（第71-72题），每题40秒。')
    t(33,183,'第二部分　看图说话（第73题），作答时间为2分钟。')
    t(33,208,'第三部分　回答问题（第74-75题），每题2分钟。')
    t(191,266,'第一部分　听后复述',13,center=True)
    t(33,301,'请听一段话，然后用自己的话复述。')
    t(56,350,'71. （40秒）')
    t(211,350,'72. （40秒）')
    l.end()
    l.begin('口语','第二部分　看图说话',(73,73))
    t(33,124,'请按顺序看三张图，并连起来讲一个故事。时间为2分钟。')
    t(33,149,'73.')
    pic,=photos(doc,9)
    l.image(doc,9,pic,33,166,317,143)
    for i in range(3):
        t(86+105*i,328,'图'+str(i+1),center=True)
    t(33,364,'准备笔记')
    for i in range(4):
        l.line(33,389+24*i,350,389+24*i)
    l.end()
    l.begin('口语','第三部分　回答问题',(74,75))
    t(33,124,'请用汉语回答。每题2分钟。')
    for i,n in enumerate((74,75)):
        y=l.numbered(n,159+165*i,oral[n][0])
        t(58,y+12,'准备笔记')
        for k in range(4):
            l.line(58,y+31+21*k,350,y+31+21*k)
    l.end()
    l.save(path)

def answer_booklet(level,number,data,path):
    _,keys,transcripts,questions,*_,writing,oral,scopes=data
    l=Exam(number,level=level,page_offset=0)
    t=l.text
    def heading(value,part=''):
        l.begin(value,part)
    heading('答案表')
    for start,y,title in [(1,106,'听力'),(33,320,'阅读')]:
        t(33,y,title,13)
        for i in range(32):
            x=44+(i%4)*80
            yy=y+26+i//4*22
            t(x,yy,f'{start+i}.')
            t(x+24,yy,keys[start+i])
    l.end()
    heading('答案表','书写')
    t(33,119,'第一部分　看图，用词造句',13)
    y=144
    for n in range(65,70):
        y=l.numbered(n,y,writing[n][0])
        for alternative in writing[n][1:]:
            y=l.paragraph(y,alternative,x=58)
        y+=4
    t(33,y+13,'第二部分　写短文',13)
    y=l.numbered(70,y+39,writing[70][0])
    l.end()
    heading('口语','第一部分　听后复述')
    y=119
    for n in (71,72):
        y=l.numbered(n,y,oral[n][0])+18
    t(191,y+4,'第二部分　看图说话',13,center=True)
    y=l.numbered(73,y+31,oral[73][0])
    assert y<508,y
    l.end()
    heading('口语','第三部分　回答问题')
    y=119
    for n in (74,75):
        y=l.numbered(n,y,oral[n][0])+8
        y=l.paragraph(y,oral[n][1],x=58,step=13)+13
    assert y<516,y
    l.end()
    transcript_step = 13 if number >= 5 else 15

    def line_height(value):
        return transcript_step*sum(1 for _ in wrap(value,RIGHT-58))

    examples = {1:'l1',8:'l1b',15:'l2',21:'l2b'}
    pages = []
    for part, low, high in [(0,1,14),(1,15,32)]:
        starts = [n for n in sorted(scopes) if low<=n<=high]
        heights = []
        for n in starts:
            end = scopes[n]
            height = sum(line_height(line) for line in transcripts[n])
            height += sum(line_height(questions[m])+11 for m in range(n,end+1))
            if end>n:
                height += 21
            if n in examples:
                sample = EX[examples[n]]
                height += 12+sum(line_height(line) for line in sample['lines'])
                if 'second' in sample:
                    height += 3+line_height(sample['second'])
            heights.append(height)
        pages.extend((starts[a],scopes[starts[b-1]],part)
                     for a,b in page_ranges(heights,509-117))
    for first,last,part in pages:
        heading('听力原文',PARTS[part]+('（续）' if first not in (1,15) else ''))
        y=117
        for n in range(first,last+1):
            if n in examples:
                y=l.example_listening(y,EX[examples[n]],False,step=transcript_step)
            if n in transcripts:
                lines=transcripts[n]
                if scopes[n]>n:
                    t(33,y,f'第{n}-{scopes[n]}题')
                    y+=17
                    for line in lines:
                        y=l.paragraph(y,line,x=58,step=transcript_step)
                    y+=4
                else:
                    for i,line in enumerate(lines):
                        y=l.numbered(n,y,line,step=transcript_step) if i==0 else l.paragraph(y,line,x=58,step=transcript_step)
            y=l.numbered(n,y,questions[n],step=transcript_step) if scopes.get(n)!=n else l.paragraph(y,questions[n],x=58,step=transcript_step)
            y+=11
        assert y<516,(first,y)
        l.end()
    l.save(path)

def build(level,number):
    data=load(number)
    out=Path('output')
    preview=out/'preview'
    preview.mkdir(parents=True,exist_ok=True)
    for label,generate in [('문제지',question_booklet),('정답및해설',answer_booklet)]:
        path=out/f'HSK3.0_{level}급_제{number:02}회_{label}.pdf'
        generate(level,number,data,path)
        assert path.stat().st_size<5_000_000
        with fitz.open(path) as pdf:
            preview_label = '해설' if label=='정답및해설' else label
            for image in set(preview.glob(f'제{number:02}회_{preview_label}-*.png')) | set(preview.glob(f'제{number:02}회_{label}-*.png')):
                if image.stem.rsplit('-',1)[-1].isdecimal():
                    image.unlink()
            for i,page in enumerate(pdf,1):
                page.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(preview/f'제{number:02}회_{preview_label}-{i:02}.png')
            print(label,len(pdf),path.stat().st_size)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--level',type=int,choices=[4],required=True)
    ap.add_argument('--set',type=int,choices=range(1,11),required=True)
    args=ap.parse_args()
    build(args.level,args.set)

if __name__=='__main__':
    main()







