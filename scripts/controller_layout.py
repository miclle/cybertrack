"""Measured controller envelope and explicitly provisional mechanical interfaces.

The board has no verified screw holes. Pin-row spacing comes from the supplier
 drawing; height datums, socket slots, USB bodies and antenna extent are design
 allocations, not reconstructed measurements from the photos.
"""
import hashlib
import json
from pathlib import Path
import FreeCAD as App
import Part
V=App.Vector
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'hardware/components/ESP32-S3-N16R8/board-data.json'
RF_SOURCE='https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html#general-principles-of-pcb-layout-for-modules-positioning-a-module-on-a-base-board'


def box(x0,y0,z0,x1,y1,z1):
    return Part.makeBox(x1-x0,y1-y0,z1-z0,V(x0,y0,z0))


def build_controller(doc,add,cut,fuse,fastener,insert):
    # Shift the local carrier rearward so the antenna review area clears audio.
    raw_add,raw_cut,raw_fuse,raw_fastener,raw_insert=add,cut,fuse,fastener,insert
    def shifted(shape):
        shape=shape.copy();shape.translate(V(0,7,0));return shape
    def add(name,label,shape,*args):return raw_add(name,label,shifted(shape),*args)
    def cut(name,shape):return raw_cut(name,shifted(shape))
    def fuse(name,shape):return raw_fuse(name,shifted(shape))
    def fastener(name,x,y,*args):return raw_fastener(name,x,y+7,*args)
    def insert(name,x,y,*args):return raw_insert(name,x,y+7,*args)
    fuse('ElectronicsTray',box(-44,3,144.5,17.4,10,145.5))
    data=json.loads(SOURCE.read_text());m=data['measured_dimensions_mm'];d=data['dimensions_mm']
    length,width,height=(m[k] for k in ('length_including_antenna','width','height_with_soldered_pins'))
    assert (length,width,height)==(63.6,28.2,13.2), 'Review interfaces if measurements change'
    x0,x1=-39.6,24.0;y0,y1=-16-width/2,-16+width/2;z0=163.6
    pcb_z=169.2;pcb_top=170.8;antenna_start=17.6
    board=box(x0,y0,pcb_z,x1,y1,pcb_top).fuse(box(x0,y0,pcb_top,antenna_start,y1,z0+height))
    rows=[-16-d['header_row_spacing']/2,-16+d['header_row_spacing']/2]
    pin_start=x0+d['end_pin_to_pcb_edge_rounded'];pin_end=pin_start+d['first_last_pin_spacing']
    for y in rows:
        # Continuous strips are occupied pin-row corridors, not individual contacts.
        board=board.fuse(box(pin_start,y-.32,z0,pin_end,y+.32,pcb_z))
    add('ESP32Board','实测 ESP32-S3 整板包络／内部层高为假设',board.removeSplitter(),'envelope','electronics',
        '用户实测总外包络 63.6×28.2×13.2；PCB 厚1.6、针排条带宽0.64及层高均为设计假设；不是逐元件模型')
    # The previous broad allocation is replaced rather than overlapping the board.
    residual=doc.getObject('Electronics');residual.Shape=box(-35,-72,168,35,-47,181)
    residual.Label='前上方剩余电子分配区 70×25×13／非实物器件'
    residual.EvidenceBasis='主控独立布局后的暂定余量；未证明驱动、升压或开关板全部可装入'
    carrier=box(-44,-38,154,17.4,9,156)
    add('ControllerCarrier','非金属候选主控小托架／天线端悬出',carrier,'structure','body',
        '候选61.4×47×2；不使用开发板排针孔作螺钉孔；材料、刚度及制造公差未定')
    for i,x in enumerate((-41,0)):
        for j,y in enumerate((-35,6)):
            tag=str(i)+str(j)
            fuse('ElectronicsTray',Part.makeCylinder(3,8.5,V(x,y,145.5)))
            cut('ElectronicsTray',Part.makeCylinder(2.1,5,V(x,y,149.1)))
            insert('ControllerMountInsert'+tag,x,y,149.2,153.9)
            cut('ControllerCarrier',Part.makeCylinder(1.5,3,V(x,y,153.5)))
            fastener('ControllerMountScrew'+tag,x,y,150,156,157)
    for name,y in zip(('Front','Rear'),rows):
        socket=box(pin_start-1.3,y-1.4,156,pin_end+1.3,y+1.4,pcb_z)
        socket=socket.cut(box(pin_start-.3,y-.5,z0-.2,pin_end+.3,y+.5,pcb_z+.1))
        add('ControllerSocket'+name,'22 位排母承接区域 '+name,socket.removeSplitter(),'structure','dark',
            '图纸针排中心距25.4／首末针53.34；连续槽为简化接口，非选定排母。插入深度、触点与固定工艺待实测')
    # A removable nonmetal anti-lift bridge clears the full component envelope.
    retainer=box(-32,-34,177.3,-29,2,178.8)
    for y0,y1 in ((-34,-31),(-1,2)):
        retainer=retainer.fuse(box(-32,y0,158,-29,y1,177.3))
    for name,y,lo,hi in [('Front',-34,-37,-31),('Rear',2,-1,5)]:
        retainer=retainer.fuse(box(-37,lo,156,-27,hi,158))
        retainer=retainer.cut(Part.makeCylinder(1.5,3,V(-35,y,155.5)))
        fuse('ControllerCarrier',Part.makeCylinder(3,4,V(-35,y,150)))
        cut('ControllerCarrier',Part.makeCylinder(2.1,4.1,V(-35,y,150)))
        cut('ControllerCarrier',Part.makeCylinder(1.5,3,V(-35,y,153.5)))
        insert('ControllerRetainerInsert'+name,-35,y,150.1,153.9)
        fastener('ControllerRetainerScrew'+name,-35,y,151,158,159)
    add('ControllerRetainer','可拆防脱压架／组件包络上方0.5间隙',retainer.removeSplitter(),'structure','accent',
        '非金属候选；不预压元件。0.5为设计间隙，冲击承载、触碰位置和母座拔出力未验证')
    # Harness corridor to the socket tail area; no GPIO or electrical connection defined.
    from refine_assembly import route
    points=[(0,-5,146),(0,-5,150),(-17,-5,150),(-17,-34,150),(-17,-34,161),(-17,-31.7,161)]
    wire=route(points,1.5)
    cut('ControllerCarrier',Part.makeCylinder(2.3,4,V(-17,-34,153)))
    guide=Part.makeCylinder(3.2,2.5,V(-17,-34,156)).cut(Part.makeCylinder(2.2,3,V(-17,-34,155.8)))
    add('ControllerWireGuide','主控尾线导向环／孔Ø4.4候选',guide,'structure','dark','线束Ø3候选；最小弯曲半径、压紧和实际端子未核实')
    add('ControllerWireRoute','主控尾线独立走线Ø3／不定义针序',wire,'envelope','power',
        '头舱入口至排母尾线区的路径分配；与既有线束端部留连接余量，不代表电气接通；拆卸前断开')
    for tag,y in [('COM',-9.5),('USB',-22.5)]:
        add('ControllerUSB'+tag,tag+'直头插头候选18×10×8／开盖检修',box(-57.6,y-5,169.8,-39.6,y+5,177.8),
            'clearance','power','用户确认直头；插头18×10×8、双口中心Y=-15.5/-2.5及Z173.8均为设计假设，需实测')
        lead=box(-65.6,y-5,169.8,-57.6,y+5,201)
        add('ControllerUSBLead'+tag,tag+'线尾转向并向上出线空间',lead,'clearance','power',
            '冠盖拆下时的线尾空间；不是实际线缆或厂家弯曲半径，不支持据此合盖夹线')
    rf=box(17.6,-45.1,154.2,39,13.1,185.8)
    add('ControllerAntennaSpace','天线端审查区／禁止布线与金属件',rf,'clearance','signal',
        '天线区X17.6…24为假设；向外15、横向两侧15、上下15的设计审查区；馈电侧保留原板，非RF验收')
    return {'board_source':'hardware/components/ESP32-S3-N16R8/board-data.json',
        'board_source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'measured_size_lwh_mm':[length,width,height],'board_bbox_mm':[x0,y0+7,z0,x1,y1+7,z0+height],
        'orientation':'component side +Z; length +X toward antenna, USB -X; width Y; J1 toward +Y, J2 toward -Y',
        'header_row_spacing_mm':d['header_row_spacing'],'header_span_mm':d['first_last_pin_spacing'],
        'header_evidence':'supplier drawing, not measured; continuous pin/socket slots are schematic',
        'assumed_pcb_z_mm':[pcb_z,pcb_top],'assumed_usb_plug_mm':[18,10,8],
        'usb_type':'straight; user confirmed','assumed_usb_centers_yz_mm':{'COM':[-2.5,173.8],'USB':[-15.5,173.8]},'usb_requires_crown_removal':True,
        'carrier_outer_plan_mm':[61.4,47],'additional_fasteners':6,
        'remaining_electronics_allocation_mm':[70,25,13],
        'rf_guideline':RF_SOURCE,'antenna_extent_assumed':True,'rf_performance_verified':False,
        'socket_fit_retention_and_cable_bend_verified':False,'physical_fit_verified':False}


def controller_members(doc):
    return [o.Name for o in doc.Objects if hasattr(o,'Category') and
            (o.Name=='ESP32Board' or o.Name.startswith('Controller')) and
            o.Category!='clearance' and o.Name!='ControllerWireRoute' and
            not o.Name.startswith(('ControllerMountScrew','ControllerMountInsert'))]


def check_controller_spaces(doc,crown):
    """Keep access/RF review volumes separate from occupied material collision checks."""
    physical=[o for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance']
    results=[]
    for name in ('ControllerUSBCOM','ControllerUSBUSB','ControllerUSBLeadCOM','ControllerUSBLeadUSB','ControllerAntennaSpace'):
        region=doc.getObject(name).Shape;hits=[]
        excluded=set(crown) | {o.Name for o in physical if o.Name.startswith('CrownScrew')} if 'USB' in name else {'ESP32Board'}
        for obj in physical:
            if obj.Name in excluded:continue
            if not region.optimalBoundingBox(False).intersect(obj.Shape.optimalBoundingBox(False)):continue
            vol=region.common(obj.Shape).Volume
            if vol>.01:hits.append({'object':obj.Name,'overlap_mm3':vol})
        results.append({'name':name,'excluded':sorted(excluded),'overlaps':hits,'passed':not hits})
    return {'checks':results,'passed':all(r['passed'] for r in results),
            'scope':'USB with crown removed; antenna assumed external review region excludes host board',
            'actual_plug_access_or_rf_verified':False}
