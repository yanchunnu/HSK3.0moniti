"""Build one HSK 2 sample booklet and answer booklet from the numbered source."""
import argparse
import json
from pathlib import Path
import re
from io import BytesIO

from PIL import Image
import pymupdf as fitz
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas



import zxingcpp

PARTS = ('第一部分','第二部分','第三部分','第四部分')
NAMES = '一二三四五六七八九十'
EXAMPLE3 = ['甲：你今天怎么来学校？','乙：我坐公共汽车来的。','问：他怎么来学校？']
SAMPLE_EXAMPLES = {
    'listening2': ['甲：你在这儿等什么？','乙：我在等公共汽车。'],
    'reading1': '花园里的花开了。',
    'reading2': ['我想喝一杯（D）。','Wǒ xiǎng hē yì bēi (D).'],
    'reading3': ['你最喜欢什么颜色？','Nǐ zuì xǐhuan shénme yánsè?'],
}
SECTIONS = [('听力', [5,10,10], '约17分钟'), ('阅读',[5,5,10,5],'25分钟'),
            ('书写',[5,5],'10分钟')]
HAN = r'[\u3400-\u9fff]'
PAGE_RANGES = [(1,5),(6,10),(11,15),(16,20),(21,25),(26,30),(31,35),
               (36,40),(41,45),(46,48),(49,50),(51,55),(56,60)]

def answers(source):
    page = source[15].get_text()
    keys = {int(n):a for n,a in re.findall(r'(?<!\d)(\d{2})\s+([A-F])\b', page)}
    writing = page[page.index('56'):page.index('51-55')]
    for n,b in re.findall(r'(5[6-9]|60)(.*?)(?=5[6-9]|60|\Z)',writing,re.S):
        keys[int(n)] = ''.join(re.findall(HAN,b))
    finished = page.split('51-55번 완성 한자:')[1].split('한자 위에는')[0]
    for n,b in re.findall(r'(5[1-5])(.*?)(?=5[1-5]|\Z)',finished,re.S):
        keys[int(n)] += ' / '+''.join(re.findall(HAN,b))
    assert sorted(keys) == list(range(1,61)) and all(keys.values())
    scripts = {}
    for page in source[16:23]:
        content = page.get_text()
        for n,a,b in re.findall(r'(?ms)^(\d+)\.\s*정답\s+([A-F])[^\n]*\n(.*?)(?=^\d+\.\s*정답|\Z)',content):
            n = int(n)
            assert a == keys[n], (n,a,keys[n])
            # Translation follows the transcript. Stop before Korean text or explanatory options.
            b = re.split(r'[가-힣]',b,maxsplit=1)[0]
            clean = ''.join(re.findall(r'[\u3400-\u9fff：，、。？！；]',b))
            if n >= 16:
                clean = clean[re.search(r'[甲乙男女]：',clean).start():]
            scripts[n] = re.findall(r'(?:[甲乙男女问]：)?[^：]+?(?=(?:[甲乙男女问]：)|$)',clean)
            assert scripts[n] and all(line[-1] in '。？！' for line in scripts[n]), (n,clean)
    assert list(scripts) == list(range(1,26)), scripts
    return keys,scripts

def photos(raw,page):
    ops = raw.pages[page].get_contents().operations
    height = float(raw.pages[page].mediabox.height)
    for i in range(len(ops)-5):
        if [op for _,op in ops[i:i+6]] == [b're',b'W*',b'n',b'q',b'cm',b'Do']:
            x,y,w,h = map(float,ops[i][0])
            yield fitz.Rect(x,height-y-h,x+w,height-y)

class Layout:
    def __init__(self,set_number):
        self.set = set_number
        self.buf = BytesIO()
        self.c = canvas.Canvas(self.buf,pagesize=(595.276,841.89))
        self.pages = 0
        self.clips = []
        for name,file in [('CN','simhei.ttf'),('Latin','arial.ttf'),('KR','malgun.ttf')]:
            pdfmetrics.registerFont(TTFont(name,str(Path('C:/Windows/Fonts')/file)))

    def text(self,x,y,value,size=10,font='CN',center=False,color='#17212c'):
        self.c.setFillColor(color)
        self.c.setFont(font,size)
        draw = self.c.drawCentredString if center else self.c.drawString
        draw(x,540-y,value)

    def line(self,x1,y1,x2,y2):
        self.c.setStrokeColor('#a1abb5')
        self.c.setLineWidth(.55)
        self.c.line(x1,540-y1,x2,540-y2)

    def box(self,x,y,w=15,h=15):
        self.c.setStrokeColor('#536173')
        self.c.setLineWidth(.65)
        self.c.rect(x,540-y-h,w,h,stroke=1,fill=0)

    def mark(self,x,y):
        self.c.setStrokeColor('#17513c')
        self.c.setLineWidth(1.2)
        self.c.line(x,540-y,x+3,540-y-3)
        self.c.line(x+3,540-y-3,x+9,540-y+4)

    def begin(self,title='',part='',question_range=None,subheader=None,cover=False):
        self.pages += 1
        self.c.saveState()
        self.c.scale(595.276/382,841.89/540)
        if cover:
            return
        if subheader:
            self.text(35,31,subheader,8)
        else:
            self.text(27,24,f'HSK 3.0  •  2급 제{self.set}회 모의고사',8,'KR')
        self.line(27,37 if subheader else 31,355,37 if subheader else 31)
        if title:
            self.text(191,67,title,20,center=True)
        if part:
            self.text(191,89 if title else 65,part,13,center=True)
        if question_range:
            first,last = question_range
            self.text(32,106 if title else 91,f'第{first}–{last}题',10)
        self.line(27,509,355,509)
        self.text(191,525,str(self.pages if subheader else self.pages-1),8,'Latin',True)

    def end(self):
        self.c.restoreState()
        self.c.showPage()

    def pair(self,x,y,han,py):
        self.text(x,y-11,py,7,'Latin',color='#4e5e70')
        self.text(x,y,han,10)

    def image(self,source,page,clip,x,y,w,h):
        scale = min(w/clip.width,h/clip.height)
        pix = source[page].get_pixmap(matrix=fitz.Matrix(2,2),clip=clip,alpha=False)
        im = Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        im.thumbnail((1200,1200))
        encoded = BytesIO()
        im.save(encoded,'JPEG',quality=85,optimize=True)
        encoded.seek(0)
        self.c.drawImage(ImageReader(encoded),x+(w-clip.width*scale)/2,
                         540-y-(h+clip.height*scale)/2,clip.width*scale,clip.height*scale)

    def crop(self,page,clip,x,y,width,max_height=400):
        scale = min(width*595.276/382/clip.width,max_height*841.89/540/clip.height)
        self.clips.append((self.pages-1,page,clip,fitz.Rect(
            x*595.276/382,y*841.89/540,
            x*595.276/382+clip.width*scale,y*841.89/540+clip.height*scale)))

    def save(self,path,source=None):
        self.c.save()
        with fitz.open(stream=self.buf.getvalue(),filetype='pdf') as pdf:
            for target,page,clip,rect in self.clips:
                pdf[target].show_pdf_page(rect,source,page,clip=clip)
            pdf.save(path,garbage=4,deflate=True)

def body_clip(source,page,top=149,bottom=788):
    return fitz.Rect(37,top,558,bottom)

def booklet(source,raw,keys,set_number,output,examples):
    layout = Layout(set_number)
    t,ln = layout.text,layout.line
    url = f'https://yanchunnu.github.io/-/hsk-listening.html?level=2&set={set_number}'
    layout.begin(cover=True)
    # The supplied cover shares the Level 1 design.
    cover = source[0]
    text_hit = cover.search_for('문제 · 정답 · 듣기 대본 · 한국어 해설')
    assert len(text_hit) == 1
    # Cover uses the same trimmed source as the approved Level 1 production.
    layout.clips.append((0,0,cover.rect,cover.rect))
    layout.end()

    layout.begin('考试结构')
    t(191,91,'HSK 3.0（二级）',13,center=True)
    cols = [35,96,167,219,267,347]
    row = 0
    for y in range(117,382,24):
        ln(cols[0],y,cols[-1],y)
    for x in cols:
        ln(x,117,x,381)
    def table_line(y,labels):
        for left,right,label in zip(cols,cols[1:],labels):
            t((left+right)/2,y,str(label),9,center=True)
    table_line(133,['题型','部分','题量','合计','时长'])
    for title,counts,time in SECTIONS:
        for part,count in enumerate(counts):
            table_line(157+24*row,[title,PARTS[part],count,sum(counts) if not part else '',time if not part else ''])
            row += 1
    table_line(373,['总计','九个部分',60,60,'约60分钟'])
    t(35,421,'听力结束后有3分钟填写答题卡。')
    t(35,445,'全部考试约60分钟（含填写个人信息时间5分钟）。')
    layout.end()

    for page,(first,last) in enumerate(PAGE_RANGES,1):
        if page == 6:
            layout.begin()
            ln(47,205,335,205)
            t(191,246,'下面是阅读部分',23,center=True)
            t(191,281,'请在阅读考试开始后作答',19,center=True)
            ln(47,310,335,310)
            layout.end()
        group = 0 if page<=5 else 1 if page<=11 else 2
        part = [0,1,1,2,2,0,1,2,2,3,3,0,1][page-1]
        initial = page in (1,6,12)
        layout.begin(('一、听力','二、阅读','三、书写')[group] if initial else '',
                     PARTS[part],(first,last))
        if page == 1:
            t(32,119,'听一句话，选择正确图片。',9)
            t(32,131,'例句：这是一把伞。',9)
            xs = [30,67,162,257,352]
            for x in xs:
                ln(x,137,x,497)
            for y in range(137,498,60):
                ln(xs[0],y,xs[-1],y)
            t(39,168,'例',9)
            for col,word in enumerate(['书','杯子','伞']):
                x=114+95*col
                c=layout.c
                c.setStrokeColor('#38506b')
                c.setLineWidth(1.3)
                if word=='书':
                    c.roundRect(x-14,540-181,28,27,2,stroke=1,fill=0)
                    ln(x-7,154,x-7,181)
                    ln(x-3,162,x+8,162)
                elif word=='杯子':
                    c.roundRect(x-12,540-181,23,25,3,stroke=1,fill=0)
                    c.arc(x+7,540-177,x+23,540-159,-90,180)
                else:
                    c.arc(x-18,540-174,x+18,540-151,0,180)
                    ln(x-18,162,x+18,162)
                    ln(x,151,x,179)
                    c.arc(x-7,540-183,x,540-175,180,180)
                    layout.mark(x+16,188)
                t(x,192,'ABC'[col],8,'Latin',True)
            boxes = list(photos(raw,page))
            assert len(boxes)==15
            for i,clip in enumerate(boxes):
                row,col = divmod(i,3)
                y = 197+row*60
                if col == 0:
                    t(43,y+29,f'{row+1}.',9,'Latin')
                layout.image(source,page,clip,74+95*col,y+2,80,45)
                t(114+95*col,y+56,'ABC'[col],8,'Latin',True)
        elif page in (2,3,6):
            t(32,118 if initial else 107,'选择与句子相符的图片。' if page==6 else '听对话，选择最匹配的图片。',9)
            boxes=list(photos(raw,page))
            assert len(boxes)==6
            for i,clip in enumerate(boxes):
                row,col=divmod(i,2)
                x,y=52+151*col,128+72*row
                layout.image(source,page,clip,x,y,125,57)
                t(x+62,y+65,'ABCDEF'[i],8,'Latin',True)
            unused = (set('ABCDEF')-{keys[i] for i in range(first,last+1)})
            assert len(unused)==1
            if page in (2,6):
                t(32,356,'例',9)
                if page==2:
                    t(62,356,examples['listening2'][0],10)
                    t(62,374,examples['listening2'][1],10)
                else:
                    t(62,356,examples['reading1'],10)
                layout.box(329,343)
                t(336.5,354,unused.pop(),9,'Latin',True)
            if page==6:
                layout.crop(page,body_clip(source,page,442,676),31,373,320,124)
            else:
                for i,n in enumerate(range(first,last+1)):
                    y=395+i*23
                    t(35,y+11,f'{n}.',9,'Latin')
                    layout.box(329,y)
        else:
            instruction = {4:'听对话和问题，选择正确答案。',5:'听对话和问题，选择正确答案。',
                7:'选择合适的词语填空。',8:'选择与句子相应的回答。',9:'选择与句子相应的回答。',
                10:'阅读短文，选择正确答案。',11:'阅读短文，选择正确答案。',
                12:'选择合适的汉字部件，写出完整的汉字。',13:'根据拼音写出正确的词语。'}
            t(32,120 if initial else 107,instruction[page],9)
            top=121
            if page==4:
                t(32,130,'例',9)
                for i,line in enumerate(EXAMPLE3):
                    t(62,130+i*17,line)
                for x,s in zip((62,160,250),('A 公共汽车','B 自行车','C 地铁')):
                    t(x,183,s)
                layout.mark(120,180)
                top=205
            elif page==7:
                layout.crop(page,body_clip(source,page,150,232),31,122,320)
                t(32,190,'例',9)
                choice = next(iter(set('ABCDEF')-{keys[i] for i in range(31,36)}))
                assert f'（{choice}）' in examples['reading2'][0]
                layout.pair(62,190,*examples['reading2'])
                layout.crop(page,body_clip(source,page,235),31,208,320,290)
            elif page==8:
                unused = set('ABCDEF')-{keys[i] for i in range(36,41)}
                assert len(unused)==1
                layout.crop(page,body_clip(source,page,150,377),31,120,320,145)
                t(32,284,'例',9)
                layout.pair(62,284,*examples['reading3'])
                layout.box(329,272)
                t(336.5,283,unused.pop(),9,'Latin',True)
                layout.crop(page,body_clip(source,page,377),31,299,320,200)
            elif page==10:
                t(32,130,'例',9)
                layout.pair(62,130,'小李明天坐火车去北京。','Xiǎo Lǐ míngtiān zuò huǒchē qù Běijīng.')
                layout.pair(62,158,'★ 小李什么时候去北京？','Xiǎo Lǐ shénme shíhou qù Běijīng?')
                for x,s in zip((62,160,250),('A 今天','B 明天','C 后天')):
                    t(x,180,s)
                layout.mark(205,177)
                top=196
            elif page==12:
                t(32,147,'例',9)
                layout.pair(62,147,'日 ＋（月）→ 明','míng')
                layout.box(329,132,15,17)
                t(336.5,145,'明',10,center=True)
                top=166
            elif page==13:
                t(32,146,'例',9)
                layout.pair(62,146,'（      ）离我家很近。','xuéxiào')
                for index,char in enumerate('学校'):
                    layout.box(65+16*index,150,16,14)
                    t(73+16*index,161,char,10,center=True)
                top=177
            if page not in (7,8):
                layout.crop(page,body_clip(source,page),31,top,320,500-top)
        layout.end()

    intermediate = output.with_suffix('.tmp.pdf')
    layout.save(intermediate,source)
    with fitz.open(intermediate) as doc:
        # Redact the obsolete subtitle from the source itself before importing the cover.
        target = doc[0]
        hits=target.search_for('문제 · 정답 · 듣기 대본 · 한국어 해설')
        assert len(hits)==1
        target.add_redact_annot(hits[0],fill=(1,1,1))
        target.apply_redactions(images=0,graphics=0)
        codes = zxingcpp.read_barcodes(Image.frombytes('RGB',
            ((pix:=target.get_pixmap()).width,pix.height),pix.samples))
        if [code.text for code in codes] != [url]:
            raise ValueError([code.text for code in codes])
        found = codes[0].position
        target.insert_link({'kind':fitz.LINK_URI,'uri':url,'from':fitz.Rect(
            found.top_left.x,found.top_left.y,found.bottom_right.x,found.bottom_right.y)})
        doc.save(output,garbage=4,deflate=True)
    intermediate.unlink()
    assert output.stat().st_size <= 5_000_000

def answer_booklet(keys,scripts,set_number,path,examples):
    layout=Layout(set_number)
    t=layout.text
    head=f'HSK 3.0  /  二级  /  第{NAMES[set_number-1]}套'
    layout.begin('答案表',subheader=head)
    n=1
    y=96
    for title,counts,_ in SECTIONS:
        t(35,y,title,13)
        y+=20
        for i,count in enumerate(counts):
            remaining=count
            while remaining:
                t(37,y,PARTS[i] if remaining==count else '',8)
                for x in range(min(remaining,5)):
                    t(99+x*51,y,f'{n:02}  {keys[n]}',8 if 51<=n<=55 else 9)
                    n+=1
                layout.line(35,y+5,347,y+5)
                y+=21
                remaining-=min(remaining,5)
        y+=8
    layout.end()
    chunks = [[0,*range(1,6),-1,*range(6,11)],list(range(11,16)),
              [-1,*range(16,21)],list(range(21,26))]
    for part,numbers in zip([0,1,2,2],chunks):
        layout.begin('听力原文',PARTS[part],subheader=head)
        y=116
        for n in numbers:
            if n==0:
                lines=['这是一把伞。']
            elif n==-1:
                lines=examples['listening2'] if part==0 else EXAMPLE3
                if part==0:
                    t(35,y,PARTS[1],13)
                    y+=23
            else:
                lines=scripts[n]
            t(36,y,f'{n}.' if n>0 else '例',9)
            for line in lines:
                for start in range(0,len(line),32):
                    t(62,y,line[start:start+32])
                    y+=15
            y+=8
        assert y<510
        layout.end()
    layout.save(path)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('set_number',type=int,choices=range(1,11))
    parser.add_argument('--examples',type=Path,help='JSON with set-specific examples for the unused options')
    args=parser.parse_args()
    if args.set_number != 1 and args.examples is None:
        parser.error('supply --examples for the selected source photos and options')
    examples=json.loads(args.examples.read_text(encoding='utf8')) if args.examples else SAMPLE_EXAMPLES
    n=args.set_number
    stem=f'HSK3.0_2급_제{n:02}회_'
    source_path=Path('input/sets')/(stem+'표지통일_전체듣기QR.pdf')
    out=Path('output')
    preview=out/'preview'
    preview.mkdir(parents=True,exist_ok=True)
    problem=out/(stem+'문제지.pdf')
    answer=out/(stem+'정답및해설.pdf')
    with fitz.open(source_path) as source:
        keys,scripts=answers(source)
        booklet(source,PdfReader(source_path),keys,n,problem,examples)
        answer_booklet(keys,scripts,n,answer,examples)
    for path in (problem,answer):
        with fitz.open(path) as pdf:
            print(path,len(pdf),path.stat().st_size)
            for i,page in enumerate(pdf,1):
                pixels=page.get_pixmap(matrix=fitz.Matrix(1.65,1.65))
                if path==problem:
                    pixels.save(preview/f'제{n:02}회_문제지-{i:02}.png')
                    image=Image.frombytes('RGB',(pixels.width,pixels.height),pixels.samples)
                    assert len(zxingcpp.read_barcodes(image))==(1 if i==1 else 0)

if __name__=='__main__':
    main()
