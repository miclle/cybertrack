"""Build the current six-part print review supplement from verified CAD renders."""
import hashlib
import json
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'hardware/model'
OUT=MODEL/'print-parts'
audit=json.loads((MODEL/'print-consolidation-audit.json').read_text())
assert audit['passed'] and audit['source_sha256']==hashlib.sha256((MODEL/audit.get('source_document','CyberTrack.FCStd')).read_bytes()).hexdigest()
report=json.loads((MODEL/'readback.json').read_text())
assert report['design_revision']=='0.51'
for r in audit['parts']:
    for filename,digest in r['files'].items():
        assert hashlib.sha256((OUT/filename).read_bytes()).hexdigest()==digest
for r in audit['parts']:
    p=OUT/(r['id']+'.png')
    assert hashlib.sha256(p.read_bytes()).hexdigest()==report['files_sha256']['print-parts/'+p.name]
pdfmetrics.registerFont(TTFont('ZH','/System/Library/Fonts/STHeiti Light.ttc',subfontIndex=0))
U=72/25.4
W,H=297*U,210*U
c=canvas.Canvas(str(OUT/'print-parts.pdf'),pagesize=(W,H))
c.setTitle('CyberTrack 0.51 合并打印图册')
c.setAuthor('CyberTrack')
INK='#173643';MUTED='#52666F';ACCENT='#D66C30';PALE='#EEF3F5'
style=ParagraphStyle('body',fontName='ZH',fontSize=9,leading=13,textColor=INK,wordWrap='CJK')

def text(x,y,s,size=10,color=INK):
    c.setFillColor(color);c.setFont('ZH',size);c.drawString(x*U,y*U,s)

def para(x,y,s,width=120):
    p=Paragraph(s,style);_,h=p.wrap(width*U,100*U);p.drawOn(c,x*U,y*U-h)

def pic(path,x,y,width,height):
    with Image.open(path) as im:
        ratio=min(width*U/im.width,height*U/im.height)
        w,h=im.width*ratio,im.height*ratio
    c.drawImage(ImageReader(str(path)),x*U+(width*U-w)/2,y*U+(height*U-h)/2,w,h,mask='auto')

def frame(title,page):
    c.setFillColor(PALE);c.rect(0,182*U,W,28*U,fill=1,stroke=0)
    text(14,193,title,19)
    text(14,184,'CYBERTRACK  /  0.51  /  2026-10-26',9,MUTED)
    c.setStrokeColorRGB(.8,.85,.87);c.line(14*U,15*U,283*U,15*U)
    text(14,9,'CAD连通性与装配评审；材料、层向、支撑、公差与实物验收未完成。',8,MUTED)
    text(266,9,f'{page} / 4',8,MUTED)

frame('六组合并打印 · 保留原有机甲层次',1)
pic(MODEL/'assembly.png',6,32,151,144)
text(162,164,'58个源特征 → 6个单实体候选',16,ACCENT)
text(162,153,'本轮六件，不是全机打印BOM。',10)
for i,row in enumerate(audit['parts']):
    text(162,139-i*11,row['label'],11)
para(162,65,'双枪与背包保持原材料外形；冠盖增加背侧连接筋，颈架填平横梁间隙并补孔顶薄桥，底盘补湿舱内侧接缝。装甲台阶、凹槽、脊翼、主要外轮廓和检修分界保留。',119)
para(162,38,'原0.50装配图册用于识别源特征；本图册与0.51分件清单决定本轮打印范围。',119)
c.showPage()
notes=[
 '底托、两处托管槽合为一件。枪体、胶垫及肩梁独立，保留两颗基座螺钉。',
 '底座、前圆环、六段槽壁合为一件。保留穿环入槽与底座可拆路径，软垫独立。',
 '背包壳、下后护甲和脊条融合；桶座原已一体。瓶底托、绑带、软垫和设备不并入。',
 '底盘与湿舱隔板融合并补内侧接缝；保留两处原有封闭内腔。底盖、电源内托架、顶盖和电子托框独立。',
 '四条宽6、高2 mm的背侧连接筋连接前后护甲。四颗冠盖螺钉保持，整体上取。',
 '横梁半径7.5改8 mm；外层板孔顶各补0.4 mm薄桥。外轮廓和中央走线保持，无活动关节。',
]
for page in range(3):
    frame('合并打印件 · 几何与装配边界',page+2)
    for column in range(2):
        i=page*2+column;r=audit['parts'][i];x=14+column*140
        text(x,169,r['label'],15)
        pic(OUT/(r['id']+'.png'),x,68,128,96)
        text(x,64,'外包络：'+' × '.join(f'{v:.2f}' for v in r['size_xyz_mm'])+' mm',10)
        text(x,55,f"{r['feature_count']}个源特征 → 1个有效实体；STL闭合边界与CAD一致。",10,ACCENT)
        para(x,48,notes[i],128)
        text(x,23,'STL仅居中落地，图示轴向不是已确定的打印朝向。',8,MUTED)
    c.showPage()
c.save()
print(OUT/'print-parts.pdf')
