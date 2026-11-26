"""Parse the numbered Level 3 source and lay out the exam and answer booklets."""
from pathlib import Path
import json
import re
from io import BytesIO

import pymupdf as fitz
from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.graphics.barcode import qr
from reportlab.graphics import renderPDF

from booklet import Layout, PARTS, writing_syllables

EX = json.loads(Path(__file__).with_name('例01.json').read_text(encoding='utf8'))
BLANK = '（　　）'
# A4 scaling turns 14 layout units into approximately 21.8 pt.
OPTION_GAP = 14
OPTION_STACK_STEP = 17


def parse(number):
    path, = Path('input/sets').glob(f'*제{number:02}회*.pdf')
    doc = fitz.open(path)
    pages = [p.get_text(sort=True) for p in doc]
    explanations = '\n'.join(pages[7:])
    keys = {int(n): v for n, v in re.findall(r'\b(\d+)\.\s+([A-E]|[\u4e00-\u9fff]+)(?=\s|$)', pages[7].split('뒤쪽')[0])}
    assert len(keys) == 65, keys
    listening = {}
    pattern = r'(?ms)^\s*(\d+)\.\s+정답\s+([A-E])\s*\n(.*?)(?=^\s*\d+\.\s+정답|\Z)'
    for n, key, body in re.findall(pattern, explanations):
        n = int(n)
        if n > 30:
            break
        assert keys[n] == key
        initial = re.split(r'\n\s*[가-힣]', body, maxsplit=1)[0].strip()
        if n <= 20:
            lines = initial.splitlines()
        else:
            lines = [''.join(line.strip() for line in initial.splitlines())]
        if n >= 11:
            lines.append(re.search(r'(?m)^\s*(问：.+)$', body)[1])
        listening[n] = [line.strip() for line in lines]
    assert list(listening) == list(range(1, 31))
    for n, sentence in re.findall(r'(?m)^\s*(6[6-9]|70)\.\s+제시어[^\n]+\n\s*([^\n]+)', explanations):
        keys[int(n)] = sentence.strip()
    assert len(keys) == 70
    oral = {}
    tail = explanations.split('听后重复', 1)[1]
    for n, sentence in re.findall(r'(?m)^\s*([1-8])\.\s+([^\n]+)', tail):
        oral[int(n)] = [sentence]
    for n, sentence in re.findall(r'(?m)^\s*(9|1[0-3])\.\s+모범 답안\s*\n\s*([^\n]+)', tail):
        oral[int(n)] = [sentence]
    for n, question, answer in re.findall(r'(?m)^\s*(1[45])\.\s+([^\n]+)\n\s*[가-힣][^\n]+\n\s*([\u4e00-\u9fff][\u4e00-\u9fff，。？！、；：\s]+)', tail):
        oral[int(n)] = [question, re.sub(r'\s+', '', answer)]
    assert list(oral) == list(range(1, 16)), oral
    return doc, pages, keys, listening, oral


class Exam(Layout):
    def __init__(self, number):
        super().__init__(number, level=3)

    def numbered_text(self, number, y, value, x=36):
        self.text(x, y, f'{number}.')
        return self.text_lines(x+24, y, value, width=355-x-24)

    def text_lines(self, x, y, value, width=309, step=15):
        while value:
            stop = len(value)
            while pdfmetrics.stringWidth(value[:stop], 'CN', 10) > width:
                stop -= 1
            if 0 < len(value) - stop <= 3:
                stop -= 5
            while stop < len(value) and value[stop] in '，。？！；、）':
                stop -= 1
            self.text(x, y, value[:stop])
            value = value[stop:]
            y += step
        return y

    def option_labels(self, values, first_letter='A'):
        labels = [f'{chr(ord(first_letter)+i)}  {value}' for i, value in enumerate(values)]
        widths = [pdfmetrics.stringWidth(label, 'CN', 10) for label in labels]
        return labels, widths

    def option_slots(self, widths, checked):
        return tuple(width + (18 if checked == i else 0)
                     + (OPTION_GAP if i < len(widths)-1 else 0)
                     for i, width in enumerate(widths))

    def option_columns(self, rows, left):
        available = 355-left
        default = available/3
        slots = [self.option_slots(self.option_labels(values)[1], checked)
                 for values, checked in rows]
        # Keep the most rows horizontal on one shared grid, preferring the equal grid on ties.
        candidates = ((a, b, available-a-b)
                      for a in {default, *(row[0] for row in slots)}
                      for b in {default, *(row[1] for row in slots)}
                      if a+b < available)

        def score(columns):
            fits = sum(all(need <= have for need, have in zip(row, columns)) for row in slots)
            a, b, _ = columns
            return (-fits, abs(a-default) + abs(a+b-2*default), a, b)

        columns = min(candidates, key=score)
        return columns, len(rows) + score(columns)[0]

    def options(self, y, values, checked=None, left=39, first_letter='A', row_step=16, columns=None):
        labels, widths = self.option_labels(values, first_letter)
        columns = columns or ((355-left)/3,) * 3
        inline = all(need <= have for need, have in zip(self.option_slots(widths, checked), columns))
        for i, (label, width) in enumerate(zip(labels, widths)):
            x = left + sum(columns[:i]) if inline else left
            baseline = y if inline else y + i*OPTION_STACK_STEP
            self.text(x, baseline, label)
            if checked == i:
                self.mark(x + width + 8, baseline-3)
        return y + row_step + (0 if inline else (len(labels)-1)*OPTION_STACK_STEP)


def pictures(doc, page):
    return [fitz.Rect(item['bbox']) for item in doc[page].get_image_info() if item['width'] >= 900]


def art(layout, kind, x, y, w=84, h=58):
    img = Image.new('RGB', (336, 232), '#eaf2f4')
    d = ImageDraw.Draw(img)
    if kind in ('snow', 'sun', 'rain'):
        d.rectangle((0, 163, 336, 232), fill='#f9fbff' if kind == 'snow' else '#92b891')
        d.rectangle((113, 117, 225, 189), fill='#bd896c')
        d.polygon([(94, 124), (171, 57), (244, 124)], fill='white' if kind == 'snow' else '#775a50')
        d.rectangle((155, 144, 182, 189), fill='#725750')
        if kind == 'sun':
            d.ellipse((244, 13, 303, 72), fill='#f4bf3d')
        else:
            for cx, cy in ((40,49),(65,91),(25,120),(271,53),(289,102),(306,151),(76,157),(221,45),(139,29)):
                if kind == 'snow':
                    d.ellipse((cx,cy,cx+9,cy+9), fill='white')
                else:
                    d.line((cx,cy,cx-9,cy+24), fill='#447e9a', width=4)
    else:
        d.rectangle((30,115,309,208), fill='#6b8f9e')
        d.ellipse((109,129,241,199), fill='#c7e3ee')
        d.arc((147,38,213,123), 180, 330, fill='#4f6169', width=10)
        d.line((205,78,205,113), fill='#4f6169', width=10)
        d.line((204,115,195,153), fill='#57a9d3', width=6)
        d.ellipse((149,147,211,180), fill='#fdf8df', outline='#658699', width=5)
        d.line((149,158,154,183,202,183,210,158), fill='#fdf8df', width=8)
        d.ellipse((92,126,139,151), fill='#e9b17e')
        d.line((62,95,105,134,158,154), fill='#e9b17e', width=18)
    layout.c.drawImage(ImageReader(img), x, 540-y-h, w, h)


def writing_line(layout, n, y, sentence, ruby, answer, show=False):
    left, right = sentence.split(BLANK)
    layout.text(32, y, n)
    x = 58
    layout.text(x, y, left)
    x += pdfmetrics.stringWidth(left, 'CN', 10) + 3
    for syllable, char in zip(writing_syllables(answer, ruby.replace(' ', '')), answer):
        layout.syllable(x+8.5, y-17, syllable)
        layout.box(x, y-12, 17, 17)
        if show:
            layout.text(x+8.5, y, char, center=True)
        x += 18
    layout.text(x+3, y, right)
    

def booklet(number, data, path):
    doc, pages, keys, _, oral = data
    l = Exam(number)
    t = l.text
    l.begin(cover=True)
    purple = '#653094'
    t(191, 87, 'HSK3.0  3급', 30, 'KR', True, purple)
    t(191, 169, '모의고사', 23, 'KR', True, purple)
    t(191, 246, f'제{number}회 모의고사', 16, 'KR', True, purple)
    t(191, 362, '필기 70문항  ·  말하기 15문항', 10, 'KR', True, purple)
    t(191, 384, '듣기 30  ·  독해 30  ·  쓰기 10  ·  말하기 15', 9, 'KR', True, purple)
    t(191, 419, 'QR을 스캔하면 이 회차의 듣기와 말하기 음원을 재생합니다.', 7, 'KR', True)
    url = f'https://yanchunnu.github.io/-/hsk-listening.html?level=3&set={number}'
    widget = qr.QrCodeWidget(url, barWidth=47, barHeight=47)
    from reportlab.graphics.shapes import Drawing
    d = Drawing(47, 47)
    d.add(widget)
    renderPDF.draw(d, l.c, 167.5, 64)
    t(191, 485, '듣기 · 말하기', 7, 'KR', True)
    t(25, 505, '이름', 8, 'KR')
    t(204, 505, '날짜', 8, 'KR')
    l.line(50,509,171,509)
    l.line(230,509,355,509)
    l.end()

    l.begin('考试结构')
    cols = [32,95,169,222,276,351]
    rows = [('题型','部分','题量','合计','时长')]
    for title, counts, timing in [('听力',(10,10,10),'约23分钟'),('阅读',(10,10,10),'30分钟'),('书写',(5,5),'20分钟'),('口语',(8,5,2),'约15分钟')]:
        for i,count in enumerate(counts):
            rows.append((title if i==0 else '', PARTS[i],str(count),str(sum(counts)) if i==0 else '',timing if i==0 else ''))
    for i,row in enumerate(rows):
        y=112+i*22
        l.line(cols[0],y,cols[-1],y)
        for a,b,value in zip(cols,cols[1:],row):
            t((a+b)/2,y+15,value,9,center=True)
    bottom=112+22*len(rows)
    l.line(cols[0],bottom,cols[-1],bottom)
    for x in cols:
        l.line(x,112,x,bottom)
    t(32,402,'笔试约83分钟，含填写个人信息及答题卡时间。')
    t(32,424,'口语考试含6分钟准备时间。')
    l.end()

    photos = pictures(doc,1)
    assert len(photos)==10
    for part in range(2):
        l.begin('一、听力' if not part else '',PARTS[0],(1,10),continued=bool(part))
        y=124 if not part else 110
        t(32,y,'听对话，选择最匹配的图片。')
        if not part:
            for i, sentence in enumerate(EX['listening1']):
                t(32,y+17+15*i,('例：' if not i else '　　')+sentence)
            for i, kind in enumerate(('sun','snow','rain')):
                x=39+106*i
                art(l,kind,x,y+39,83,53)
                t(x+41,y+105,chr(65+i),center=True)
            l.mark(193,y+103)
            y+=117
        else:
            y+=20
        for i, image in enumerate(photos[part*5:part*5+5]):
            x=39+(i%3)*106
            top=y+(i//3)*84
            l.image(doc,1,image,x,top,86,66)
            t(x+43,top+79,chr(65+i),center=True)
        for i in range(5):
            t(37+i*64,y+201,f'{part*5+i+1}.')
            l.box(56+i*64,y+190,15,15)
        l.end()

    listening_pages = [
        (11, 16, 'listening2', ['九点','十点','十一点'], 1, 10),
        (16, 21, 'listening2b', ['书包里','门口的桌子上','窗户旁边'], 1, 14),
        (21, 31, 'listening3', ['看报纸','吃晚饭','搬桌子'], 0, 10),
    ]
    for first, end, example, example_choices, checked, example_gap in listening_pages:
        dialogue = first < 21
        part = 1 if dialogue else 2
        start = 11 if dialogue else 21
        l.begin('',PARTS[part],(start,start+9),continued=first==16)
        t(32,110,'听对话和问题，选择正确答案。' if dialogue else '听短文和问题，选择正确答案。')
        y=132
        for i,line in enumerate(EX[example]):
            y=l.text_lines(36,y,('例：' if i==0 else '　　')+line)
        questions = []
        for n in range(first,end):
            row=re.search(rf'(?m)^\s*{n}\.\s+A\s+(.+?)\s+B\s+(.+?)\s+C\s+(.+)$',pages[2])
            questions.append((n, row.groups()))
        rows = [(example_choices, checked), *((values, None) for _, values in questions)]
        columns, stacked = l.option_columns(rows, left=58)
        example_baseline = y + 3
        example_end = l.options(example_baseline,example_choices,checked,left=58,columns=columns)
        stack_height = 2*OPTION_STACK_STEP*stacked - (example_end-example_baseline-16)
        y = example_end + example_gap
        # Reclaim only inter-question whitespace if the stacked rows need extra height.
        row_step = min(21, (508-y-stack_height)/len(questions))
        assert row_step >= 17, (number, first, row_step)
        for n, values in questions:
            t(32,y,f'{n}.')
            y=l.options(y,values,left=58,row_step=row_step,columns=columns)
        assert y<509
        l.end()

    def divider(section):
        l.begin()
        l.line(47,208,335,208)
        t(191,249,f'下面是{section}部分',23,center=True)
        t(191,282,f'请在{section}考试开始后作答',19,center=True)
        l.line(47,310,335,310)
        l.end()

    divider('阅读')
    # Source reading columns have independent text boxes.
    columns=[]
    for a,b in [(0,290),(290,596)]:
        columns.append(doc[3].get_text(clip=fitz.Rect(a,40,b,780),sort=True))
    for j in (0,1):
        l.begin('二、阅读' if j==0 else '',PARTS[0],(31,40),continued=bool(j))
        t(32,120,'请选择与题目相对应的句子。每个选项只能用一次。')
        col=columns[j]
        options=re.findall(r'(?m)^\s*([A-E])\.\s*([^\n]+)',col)
        options = [(a, v) for a, v in options if " B." not in v]
        assert len(options)==5,options
        if j==0:
            options.append(('F',EX['reading1'][1]))
        y=147
        for label,value in options:
            t(38,y,f'{label}.  {value}')
            y+=21
        if j==0:
            t(38,y+5,'例：'+EX['reading1'][0]+'（F）')
            l.mark(38+pdfmetrics.stringWidth('例：'+EX['reading1'][0]+'（F）','CN',10)+9,y+2)
            y+=33
        for n in range(31+j*5,36+j*5):
            value=re.search(rf'(?m)^\s*{n}\.\s*(.+)$',col)[1]
            t(38,y,f'{n}.  '+re.sub(r'\(_+\)',BLANK,value))
            y+=27
        l.end()

    for j,col in enumerate(columns):
        l.begin('',PARTS[1],(41,50),continued=bool(j))
        t(32,111,'请选择合适的词语填空。每个选项只能用一次。')
        line=re.search(r'(?m)^\s*A\.\s*.+B\..+E\..+$',col)[0]
        choices=re.findall(r'[A-E]\.\s*([^\s]+)',line)
        if j==0:
            choices.append(EX['reading2'][0])
        y=142
        for i in range(0,len(choices),3):
            y=l.options(y,choices[i:i+3],first_letter=chr(65+i),row_step=21)
        if j==0:
            t(39,y+10,'例：'+EX['reading2'][1].replace(BLANK,'（F）'))
            l.mark(39+pdfmetrics.stringWidth('例：'+EX['reading2'][1].replace(BLANK,'（F）'),'CN',10)+9,y+7)
            y+=37
        for n in range(41+j*5,46+j*5):
            row=re.search(rf'(?m)^\s*{n}\.\s*(.+)$',col)[1]
            t(39,y,f'{n}.  '+re.sub(r'（_+）',BLANK,row))
            y+=31
        l.end()

    reading=re.findall(r'(?ms)^\s*(5[1-9]|60)\.\s*(.*?)\s*★\s*(.*?)\s*A\s+(.+?)\s+B\s+(.+?)\s+C\s+([^\n]+)',pages[4])
    assert len(reading)==10
    for j,(start,end) in enumerate(((0,3),(3,7),(7,10))):
        l.begin('',PARTS[2],(51,60),continued=bool(j))
        t(32,111,'阅读短文，选出正确答案。')
        example_choices = ['下了雪','刮了大风','非常热']
        rows = [(row[3:], None) for row in reading[start:end]]
        if j == 0:
            rows.insert(0, (example_choices, 1))
        columns, _ = l.option_columns(rows, left=39)
        y=138
        if j==0:
            y=l.text_lines(36,y,'例：'+EX['reading3'][0])
            y=l.text_lines(43,y,'★ '+EX['reading3'][1])
            y=l.options(y,example_choices,1,columns=columns)+14
        for n,passage,question,*values in reading[start:end]:
            y=l.text_lines(36,y,f'{n}.  '+re.sub(r'\s+','',passage))
            y=l.text_lines(43,y,'★ '+question)
            y=l.options(y,values,columns=columns)+17
        assert y<509
        l.end()

    divider('书写')
    l.begin('三、书写',PARTS[0],(61,65))
    t(32,123,'根据拼音，在空格中写出正确的汉字。')
    writing_line(l,'例',164,*EX['writing1'],True)
    for i,n in enumerate(range(61,66)):
        ruby,sentence=re.search(rf'(?m)^\s*{n}\.\s*(\S+)\s+(.+)$',pages[5]).groups()
        writing_line(l,str(n)+'.',218+51*i,re.sub(r'（_+）',BLANK,sentence),ruby,keys[n])
    l.end()
    writing_photos = pictures(doc,5)
    assert len(writing_photos)==5
    l.begin('',PARTS[1],(66,70))
    t(32,110,'请用所给词语，根据图片写一个完整的句子。')
    art(l,'wash',59,125,76,52)
    t(32,145,'例')
    t(147,145,EX['writing2'][0])
    t(147,166,EX['writing2'][1])
    for n,clip in enumerate(writing_photos,66):
        y=187+(n-66)*62
        word=re.search(rf'{n}\.\s*提示词：(\S+)',pages[5])[1]
        t(32,y+19,f'{n}.')
        l.image(doc,5,clip,59,y,80,52)
        t(147,y+16,word)
        l.line(147,y+34,348,y+34)
        l.line(147,y+50,348,y+50)
    l.end()

    l.begin('口语','考试说明')
    t(32,120,'口语考试约15分钟，含准备时间6分钟。')
    t(32,144,'请提前阅读看图说话和回答问题。')
    t(191,191,'第一部分　听后重复',13,center=True)
    t(32,220,'第1-8题：请听句子并重复。每题10秒。')
    for n in range(1,9):
        t(42+80*((n-1)%4),260+38*((n-1)//4),f'{n}.（10秒）')
    l.end()

    l.begin('口语','第二部分　看图说话',(9,13))
    t(32,123,'请用汉语描述图片中的人物、地点和动作。每题15秒。')
    assert len(pictures(doc,6))==5
    for i,clip in enumerate(pictures(doc,6)):
        x=40+104*(i%3)
        y=155+121*(i//3)
        l.image(doc,6,clip,x,y,92,82)
        t(x+46,y+98,f'{i+9}.（15秒）',center=True)
    l.end()

    l.begin('口语','第三部分　回答问题',(14,15))
    t(32,123,'请阅读问题，用汉语回答。每题1分30秒。')
    for i,n in enumerate((14,15)):
        y=l.text_lines(37,160+157*i,f'{n}.  '+oral[n][0])
        t(37,y+14,'准备笔记')
        for k in range(3):
            l.line(37,y+35+k*23,347,y+35+k*23)
    l.end()
    l.save(path)


def answer_booklet(number, data, path):
    _, _, keys, listening, oral = data
    l=Exam(number)
    l.begin('答案表',subheader='HSK 3.0（三级）')
    for start,title,y in ((1,'听力',99),(31,'阅读',226)):
        l.text(32,y,title,13)
        for offset in range(30):
            n=start+offset
            x=37+64*(offset%5)
            baseline=y+20+16*(offset//5)
            l.text(x,baseline,f'{n}.')
            l.text(x+24,baseline,keys[n])
    l.text(32,353,'书写',13)
    l.text(37,375,'第一部分  61-65题（词语）')
    for n in range(61,66):
        x=37+64*(n-61)
        l.text(x,392,f'{n}.')
        l.text(x+24,392,keys[n])
    l.text(37,416,'第二部分  66-70题（句子）')
    for n in range(66,71):
        l.numbered_text(n,436+15*(n-66),keys[n],x=37)
    l.end()
    l.begin('口语','第一部分　听后重复',subheader='HSK 3.0（三级）')
    for i in range(1,9):
        l.numbered_text(i,115+23*(i-1),oral[i][0])
    l.text(191,323,'第二部分　看图说话',13,center=True)
    for i in range(9,14):
        l.numbered_text(i,353+23*(i-9),oral[i][0])
    l.end()
    l.begin('口语','第三部分　回答问题',subheader='HSK 3.0（三级）')
    y=119
    for i in (14,15):
        y=l.numbered_text(i,y,oral[i][0])+12
        y=l.text_lines(60,y,oral[i][1],width=295)+33
    l.end()
    for j,(start,end) in enumerate(((1,5),(6,10),(11,15),(16,20),(21,25),(26,30))):
        part=(0,0,1,1,2,2)[j]
        l.begin('听力原文',PARTS[part]+('（续）' if j in (1,3,5) else ''),subheader='HSK 3.0（三级）')
        y=111
        if j not in (1,5):
            for line in EX['listening2b' if j==3 else f'listening{part+1}']:
                y=l.text_lines(37,y,('例：' if y==111 else '　　')+line)
            y+=10
        # Longer dialogue pages need additional clearance above the footer.
        gap = 8 if number != 1 and part == 1 else 10
        for n in range(start,end+1):
            for i,line in enumerate(listening[n]):
                if i == 0:
                    y=l.numbered_text(n,y,line,x=37)
                else:
                    y=l.text_lines(61,y,line,width=294)
            y+=gap
        assert y-gap-15<503, (j,y)
        l.end()
    l.save(path)


def build(number, questions_only=False):
    data=parse(number)
    stem=f'HSK3.0_3급_제{number:02}회_'
    out=Path('output')
    out.mkdir(exist_ok=True)
    preview=out/'preview'
    preview.mkdir(exist_ok=True)
    booklets = [('문제지', booklet)]
    if not questions_only:
        booklets.append(('정답및해설', answer_booklet))
    for label,fn in booklets:
        path=out/(stem+label+'.pdf')
        fn(number,data,path)
        assert path.stat().st_size<5_000_000
        with fitz.open(path) as pdf:
            preview_label = '해설' if label == '정답및해설' and number != 1 else label
            for i,page in enumerate(pdf,1):
                page.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(preview/f'제{number:02}회_{preview_label}-{i:02}.png')
            prefix=f'제{number:02}회_{preview_label}-'
            for image in preview.glob(f'{prefix}*.png'):
                suffix=image.stem.removeprefix(prefix)
                if suffix.isdecimal() and int(suffix)>len(pdf):
                    image.unlink()
            if label == '문제지':
                assert len(pdf) == 21, (number, len(pdf))
            print(label,len(pdf),path.stat().st_size)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level',type=int,choices=[3],required=True)
    parser.add_argument('--set',type=int,choices=range(1,11),required=True)
    build(parser.parse_args().set)
