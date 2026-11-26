import argparse
from pathlib import Path
from io import BytesIO

from PIL import Image
import pymupdf as fitz
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas



PARTS = ('第一部分', '第二部分', '第三部分')
PINYIN_SIZE = 7
CELL_WIDTH = 28 / (595.276 / 382)
RUBY_SCALE = 0.73

def range_title(question_range,continued=False):
    first,last = question_range
    return (f'第{first}题' if first == last else f'第{first}-{last}题') + ('（续）' if continued else '')

class Layout:
    def __init__(self,set_number,*,level: int, page_offset=1):
        self.set = set_number
        self.level = level
        self.page_offset = page_offset
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

    def begin(self,title='',part='',question_range=None,subheader=None,cover=False,continued=False):
        self.pages += 1
        self.c.saveState()
        self.c.scale(595.276/382,841.89/540)
        if cover:
            return
        self.text(27,24,f'HSK 3.0 • {self.level}급 제{self.set}회 모의고사',8,'KR')
        self.line(27,37 if subheader else 31,355,37 if subheader else 31)
        if title:
            self.text(191,67,title,20,center=True)
        if part:
            self.text(191,89 if title else 65,part,13,center=True)
        if question_range:
            self.text(32,106 if title else 91,range_title(question_range,continued),10)
        self.line(27,509,355,509)
        self.text(191,525,str(self.pages-self.page_offset),8,'Latin',True)

    def end(self):
        self.c.restoreState()
        self.c.showPage()

    def syllable(self,x,y,value):
        width = pdfmetrics.stringWidth(value,'Latin',PINYIN_SIZE)*RUBY_SCALE
        assert width <= CELL_WIDTH-0.6, (value,width)
        self.c.saveState()
        text = self.c.beginText(x-width/2,540-y)
        text.setFont('Latin',PINYIN_SIZE)
        text.setHorizScale(RUBY_SCALE*100)
        text.setFillColor('#4e5e70')
        text.textOut(value)
        self.c.drawText(text)
        self.c.restoreState()

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

    def save(self,path,source=None):
        self.c.save()
        with fitz.open(stream=self.buf.getvalue(),filetype='pdf') as pdf:
            for target,page,clip,rect in self.clips:
                pdf[target].show_pdf_page(rect,source,page,clip=clip)
            pdf.save(path,garbage=4,deflate=True)

if __name__ == '__main__':
    from level4 import main
    main()
