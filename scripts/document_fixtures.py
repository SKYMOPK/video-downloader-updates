"""Generate realistic synthetic acceptance fixtures using the bundled authoring runtime."""
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches
from docx.oxml.ns import qn
from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Inches as SlideInches, Pt as SlidePt
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas

ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'evidence/document-fixtures'
folder.mkdir(exist_ok=True)
image=Image.new('RGBA',(800,400),(0,0,0,0))
draw=ImageDraw.Draw(image)
draw.rectangle((40,30,350,370),fill='#2563a8')
draw.ellipse((430,60,740,370),fill='#d39339')
draw.text((70,65),'TOP LEFT',fill='white',font_size=36)
image.save(folder/'透明圖片.png')
image.convert('RGB').save(folder/'兩頁.tiff',save_all=True,append_images=[Image.new('RGB',(400,800),'#60987c')])
image.convert('RGB').save(folder/'照片.jpg',quality=95)
image.save(folder/'動畫.gif',save_all=True,append_images=[Image.new('RGBA',(800,400),'blue')],duration=200,loop=0)
document=Document()
style=document.styles['Normal']; style.font.name='Microsoft JhengHei'; style.font.size=Pt(11)
style.element.rPr.rFonts.set(qn('w:eastAsia'),'Microsoft JhengHei')
document.add_heading('中文文件轉換驗收',0)
document.add_paragraph('這份文件包含繁體中文、表格、圖片與分頁。來源檔案應完整保留，輸出的 PDF 應可閱讀與選取文字。')
table=document.add_table(rows=1,cols=3); table.style='Light Shading Accent 1'
for cell,text in zip(table.rows[0].cells,['項目','內容','結果']): cell.text=text
for values in [('排版','中文與英文 Windows App','正常'),('檔案','Word → PDF','待確認')]:
    for cell,text in zip(table.add_row().cells,values): cell.text=text
document.add_picture(str(folder/'透明圖片.png'),width=Inches(5))
document.add_page_break(); document.add_heading('第二頁：確認沒有遺漏',1)
document.add_paragraph('最後一行：測試完成。')
document.save(folder/'中文報告.docx')
workbook=Workbook(); sheet=workbook.active; sheet.title='轉換測試'
for row in [('項目','數量','金額'),('文件',3,120),('圖片',2,80),('合計',5,'=SUM(C2:C3)')]: sheet.append(row)
for key in ('A','B','C'): sheet.column_dimensions[key].width=22
sheet.print_options.horizontalCentered=True; sheet.print_area='A1:C4'; sheet.page_setup.orientation='landscape'
workbook.save(folder/'試算表.xlsx')
slides=Presentation()
for title,body in [('中文簡報驗收','第一張投影片：保留標題與內文'),('第二頁','動畫不會保留，靜態內容應完整')]:
    slide=slides.slides.add_slide(slides.slide_layouts[1]); slide.shapes.title.text=title; slide.placeholders[1].text=body
    for shape in slide.shapes:
        if shape.has_text_frame:
            for paragraph in shape.text_frame.paragraphs:
                for run in paragraph.runs: run.font.name='Microsoft JhengHei'
slides.save(folder/'簡報.pptx')
(folder/'中文文字.txt').write_text('純文字轉換\n繁體中文測試與 English 123\n保留分行。',encoding='utf-8')
(folder/'Big5文字.txt').write_text('繁體中文 Big5 文字測試',encoding='big5')
pdf=canvas.Canvas(str(folder/'可選取文字.pdf')); pdf.drawString(72,760,'Page one - text extraction'); pdf.showPage(); pdf.drawString(72,760,'Page two - final line'); pdf.save()
pdf=canvas.Canvas(str(folder/'掃描文件.pdf')); pdf.drawImage(str(folder/'照片.jpg'),50,300,width=480,height=240); pdf.save()
print('Document acceptance fixtures generated.')
