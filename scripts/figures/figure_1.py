# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Recreate the supplied scientific flowchart, correcting only two split counts.

Source diagram: submission folder / original submission / Figure 1.tif.
Verified split counts: supplied Additional_file_1, first table.
No patient data are loaded and no analysis is performed.
"""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
import pypdfium2 as pdfium
from PIL import Image
import math

OUT = _sad_private_path("publication_figures")
OUT.mkdir(parents=True, exist_ok=True)
W, H = 7.2 * 72, 10.3 * 72
pdf_path = OUT / 'Figure_1_vector.pdf'
c = canvas.Canvas(str(pdf_path), pagesize=(W, H))
c.setFillColor(HexColor('#FFFFFF'))
c.rect(0, 0, W, H, fill=1, stroke=0)

def text_at(x, y, text, fontsize=11, weight='normal', background=False, anchor='center'):
    lines = text.split('\n')
    font = 'Times-Bold' if weight == 'bold' else 'Times-Roman'
    line_height = fontsize * 1.23
    total_height = len(lines) * line_height
    base = y * H + total_height/2 - fontsize
    if background:
        width = max(c.stringWidth(t, font, fontsize) for t in lines) + 4
        c.setFillColor(HexColor('#FFFFFF'))
        c.rect(x*W - width/2, base-(len(lines)-1)*line_height-3, width, total_height+3, fill=1, stroke=0)
    c.setFillColor(HexColor('#111111'))
    c.setFont(font, fontsize)
    for i, t in enumerate(lines):
        c.drawCentredString(x*W, base - i*line_height, t)

def box(x, y, w, h, text, fill='#FBE8CD', edge='#D69721', fontsize=11, weight='normal'):
    c.setStrokeColor(HexColor(edge))
    c.setFillColor(HexColor(fill))
    c.setLineWidth(1)
    c.roundRect(x*W,y*H,w*W,h*H,8,stroke=1,fill=1)
    text_at(x+w/2,y+h/2,text,fontsize,weight)

def arrow(x1,y1,x2,y2):
    a,b,d,e=x1*W,y1*H,x2*W,y2*H
    c.setStrokeColor(HexColor('#222222'))
    c.setFillColor(HexColor('#222222'))
    c.setLineWidth(1.1)
    c.line(a,b,d,e)
    angle=math.atan2(e-b,d-a)
    backx,backy=d-7*math.cos(angle),e-7*math.sin(angle)
    dx,dy=3*math.sin(angle),-3*math.cos(angle)
    path=c.beginPath();path.moveTo(d,e);path.lineTo(backx+dx,backy+dy);path.lineTo(backx-dx,backy-dy);path.close()
    c.drawPath(path,fill=1,stroke=0)

def line(xs,ys):
    c.setStrokeColor(HexColor('#222222'));c.setLineWidth(1.1)
    for i in range(len(xs)-1):c.line(xs[i]*W,ys[i]*H,xs[i+1]*W,ys[i+1]*H)

# Source database and eligibility.
box(.045, .885, .32, .087, 'MIMIC-IV dataset\n(Version 3.1)\n94,458 ICU stays', weight='bold')
box(.045, .775, .32, .067, '41,295 ICU stays met\nthe Sepsis-3 criteria')
arrow(.205, .877, .205, .850)

# Exclusion panel mirrors the source diagram and retains all supplied counts.
c.setFillColor(HexColor('#DFE9F7'));c.setStrokeColor(HexColor('#648ABF'));c.setDash(6,6)
c.rect(.54*W,.388*H,.42*W,.455*H,fill=1,stroke=1);c.setDash()
text_at(.75, .815, 'Exclusion criteria', 12)
box(.585, .691, .33, .072, 'Multiple ICU admissions\nor hospital admissions', '#FFFFFF', '#222222')
box(.585, .529, .33, .113, 'No valid CAM-ICU record\nwithin 7 days after sepsis;\nCAM-ICU positive within\n24 h before sepsis', '#FFFFFF', '#222222')
box(.585, .407, .33, .076, 'ICU length of stay <24 h;\npregnancy; age <18 years', '#FFFFFF', '#222222')
line([.205, .205], [.767, .352])
for y, label in [(.727, '13,414 ICU stays\nexcluded'),
                 (.5855, '8,610 patients\nexcluded'),
                 (.445, '1,420 patients\nexcluded')]:
    arrow(.205, y, .577, y)
    text_at(.36, y+.024, label, 10, background=True)
box(.045, .300, .32, .074, '17,851 patients met\nthe inclusion criteria')

# Counts agree with the supplied cohort partition table and later test-set figures.
line([.205, .205], [.292, .257])
line([.16, .82], [.257, .257])
for center in [.16, .49, .82]:
    arrow(center, .257, center, .220)
box(.035, .145, .25, .067, 'Training set\n11,424 patients', weight='bold')
box(.365, .145, .25, .067, 'Validation set\n2,856 patients', weight='bold')
box(.695, .145, .25, .067, 'Test set\n3,571 patients', weight='bold')
for center in [.16, .49, .82]:
    line([center, center], [.137, .116])
line([.16, .82], [.116, .116])
arrow(.49, .116, .49, .094)
box(.315, .035, .35, .051, 'Model development\nand validation', '#FFFFFF', '#222222')
text_at(.5, .013, 'Flowchart of patient selection and dataset allocation', 10, 'bold')
c.showPage();c.save()
pdf=pdfium.PdfDocument(str(pdf_path));page=pdf[0]
image=page.render(scale=600/72).to_pil().convert('RGB')
image.save(OUT/'Figure_1.tiff', compression='tiff_lzw', dpi=(600,600))
image.thumbnail((1080,1545));image.save(OUT/'Figure_1_preview.png')
page.close();pdf.close()
print(OUT/'Figure_1.tiff')

