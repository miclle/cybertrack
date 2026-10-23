"""Build CyberTrack's preliminary tracked robot concept from curated drive components.

Run with FreeCAD's Python runtime. --render uses the local Qt display.
Dimensions for unmeasured equipment are design allocations, not supplier facts.
"""
import argparse
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import FreeCAD as App
import Part
from refine_assembly import refine, service_groups, check_service_paths

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'hardware/model'
V = App.Vector
COLORS = {'body': (0.24, 0.36, 0.43), 'dark': (0.075, 0.10, 0.12),
          'metal': (0.40, 0.48, 0.51), 'light': (0.82, 0.84, 0.80), 'accent': (0.98, 0.31, 0.07),
          'visor': (0.025, 0.055, 0.065), 'signal': (0.20, 0.87, 0.94),
          'water': (0.18, 0.68, 0.81), 'bubble': (0.49, 0.46, 0.77),
          'power': (0.91, 0.68, 0.22), 'electronics': (0.22, 0.61, 0.42)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def box(x0, y0, z0, x1, y1, z1):
    return Part.makeBox(x1-x0, y1-y0, z1-z0, V(x0, y0, z0))


def yz_prism(points, xmin, xmax):
    """Extrude a side profile along X; explicit points are design dimensions."""
    vs = [V(xmin,y,z) for y,z in points]
    return Part.Face(Part.makePolygon(vs+[vs[0]])).extrude(V(xmax-xmin,0,0))


def xz_prism(points, ymin, ymax):
    vs = [V(x,ymin,z) for x,z in points]
    return Part.Face(Part.makePolygon(vs+[vs[0]])).extrude(V(0,ymax-ymin,0))


def footprint(halfwidth, front, rear, corner, z):
    points=[(-halfwidth+corner,front),(halfwidth-corner,front),
            (halfwidth,front+corner),(halfwidth,rear-corner),
            (halfwidth-corner,rear),(-halfwidth+corner,rear),
            (-halfwidth,rear-corner),(-halfwidth,front+corner)]
    vs=[V(x,y,z) for x,y in points]
    return Part.makePolygon(vs+[vs[0]])


def faceted_shell_volume(levels):
    return Part.makeLoft([footprint(*level) for level in levels],True,True)


def strut(radius, start, end):
    a,b=V(*start),V(*end)
    return Part.makeCylinder(radius,(b-a).Length,a,b-a)


def ring(radius, bore, height, origin, direction=V(0,0,1)):
    return Part.makeCylinder(radius,height,origin,direction).cut(
        Part.makeCylinder(bore,height,origin,direction))


def describe(obj):
    s = obj.Shape; b = s.optimalBoundingBox(False)
    return {'name': obj.Name, 'label': obj.Label, 'category': obj.Category,
            'valid': s.isValid(), 'solids': len(s.Solids), 'volume_mm3': s.Volume,
            'bbox_mm': [b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]}


def render_views(doc, output):
    """Use explicit orthographic cameras, avoiding animated view transitions."""
    import FreeCADGui as Gui
    from PySide import QtGui
    view = Gui.activeDocument().activeView()
    view.stopAnimating()
    view.setAnimationEnabled(False)
    view.setCameraType('Orthographic')
    orientations = {
        'front': App.Rotation(V(1,0,0),90),
        'rear': App.Rotation(V(0,0,1),180).multiply(App.Rotation(V(1,0,0),90)),
        'side': App.Rotation(V(0,1,0),V(0,0,1),V(1,0,0),'ZXY'),
        'right': App.Rotation(V(0,-1,0),V(0,0,1),V(-1,0,0),'ZXY'),
        'top': App.Rotation(),
        'iso': App.Rotation(V(1,1,0),V(-1,1,3),V(1,-1,0.75),'ZXY'),
        'rear_iso': App.Rotation(V(-1,1,0),V(-1,-1,3),V(1,1,0.75),'ZXY'),
    }
    def render(filename, direction):
        doc.recompute()
        view.setCameraOrientation(orientations[direction].Q)
        view.fitAll()
        for _ in range(10): QtGui.QApplication.processEvents()
        view.saveImage(str(output/filename),1600,1200,'White')
    for o in doc.Objects:
        if hasattr(o,'Category'): o.ViewObject.Visibility=o.Category!='envelope'
    for filename,direction in [('assembly.png','iso'),('front.png','front'),
                               ('side.png','side'),('right.png','right'),('rear.png','rear'),('top.png','top'),('rear-assembly.png','rear_iso')]:
        render(filename,direction)
    for o in doc.Objects:
        if hasattr(o,'Category'): o.ViewObject.Visibility=o.Category!='exterior'
    render('layout.png','iso')
    for name in ('WaterModule','BubbleModule','Electronics','AudioModule','BatteryRoof','LowerTub','KeelLid'):
        doc.getObject(name).ViewObject.Visibility=False
    render('lower-layout.png','iso')
    # Service diagram: exploded rigid groups; screws and flexible routes removed first.
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=not o.Name.startswith(('PowerCableRoute','WaterHoseRoute')) and 'Screw' not in o.Name
    original_shapes={}
    offsets={'cable_access':V(0,0,-25),'battery':V(0,0,-60),'crown':V(0,0,65),'electronics':V(0,0,35),'Water':V(0,12,40),'Bubble':V(0,12,40),'arc_left':V(-24.5,0,0),'arc_right':V(24.5,0,0)}
    for group,names in service_groups(doc).items():
        for name in names:
            obj=doc.getObject(name);original_shapes[name]=obj.Shape.copy()
            shape=obj.Shape.copy();shape.translate(offsets[group]);obj.Shape=shape
    render('service.png','iso')
    for name,shape in original_shapes.items():doc.getObject(name).Shape=shape
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Category!='exterior'
            o.ViewObject.Transparency=75 if o.Category=='structure' else 0
    render('routing.png','rear_iso')
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Name in ('HeadShell','ElectronicsTray','Electronics','AudioModule','ArcModuleL','ArcModuleR')
            o.ViewObject.Transparency=80 if o.Name=='HeadShell' else 0
    render('arc-layout.png','iso')
    render('arc-top.png','top')
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=getattr(o,'ServiceGroup','')=='crown' or o.Name.startswith('CrownScrew')
            o.ViewObject.Transparency=0
    render('crown-effects.png','iso')
    render('crown-effects-top.png','top')
    for o in doc.Objects:
        if hasattr(o,'Category'):o.ViewObject.Transparency=0
    for o in doc.Objects:
        if hasattr(o,'Category'): o.ViewObject.Visibility=o.Category!='envelope'
    view.setCameraOrientation(orientations['iso'].Q)
    view.fitAll()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    if args.render:
        import FreeCADGui as Gui
        from PySide import QtCore, QtGui
        Gui.showMainWindow()
    source_path = ROOT/'hardware/components/drive-layout/DriveLayout.FCStd'
    source_hash = sha(source_path)
    source = App.openDocument(str(source_path))
    doc = App.newDocument('CyberTrack')
    doc.Label = 'CyberTrack 双履带交互机器人 · 装配候选 0.10'
    doc.Comment = 'Concept only. Unmeasured hardware uses assumed envelopes. No manufacturing release.'
    groups = {}
    for key, label in [('drive','01 双履带与动力参考'),('structure','02 新底盘与分仓'),
                       ('exterior','03 角色头舱与功能外观'),('envelope','04 未实测部件占位')]:
        g = doc.addObject('App::DocumentObjectGroup', key.title())
        g.Label = label; groups[key] = g

    def add(name,label,shape,category,color='body',basis='新设计尺寸；初步概念，未放行'):
        if shape.isNull() or not shape.isValid():
            raise ValueError(f'Invalid geometry: {name}')
        obj = doc.addObject('Part::Feature',name); obj.Label=label;obj.Shape=shape
        obj.addProperty('App::PropertyString','Category','Evidence');obj.Category=category
        obj.addProperty('App::PropertyString','EvidenceBasis','Evidence');obj.EvidenceBasis=basis
        groups[category].addObject(obj)
        if args.render:
            obj.ViewObject.ShapeColor=COLORS[color]
            obj.ViewObject.LineColor=(0.08,0.1,0.12)
            obj.ViewObject.DisplayMode='Flat Lines'
            obj.ViewObject.LineWidth=1.0
            obj.ViewObject.Visibility=category!='envelope'
        return obj

    for src in source.Objects:
        color='dark' if any(k in src.Name for k in ['Rubber','Tread','Lugs','Tires']) else 'metal'
        if 'Coupler' in src.Name: color='power'
        bounds=src.Shape.optimalBoundingBox(False)
        if bounds.XMin>0: dx=14
        elif bounds.XMax<0: dx=-14
        else: raise ValueError(f'Drive side is ambiguous: {src.Name}')
        shifted=src.Shape.copy();shifted.translate(V(dx,0,0))
        add(src.Name,src.Label,shifted,'drive',color,
            f'独立动力参考；本侧整体平移 X={dx} mm，未缩放；物理配合未验证')
    App.closeDocument(source.Name)
    # Wide low front battery bay; the rear keel and low wet backpack retain their layout.
    outline=[(-62,-101),(62,-101),(66,-97),(66,-23),(62,-19),(48,-19),
             (48,70),(44,74),(-44,74),(-48,70),(-48,-19),(-62,-19),(-66,-23),(-66,-97)]
    pts=[V(x,y,28) for x,y in outline]
    outer_plan=Part.Face(Part.makePolygon(pts+[pts[0]]))
    tub=outer_plan.extrude(V(0,0,66))
    # The battery's lower footprint stays fixed; chamfer the upper bay on both sides.
    outer_wedges=[];inner_wedges=[]
    for sign in (-1,1):
        outer_wedges.append(xz_prism([(sign*x,z) for x,z in [(66,65),(11,120),(90,120),(90,65)]],-104,-22))
        inner_wedges.append(xz_prism([(sign*x,z) for x,z in [(63,65),(8,120),(90,120),(90,65)]],-104,-22))
    fore_cavity=box(-63,-98,31,63,-21,96)
    for wedge in inner_wedges: fore_cavity=fore_cavity.cut(wedge)
    tub=tub.cut(fore_cavity).cut(box(-45,-21,31,45,71,96))
    roof_cut=yz_prism([(-103,68.761904762),(-59,74),(-19,90),(23,90),(27,94),(75,94),(75,120),(-103,120)],-70,70)
    for wedge in outer_wedges: tub=tub.cut(wedge)
    tub=tub.cut(roof_cut)
    tub=tub.cut(Part.makeCylinder(20,170,V(-85,0,50),V(1,0,0)))
    tub=tub.cut(box(-61,-97,26,61,-22,32))
    tub=tub.cut(Part.makeCylinder(12.5,10,V(24,70,76),V(0,1,0)))
    add('LowerTub','低位电源前舱／上缘内收切面',tub,'structure','dark')
    add('BatteryHatch','低位平放电源底部维护盖',box(-60.8,-96.8,28,60.8,-22.2,31),'structure','dark')
    for x in (-54,54):
        for y in (-90,-29):
            add('BatteryPad'+str(x).replace('-','N')+str(y).replace('-','N'),'电源底部承托垫',box(x-2.5,y-2.5,31,x+2.5,y+2.5,33),'structure','dark')
    for name,y in [('FrontBulkhead',-21),('RearBulkhead',25)]:
        add(name,'前部干舱隔板' if y<0 else '后部湿舱隔板',box(-45,y,31,45,y+2,94).cut(roof_cut),'structure','metal')
    battery_roof=box(-63,-98,65.5,63,-21,68.5)
    for wedge in inner_wedges: battery_roof=battery_roof.cut(wedge)
    add('BatteryRoof','低位电源上方切边隔板',battery_roof,'structure','metal')
    add('WetDivider','双液体舱中央隔板',box(-1,27,31,1,71,94),'structure','metal')
    for side,sign in [('L',1),('R',-1)]:
        for end,y in [('Front',-28.1),('Rear',28.1)]:
            start=66 if y<0 else 48
            x0,x1=(start,87) if sign>0 else (-87,-start)
            ear=box(x0,y-4,33.4,x1,y+4,41.4)
            ear=ear.cut(Part.makeCylinder(1.8,x1-x0+2,V(x0-1,y,37.4),V(1,0,0)))
            add('MountEar'+side+end,('左' if sign>0 else '右')+('前' if y<0 else '后')+'外移动力安装耳',ear,'structure')
    plan=outer_plan.copy();plan.translate(V(0,0,40))
    roof_bottom=[(-101,69),(-59,74),(-19,90),(23,90),(27,94),(74,94)]
    lid=yz_prism(roof_bottom+[(y,z+3) for y,z in reversed(roof_bottom)],-66,66)
    lid=lid.common(plan.extrude(V(0,0,30)))
    for wedge in outer_wedges: lid=lid.cut(wedge)
    for cx in (-24,24):
        lid=lid.cut(Part.makeCylinder(20.5,6,V(cx,49,92)))
    add('KeelLid','低鼻锥至颈架的折面顶盖',lid,'structure','metal')
    # Fixed twin yokes, machined-looking bearing stacks and rear diagonal stays.
    # These are static concept members, with no actuator or movement claim.
    pedestal=Part.Face(footprint(17,-17,20,6,97)).extrude(V(0,0,5))
    for sign in (-1,1):
        pedestal=pedestal.cut(strut(4.8,(sign*12,16,103),(sign*12,10.68,115.92)))
    add('NeckPedestal','颈架八角基座／斜撑沉座',pedestal,'structure','dark')
    for side,sign in [('L',1),('R',-1)]:
        x0,x1=(18,25) if sign>0 else (-25,-18)
        profile=[(-9,97),(19,97),(22,105),(7,134),(-3,140),(-25,140),(-28,132),(-16,106)]
        neck=yz_prism(profile,x0,x1)
        neck=neck.cut(Part.makeCylinder(8,60,V(-30,-11,128),V(1,0,0)))
        neck=neck.cut(yz_prism([(-9,107),(8,107),(-1,122),(-16,122)],x0-1,x1+1))
        add('NeckYoke'+side,('左' if sign>0 else '右')+'开窗前倾颈架',neck,'structure','metal')
        # A thinner outer plate leaves the inner web visible around its perimeter.
        ax0,ax1=(26,29) if sign>0 else (-29,-26)
        plate=yz_prism([(-7,100),(17,100),(17,105),(4,131),(-4,137),(-23,137),(-24,132),(-13,106)],ax0,ax1)
        plate=plate.cut(Part.makeCylinder(9,70,V(-35,-11,128),V(1,0,0)))
        plate=plate.cut(yz_prism([(-8,109),(5,109),(-2,120),(-13,120)],ax0-1,ax1+1))
        add('NeckOuterWeb'+side,('左' if sign>0 else '右')+'颈架外层加强板',plate,'structure','accent')
        add('NeckBearing'+side,('左' if sign>0 else '右')+'固定横梁阶梯套',ring(11,8,3,V(sign*29,-11,128),V(sign,0,0)),'structure','dark')
        add('NeckCap'+side,('左' if sign>0 else '右')+'横梁端部锁片',Part.makeCylinder(6,2,V(sign*32,-11,128),V(sign,0,0)),'structure','accent')
        # Axial stand-offs bridge the deliberate 1 mm layer spacing.
        for y,z in [(10,104),(-20,136)]:
            add('NeckSpacer'+side+str(z),'颈架层间连接柱 '+side+' '+str(z),Part.makeCylinder(2.5,1,V(sign*25,y,z),V(sign,0,0)),'structure','dark')
        add('NeckStay'+side,('左' if sign>0 else '右')+'后斜撑芯杆',strut(2.8,(sign*12,16,103),(sign*12,2,137)),'structure','metal')
        sleeve=strut(4.8,(sign*12,16,103),(sign*12,10.68,115.92)).cut(strut(2.8,(sign*12,16,103),(sign*12,10.68,115.92)))
        add('NeckStaySleeve'+side,('左' if sign>0 else '右')+'后斜撑固定套筒',sleeve,'structure','dark','固定外观支撑；不是液压或电动推杆')
    add('NeckCrossbar','颈架固定横梁',Part.makeCylinder(7.5,64,V(-32,-11,128),V(1,0,0)),'structure','metal')
    saddle=box(-17,-27,137,17,6,140)
    for sign in (-1,1):
        saddle=saddle.cut(strut(2.8,(sign*12,16,103),(sign*12,2,137)))
    add('NeckHeadSaddle','头舱下方承托鞍座',saddle,'structure','dark')
    for obj in groups['structure'].Group:
        if obj.Name.startswith('Neck'):
            shape=obj.Shape.copy();shape.translate(V(0,0,-4));obj.Shape=shape
    head_start=set(o.Name for o in doc.Objects)
    def face_profile(points, ymin, ymax):
        return xz_prism([(x*1.2,z) for x,z in points],ymin-16,ymax-16)
    def rear_profile(points, ymin, ymax):
        return xz_prism([(x*1.15,z) for x,z in points],ymin,ymax)
    # Faceted helmet: tapered jaw and crown are actual shell geometry, not a box under trim.
    head=faceted_shell_volume([(67,-69,22,10,140),(82,-83,29,10,151),
                               (82,-83,29,10,184),(74,-75,24,10,196)])
    inner=faceted_shell_volume([(65,-67,20,10,143),(79,-80,26,10,152),
                                (79,-80,26,10,183),(72,-73,22,10,193)])
    head=head.cut(inner)
    outer_mask=[(-59,158),(-50,184),(50,184),(59,158),(40,153),(-40,153)]
    inner_mask=[(-53,160),(-47,178),(47,178),(53,160),(35,157),(-35,157)]
    head=head.cut(face_profile(outer_mask,-76,-60))
    head=head.cut(Part.makeCylinder(6.3,24,V(44,-94,149),V(0,1,0)))
    head=head.cut(box(-8,-12,138,8,0,146))
    head=head.cut(box(-25,-40,191,25,0,199))
    rear_head_outer=[(-49,158),(-40,184),(40,184),(49,158),(34,150),(-34,150)]
    rear_head_inner=[(-43,160),(-36,179),(36,179),(43,160),(31,155),(-31,155)]
    head=head.cut(rear_profile(rear_head_outer,21,40))
    add('HeadShell','切面头盔／收窄下颌与后掠顶壳',head,'exterior')
    mask=face_profile(inner_mask,-65,-62)
    for cx in (-29,29):
        mask=mask.cut(Part.makeCylinder(8.5,6,V(cx,-84,167),V(0,1,0)))
    add('SensorMask','内嵌楔形传感器面板',mask,'exterior','visor')
    rim=face_profile(outer_mask,-69,-65).cut(face_profile(inner_mask,-70,-64))
    rim=rim.cut(Part.makeCylinder(6.3,24,V(44,-94,149),V(0,1,0)))
    add('VisorRim','六边形前脸内框',rim,'exterior','dark')
    for side,sign in [('L',1),('R',-1)]:
        brow=[(sign*x,z) for x,z in [(0,179),(0,182),(50,190),(59,182),(56,175),(47,183)]]
        add('BrowArmor'+side,('左' if sign>0 else '右')+'折线眉甲',face_profile(brow,-72,-69),'exterior','body')
        cheek=[(sign*x,z) for x,z in [(39,151),(59,157),(64,171),(67,167),(64,151),(47,143),(36,143)]]
        cheek_shape=face_profile(cheek,-72,-68).cut(Part.makeCylinder(6.3,24,V(44,-94,149),V(0,1,0)))
        add('CheekArmor'+side,('左' if sign>0 else '右')+'斜切颊部护板',cheek_shape,'exterior','metal')
        cx=sign*29
        add('UltrasonicRing'+side,'嵌入式超声波探头框 '+side,ring(8.5,7.5,2,V(cx,-83,167),V(0,1,0)),'exterior','metal','P04 位置及尺寸假设；不是已经选型的传感器')
        add('UltrasonicFace'+side,'超声波探头暗面 '+side,Part.makeCylinder(7.5,1,V(cx,-82,167),V(0,1,0)),'exterior','dark')
    add('SensorStatusStrip','前脸中部窄状态色条',box(-10,-81.5,172,10,-81,173),'exterior','signal','色块示意；不是已选定灯具')
    # Off-centre functional port avoids a smiling face while retaining forward water direction.
    add('WaterPort','偏置短喷水口占位',ring(6,3.5,15,V(44,-89,149),V(0,1,0)),'exterior','dark','P09 外观分配；实际水压、管路与喷嘴尺寸未定')
    jaw=face_profile([(-33,143),(-36,150),(-20,152),(20,152),(23,144),(8,140),(-21,140)],-71,-67.5)
    add('JawArmor','多面下颌中央护片',jaw,'exterior','dark')
    add('JawAccent','下颌偏侧识别片',face_profile([(-28,144),(-29,147),(-15,147),(-14,144)],-71.5,-71),'exterior','accent')
    # Layered side housings: shaped outer guards, recessed circular inserts and vent banks.
    for side,sign in [('L',1),('R',-1)]:
        direction=V(sign,0,0)
        x0,x1=(68,71) if sign>0 else (-71,-68)
        sideguard=yz_prism([(-28,157),(-15,145),(13,147),(23,161),(21,181),(8,190),(-17,187),(-28,174)],x0,x1)
        sideguard=sideguard.cut(Part.makeCylinder(14,8,V(sign*66,-3,167),direction))
        for y in (9,14,19):
            sideguard=sideguard.cut(box(x0-1,y,164,x1+1,y+2,175))
        add('AudioSideGuard'+side,('左' if sign>0 else '右')+'多层音频侧舱护罩',sideguard,'exterior','dark','H07/H08 造型区域；器件和声学未定')
        add('AudioEarRing'+side,('左' if sign>0 else '右')+'侧舱阶梯环',ring(18,14,3,V(sign*71,-3,167),direction),'exterior','body')
        grille=Part.makeCylinder(13.5,2,V(sign*71,-3,167),direction)
        for z in (160,165,170):
            grille=grille.cut(box(min(sign*70,sign*74),-12,z,max(sign*70,sign*74),6,z+2))
        add('AudioEarGrille'+side,('左' if sign>0 else '右')+'侧舱条孔内芯',grille,'exterior','metal')
        add('EarHub'+side,('左' if sign>0 else '右')+'侧舱中心识别片',Part.makeCylinder(5,1.5,V(sign*74,-3,167),direction),'exterior','accent')
        # Low rear-facing crown ribs replace the two upright horn-like fins.
        x0,x1=(39,44) if sign>0 else (-44,-39)
        fin=yz_prism([(-10,196),(18,196),(31,204),(25,207),(5,201),(-10,199)],x0,x1)
        add('CrownFin'+side,('左' if sign>0 else '右')+'后掠顶部封闭脊翼',fin,'exterior','dark','纯外观；不对应高压封装、安装接口或电极')
    for side,sign in [('L',1),('R',-1)]:
        for prefix in ('AudioSideGuard','AudioEarRing','AudioEarGrille','EarHub','CrownFin'):
            obj=doc.getObject(prefix+side);shape=obj.Shape.copy()
            shape.translate(V(sign*(10 if prefix=='CrownFin' else 14),0 if prefix=='CrownFin' else -6,0));obj.Shape=shape
        x0,x1=(82,84) if sign>0 else (-84,-82)
        temple=yz_prism([(-70,156),(-42,156),(-35,168),(-42,181),(-70,181)],x0,x1)
        temple=temple.cut(yz_prism([(-65,165),(-44,165),(-41,169),(-65,169)],x0-1,x1+1))
        add('TempleGuard'+side,('左' if sign>0 else '右')+'前伸太阳穴切面护板',temple,'exterior','dark')
    # Sculpted roof plates stay below the existing crown tips (Z=207 before lowering).
    # Their lower faces sit on the unchanged helmet roof; seams expose the lower shell.
    hatch=faceted_shell_volume([(28,-43,3,5,196),(26,-41,1,5,199),(17,-36,-4,5,203)])
    add('HeadServiceHatch','头顶阶梯隆起检修装甲',hatch,'exterior','metal')
    crest=yz_prism([(-33,203),(-8,203),(-12,205),(-28,205)],-4,4)
    add('CrownSpine','顶冠中央低矮脊甲',crest,'exterior','dark')
    front_roof=faceted_shell_volume([(25,-73,-47,5,196),(21,-69,-50,5,200)])
    add('CrownForePlate','额顶切角斜面装甲',front_roof,'exterior','body')
    for side,sign in [('L',1),('R',-1)]:
        plan=[(32,-64),(40,-70),(61,-70),(70,-61),(70,6),(61,16),(36,16),(32,8)]
        wires=[]
        for top in (False,True):
            points=[V(sign*x,y,204-(x-32)*0.15 if top else 196) for x,y in plan]
            wires.append(Part.makePolygon(points+[points[0]]))
        armor=Part.makeLoft(wires,True,True)
        armor=armor.cut(doc.getObject('CrownFin'+side).Shape)
        add('CrownSideArmor'+side,('左' if sign>0 else '右')+'向外下倾分片顶甲',armor,'exterior','body')
        # The original temple plate remains visible between overlapping upper/lower blades.
        x0,x1=(84,87) if sign>0 else (-87,-84)
        blade=yz_prism([(-72,174),(-50,174),(-36,182),(-43,190),(-64,190),(-72,185)],x0,x1)
        blade=blade.cut(yz_prism([(-65,180),(-49,180),(-44,183),(-63,183)],x0-1,x1+1))
        add('TempleCrest'+side,('左' if sign>0 else '右')+'太阳穴上层折面护甲',blade,'exterior','body')
        lower=yz_prism([(-67,154),(-46,154),(-38,159),(-43,162),(-64,162),(-70,158)],84 if sign>0 else -86.5,86.5 if sign>0 else -84)
        add('TempleLowerBlade'+side,('左' if sign>0 else '右')+'太阳穴下层护片',lower,'exterior','metal')
        arc=ring(22,19,2,V(sign*85,-9,167),V(sign,0,0))
        arc=arc.cut(box(-90,-33,142,90,-10,192))
        add('EarOuterArc'+side,('左' if sign>0 else '右')+'耳舱半环外护弧',arc,'exterior','metal')
    rear_roof=Part.Face(footprint(29,7,22,5,196)).extrude(V(0,0,3))
    add('CrownRearCassette','顶冠后部封闭阶梯座',rear_roof,'exterior','dark')
    for i,y in enumerate((9,13,17)):
        blade=yz_prism([(y,199),(y+2,199),(y+2,200),(y+0.5,201)],-21,21)
        add('CrownRearBlade'+str(i),'顶冠后部错层饰片 '+str(i),blade,'exterior','metal','封闭衬底上的外观饰片；不表示通风或散热性能')
    # Recessed occipital cassette: closed backing and blind louvers, not proven cooling.
    rear_frame=rear_profile(rear_head_outer,27,33).cut(rear_profile(rear_head_inner,26,34))
    add('OccipitalFrame','后脑六边内嵌护框',rear_frame,'exterior','dark')
    add('OccipitalInset','后脑内凹封闭衬板',rear_profile(rear_head_inner,24,27),'exterior','visor')
    rear_spine=[(-5,155),(5,155),(7,174),(0,178),(-7,174)]
    add('OccipitalSpine','后脑中央分层脊甲',rear_profile(rear_spine,27,34),'exterior','body')
    add('OccipitalMark','后脑纵向识别条',box(-2,34,161,2,34.5,171),'exterior','accent')
    for side,sign in [('L',1),('R',-1)]:
        brow=[(sign*x,z) for x,z in [(0,183),(40,190),(53,181),(50,176),(38,185),(0,179)]]
        add('OccipitalBrow'+side,('左' if sign>0 else '右')+'后脑折面上护甲',rear_profile(brow,33,36),'exterior','body')
        for i,z in enumerate((160,166,172)):
            blade=[(sign*x,zz) for x,zz in [(11,z),(34,z),(31,z+2.5),(11,z+2.5)]]
            add('OccipitalLouver'+side+str(i),'后脑封闭格栅饰条 '+side+str(i),rear_profile(blade,27,30),'exterior','metal','封闭浅槽外观；未设计散热性能或进出风路径')
    for obj in doc.Objects:
        if hasattr(obj,'Category') and obj.Name not in head_start:
            shape=obj.Shape.copy();shape.translate(V(0,0,-4));obj.Shape=shape
    # Passive effect-location mockups: widen the existing swept ribs into recessed
    # crown housings. No electrodes, conductor geometry or electrical gap is defined.
    for side,sign in [('L',1),('R',-1)]:
        cx=sign*51.5
        outer=yz_prism([(-16,192),(18,192),(31,200),(25,203),(-8,200),(-16,196)],cx-8,cx+8)
        pocket=Part.Face(footprint(4,-5,20,1.5,196)).extrude(V(0,0,15))
        pocket.translate(V(cx,0,0))
        fin=doc.getObject('CrownFin'+side)
        fin.Shape=outer.cut(pocket).removeSplitter()
        fin.Label=('左' if sign>0 else '右')+'顶部电弧效果位／后掠凹槽护框'
        fin.EvidenceBasis='外观与被动结构占位；无电极、导体或规定放电间隙；不代表防护或绝缘性能'
        armor=doc.getObject('CrownSideArmor'+side)
        armor.Shape=armor.Shape.cut(outer).removeSplitter()
        liner=pocket.common(box(cx-5,-6,196,cx+5,21,196.6))
        add('CrownEffectInset'+side,('左' if sign>0 else '右')+'效果槽封闭衬面',liner,'exterior','metal',
            '封闭槽底上的外观衬面；不是导电部件或已验证绝缘材料')
        for end,y in [('Front',-15),('Rear',16)]:
            if end=='Front':
                # A contrasting strip follows the leading bevel so the location
                # remains readable from the normal front isometric camera.
                marker=yz_prism([(-15,196.5),(-9,199.5),(-9,200.1),(-15,197.1)],cx-6,cx+6)
            else:
                marker=yz_prism([(y,196.6),(y+3,196.6),(y+3,200.3),(y+1,200.8),(y,200.3)],cx-2.3,cx+2.3)
            armor.Shape=armor.Shape.cut(marker).removeSplitter()
            add('CrownEffectMark'+side+end,('左' if sign>0 else '右')+'效果位置橙色端部标识 '+end,
                marker,'exterior','accent','不带电外观标识；不是电极，标识之间的距离不是拉弧间距')
    for side,sign in [('L',1),('R',-1)]:
        x0,x1=(33,46) if sign>0 else (-46,-33)
        shoulder=yz_prism([(-89,73.428571429),(-59,77),(-19,93),(-11,93),(-13,97),(-20,97),(-60,82),(-85,79)],x0,x1)
        add('ShoulderRail'+side,('左' if sign>0 else '右')+'斜面肩部承力梁',shoulder,'structure','body')
        x0,x1=(66,67.5) if sign>0 else (-67.5,-66)
        flank=yz_prism([(-95,39),(-69,39),(-50,62),(-17,80),(8,90),(-22,90),(-60,75),(-93,72),(-99,62)],x0,x1)
        flank=flank.cut(yz_prism([(-89,48),(-72,48),(-56,65),(-67,66),(-90,63)],x0-1,x1+1))
        add('KeelSideFrame'+side,('左' if sign>0 else '右')+'镂空底座侧框',flank,'structure','metal')
    # Preserve wet allocations inside a single faceted backpack with two service lids.
    for name,cx in [('Water',-24),('Bubble',24)]:
        pod=ring(20,17,82,V(cx,49,40))
        if name=='Bubble':
            pod=pod.cut(Part.makeCylinder(12.5,45,V(24,50,76),V(0,1,0)))
        add(name+'Pod',('喷水' if name=='Water' else '泡泡')+'背包内部独立液体舱',pod,'structure','dark')
        add(name+'PodCap',('喷水' if name=='Water' else '泡泡')+'内舱盖占位',Part.makeCylinder(20,3,V(cx,49,122)),'structure','metal','内舱封盖占位；补液和拆卸接口待实测')
    pack=faceted_shell_volume([(48,25,76,6,97),(52,24,81,8,104),(49,25,79,8,128)])
    pack=pack.cut(Part.Face(footprint(46,27,75,6,96)).extrude(V(0,0,30)))
    for name,cx in [('Water',-24),('Bubble',24)]:
        access=Part.Face(footprint(21,29,73,5,125)).extrude(V(0,0,5))
        access.translate(V(cx,0,0))
        pack=pack.cut(access)
    # Two recessed rear equipment panels share one perimeter shell and a central spine.
    panel_outer=[(8,105),(13,100),(38,100),(43,105),(43,118),(38,123),(13,123),(8,118)]
    panel_inner=[(11,106),(14,103),(37,103),(40,106),(40,117),(37,120),(14,120),(11,117)]
    spine=[(-4,60),(4,60),(6,68),(4,121),(0,128),(-4,121),(-6,68)]
    spine_seat=xz_prism(spine,78,86)
    for sign in (-1,1):
        outline=[(sign*x,z) for x,z in panel_outer]
        pack=pack.cut(xz_prism(outline,74,86))
    pack=pack.cut(spine_seat)
    add('BackpackShell','双液体舱共用切面背包壳',pack,'exterior','body','原位液体分配外的共用造型壳；未验证补液、密封或实物容纳')
    for name,cx,color in [('Water',-24,'water'),('Bubble',24,'bubble')]:
        lid=Part.Face(footprint(21,29,73,5,128)).extrude(V(0,0,3));lid.translate(V(cx,0,0))
        add(name+'ServiceLid',('喷水' if name=='Water' else '泡泡')+'背包顶部独立切角维护盖',lid,'exterior','dark')
        handle=yz_prism([(42,131),(58,131),(58,133),(54,135),(46,135),(42,133)],cx-10,cx+10)
        handle=handle.cut(box(cx-7,45,130,cx+7,55,133))
        add(name+'CapGrip',('喷水' if name=='Water' else '泡泡')+'低矮桥形维护握位',handle,'exterior','metal')
        add(name+'LidMark',('喷水' if name=='Water' else '泡泡')+'维护盖分区色条',box(cx-9,64,131,cx+9,67,131.6),'exterior',color)
    for side,sign,color in [('L',1,'bubble'),('R',-1,'water')]:
        outer=[(sign*x,z) for x,z in panel_outer];inner=[(sign*x,z) for x,z in panel_inner]
        frame=xz_prism(outer,79,84).cut(xz_prism(inner,78,85))
        add('PackFrame'+side,('左' if sign>0 else '右')+'背包嵌板护框',frame,'exterior','dark')
        add('PackInset'+side,('左' if sign>0 else '右')+'背包封闭内衬',xz_prism(inner,77,79),'exterior','visor')
        for i,z in enumerate((105,110,115)):
            blade=[(sign*x,zz) for x,zz in [(14,z),(37,z),(35,z+2),(14,z+2)]]
            add('PackLouver'+side+str(i),'背包浅槽饰条 '+side+str(i),xz_prism(blade,79,81),'exterior','metal','封闭浅槽；不是额外风机或已验证的通风口')
        mark=[(sign*x,z) for x,z in [(19,100.5),(32,100.5),(32,102),(19,102)]]
        add('PackMark'+side,'背包液体区识别条 '+side,xz_prism(mark,84,84.6),'exterior',color)
    add('BackpackSpine','背包至底座的中央脊梁护甲',xz_prism(spine,79,85),'exterior','metal')
    # A tapered rear base replaces the flat back wall visually, with an integrated outlet.
    rear_profile0=[(-39,34),(39,34),(47,42),(47,89),(39,97),(-39,97),(-47,89),(-47,42)]
    rear_profile1=[(-34,40),(34,40),(42,48),(42,85),(34,93),(-34,93),(-42,85),(-42,48)]
    wires=[]
    for profile,y in [(rear_profile0,74),(rear_profile1,82)]:
        vs=[V(x,y,z) for x,z in profile];wires.append(Part.makePolygon(vs+[vs[0]]))
    rear_armor=Part.makeLoft(wires,True,True)
    rear_armor=rear_armor.cut(Part.makeCylinder(15.5,25,V(24,72,76),V(0,1,0)))
    rear_armor=rear_armor.cut(spine_seat)
    left_inset=[(-37,63),(-32,59),(-13,59),(-10,63),(-10,85),(-15,89),(-32,89),(-37,84)]
    rear_armor=rear_armor.cut(xz_prism(left_inset,79,86))
    drip=yz_prism([(79,55),(94,55),(96,57),(96,60),(94,60),(94,58),(82,58),(79,57)],4,44)
    rear_armor=rear_armor.cut(drip)
    add('RearBaseArmor','底座斜面后护甲／背包下支座',rear_armor,'exterior','body')
    add('RearBaseInset','底座背部内凹检修饰板',xz_prism(left_inset,79,80),'exterior','dark','检修区域造型；紧固、密封与工具空间未验证')
    for i,z in enumerate((65,72,79)):
        add('RearBaseLouver'+str(i),'底座后部盲槽饰条 '+str(i),xz_prism([(-32,z),(-15,z),(-17,z+2),(-32,z+2)],80,81.5),'exterior','metal')
    duct=ring(12,9,9,V(24,65,76),V(0,1,0))
    add('BubbleDuct','后舱泡泡出口短颈',duct,'exterior','dark','P10 后向出口分配；风机和液路接口未定')
    add('BubbleOutlet','内嵌后向泡泡扩口',ring(15,9,17,V(24,74,76),V(0,1,0)),'exterior','dark')
    bezel=[(24+x,76+z) for x,z in [(-17,-11),(-11,-17),(11,-17),(17,-11),(17,11),(11,17),(-11,17),(-17,11)]]
    bezel=xz_prism(bezel,82,86).cut(Part.makeCylinder(15.2,6,V(24,81,76),V(0,1,0)))
    add('BubbleOutletBezel','泡泡出口八角分层护框',bezel,'exterior','metal')
    add('RearDripLip','后护甲下方折面滴液唇',drip,'exterior','dark','排液轮廓候选；坡度、滴落与防倒流未验证')
    skid=xz_prism([(-32,42),(32,42),(28,48),(-28,48)],82,83)
    add('RearLowerInset','后底座内凹视觉分层',skid,'exterior','dark')
    # Compact low nose: the former chest audio volume is now inside the helmet.
    chest=xz_prism([(-28,38),(28,38),(35,47),(28,63),(-28,63),(-35,47)],-104,-101)
    for z,width in [(44,23),(51,26),(58,23)]:
        chest=chest.cut(xz_prism([(-width,z),(width,z),(width-2,z+2),(-width+2,z+2)],-105,-100))
    add('ChestAudioPanel','低位前舱内嵌饰板',chest,'exterior','dark','沿用对象标识；音频已移入头舱，此处仅为装甲饰板')
    for side,sign in [('L',1),('R',-1)]:
        guard=[(sign*x,z) for x,z in [(36,35),(59,39),(63,46),(55,58),(44,67),(36,66),(48,55),(51,46),(36,42)]]
        add('ChestGuard'+side,('左' if sign>0 else '右')+'低鼻锥折面侧甲',xz_prism(guard,-106,-101),'exterior','body')
        accent=[(sign*x,z) for x,z in [(54,43),(57,44),(56,49),(53,49)]]
        add('ChestAccent'+side,('左' if sign>0 else '右')+'前护甲嵌条',xz_prism(accent,-106.5,-106),'exterior','accent')
    add('LowerChin','前舱薄下缘护片',xz_prism([(-30,32),(30,32),(28,35),(-28,35)],-104,-101),'exterior','body')
    add('ChestBadge','前舱上沿识别片',xz_prism([(-10,64),(10,64),(8,67),(-8,67)],-104,-101),'exterior','metal')
    plinth=yz_prism([(-29,89),(-19,93),(-15,93),(-15,100),(-29,100)],-42,-30).cut(doc.getObject('ShoulderRailR').Shape)
    add('StopPlinth','本地停止操作区基台',plinth,'exterior','dark')
    add('StopControl','后肩本地停止按钮占位',Part.makeCylinder(6,5,V(-35,-22,100)),'exterior','accent','位置假设；型号与切断电路未设计')
    allocations=[('PowerBank','实测充电宝 120×73×31.5／前下方平放',box(-60,-96,33,60,-23,64.5),'power'),
                 ('WaterModule','后部喷水液体区占位 Ø32×70',Part.makeCylinder(16,70,V(-24,49,43)),'water'),
                 ('BubbleModule','后部泡泡液体区占位 Ø32×70',Part.makeCylinder(16,70,V(24,49,43)),'bubble'),
                 ('Electronics','头舱主控／驱动／电源分配区 100×45×34',box(-50,-38,146,50,7,180),'electronics'),
                 ('AudioModule','头舱前部音频区占位 72×36×21',box(-36,-75,146,36,-39,167),'metal')]
    for name,label,shape,color in allocations:
        basis=('用户提供外形 120×73×31.5 mm，确认较重；低位平放位置获用户认可，端口、重量与实物适配未验证'
               if name=='PowerBank' else '空间分配假设；不是所购物料尺寸，不构成整套装入结论')
        add(name,label,shape,'envelope',color,basis)
    for side,sign in [('L',1),('R',-1)]:
        add('ArcModule'+side,('左' if sign>0 else '右')+'电弧模块预装占位 Ø20×80',
            Part.makeCylinder(10,80,V(sign*68.5,-66,158),V(0,1,0)),
            'envelope','accent','用户于 2026-10-24 指定预装尺寸 Ø20×80；非实测，仅被动机械包络，无高压引线、电极或驱动')
    refine(doc,add)
    doc.recompute()
    if args.render:
        for g in groups.values(): g.ViewObject.Visibility=True
        for o in groups['envelope'].Group: o.ViewObject.Visibility=False
        Gui.activeDocument().activeView().viewAxonometric()
        Gui.activeDocument().activeView().fitAll()
    OUT.mkdir(exist_ok=True)
    cad=OUT/'CyberTrack.FCStd';step=OUT/'CyberTrack.step'
    doc.saveAs(str(cad))
    shapes=[o for o in doc.Objects if hasattr(o,'Category')]
    expected={o.Name:o.Shape.copy() for o in shapes}
    # Exclude fictional equipment blocks from neutral exterior assembly export.
    Part.export([o for o in shapes if o.Category!='envelope'],str(step))
    App.closeDocument(doc.Name)
    saved=App.openDocument(str(cad))
    rows=[]
    for o in saved.Objects:
        if not hasattr(o,'Category'): continue
        row=describe(o);old=expected[o.Name]
        same=old.exportBrepToString()==o.Shape.exportBrepToString()
        diff=0.0 if same else old.cut(o.Shape).Volume+o.Shape.cut(old).Volume
        row.update(native_brep_matches=same,symmetric_difference_mm3=diff)
        if not row['valid'] or diff>1e-5: raise ValueError(f'Saved geometry changed: {o.Name}')
        rows.append(row)
    drive=[o for o in saved.Objects if hasattr(o,'Category') and o.Category=='drive']
    new=[o for o in saved.Objects if hasattr(o,'Category') and o.Category in ('structure','exterior')]
    env=[o for o in saved.Objects if hasattr(o,'Category') and o.Category=='envelope']
    bounds={o.Name:o.Shape.optimalBoundingBox(False) for o in drive+new+env}
    collisions=[];tested=0
    pairs=[(a,b) for a in new for b in drive]+[(a,b) for i,a in enumerate(new) for b in new[i+1:]]
    pairs += [(a,b) for a in env for b in drive+new]+[(a,b) for i,a in enumerate(env) for b in env[i+1:]]
    for a,b in pairs:
        if not bounds[a.Name].intersect(bounds[b.Name]): continue
        tested+=1
        common=a.Shape.common(b.Shape).Volume
        if common>0.01: collisions.append({'a':a.Name,'b':b.Name,'volume_mm3':common})
    service_check=check_service_paths(saved)
    assembly=Part.makeCompound([o.Shape for o in drive+new]);bb=assembly.optimalBoundingBox(False)
    step_shape=Part.Shape();step_shape.read(str(step))
    step_delta=abs(step_shape.Volume-assembly.Volume)
    step_bbox_delta=max(abs(getattr(step_shape.optimalBoundingBox(False),k)-getattr(bb,k)) for k in ('XMin','YMin','ZMin','XMax','YMax','ZMax'))
    step_check={'valid':step_shape.isValid(),'solids':len(step_shape.Solids),'expected_solids':len(assembly.Solids),
                'volume_difference_mm3':step_delta,'bbox_difference_mm':step_bbox_delta,
                'volume_comparison_tolerance_mm3':0.01,
                'volume_comparison_passed':step_delta<=0.01,'geometry_equivalence_verified':False,
                'usage':'layout_exchange_only; native FCStd is the geometry source'}
    if not step_check['valid'] or step_check['solids']!=step_check['expected_solids'] or step_bbox_delta>1e-5:
        raise ValueError(step_check)
    if args.render:
        render_views(saved, OUT)
        saved.save()
    # Reopen the final saved file after GUI styling; verify geometry and visibility.
    App.closeDocument(saved.Name)
    final = App.openDocument(str(cad))
    final_shapes = {o.Name:o for o in final.Objects if hasattr(o,'Category')}
    assert set(final_shapes)=={row['name'] for row in rows}
    for row in rows:
        obj=final_shapes[row['name']]
        bbox=obj.Shape.optimalBoundingBox(False)
        coords=[bbox.XMin,bbox.YMin,bbox.ZMin,bbox.XMax,bbox.YMax,bbox.ZMax]
        if max(abs(a-b) for a,b in zip(coords,row['bbox_mm']))>1e-5:
            raise ValueError(f"Final save placement differs: {obj.Name}")
        if (not obj.Shape.isValid() or len(obj.Shape.Solids)!=row['solids']
                or abs(obj.Shape.Volume-row['volume_mm3'])>1e-5):
            raise ValueError(f"Final save differs: {obj.Name}")
    if args.render:
        with zipfile.ZipFile(cad) as archive:
            gui=ET.fromstring(archive.read('GuiDocument.xml'))
            for provider in gui.findall('.//ViewProvider'):
                name=provider.attrib['name']
                if name in final_shapes:
                    visible=provider.find("Properties/Property[@name='Visibility']/Bool").attrib['value']=='true'
                    assert visible==(final_shapes[name].Category!='envelope'),name
    assert sha(source_path)==source_hash
    report={'status':'preliminary_concept','design_revision':'0.10','coordinate_system':'mm; +X left, +Y rear, +Z up; front -Y',
            'bounding_box_method':'optimalBoundingBox(useTriangulation=False, useShapeTolerance=False)',
            'power_bank_dimensions_mm':{'source':'user_measurement','length':120,'width':73,'thickness':31.5,
            'orientation':'length X, width Y, thickness Z; low horizontal placement retained from user-approved layout',
            'envelope_center_z_mm':48.75,'mass_kg':None,
            'reported_product_net_mass_kg':0.373,'mass_source':'P11; user-relayed product specification; not weighed',
            'port_face_source':'user confirmed 120 x 31.5 mm long side',
            'port_orientation_design':'+Y; lateral position and connector envelope are assumptions',
            'ports_and_cable_clearance_verified':False},
            'arc_module_envelopes':{'quantity':2,'diameter_mm':20,'length_mm':80,
                'basis':'user specified provisional envelope on 2026-10-24; not measured',
                'axis':'+Y','axis_origins_mm':[[68.5,-66,158],[-68.5,-66,158]],
                'tray_width_mm':116,'tray_hole_pattern_unchanged':True,
                'mounts_and_leads_designed':False,'electrical_clearance_verified':False,
                'insulation_liquid_isolation_emc_verified':False},
            'crown_effect_locations':{'quantity':2,'center_x_mm':[51.5,-51.5],
                'outer_size_xyz_mm':[16,47,11],'y_range_mm':[-16,31],'z_range_mm':[192,203],
                'recess_plan_mm':[8,25],'recess_y_range_mm':[-5,20],
                'basis':'design allocation for passive appearance mockup; not supplier data',
                'service_group':'crown','electrodes_or_wiring_designed':False,
                'electrical_or_protective_function_verified':False},
            'source_sha256':source_hash,'source_unchanged':True,'drive_transform':{'Left':[14,0,0],'Right':[-14,0,0],'scale':1,'method':'whole side translated, including motor, shaft, coupler and mount'},
            'drive_object_count':len(drive),'track_module_count':2,'objects':rows,
            'assembly_size_xyz_mm':[bb.XLength,bb.YLength,bb.ZLength],
            'step_readback':step_check,'collision_check':{'tolerance_mm3':0.01,'boolean_pairs_tested':tested,
            'scope':'new-to-drive, new-to-new, envelope-to-all; drive internal contacts excluded',
            'overlaps':collisions,'passed':not collisions},
            'service_paths':service_check,
            'manufacturing_released':False,'physical_fit_verified':False,
            'assembly_paths_verified':False,'electrical_verified':False,
            'final_saved_audit':{'native_objects_verified':len(final_shapes),'gui_visibility_verified':args.render},
            'previews_generated':args.render,
            'files_sha256':{p.name:sha(p) for p in [cad,step]+(sorted(OUT.glob('*.png')) if args.render else [])}}
    (OUT/'readback.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('assembly_size_xyz_mm','step_readback','collision_check','service_paths')},ensure_ascii=False,indent=2))
    App.closeDocument(final.Name)
    if args.render:
        # Dispose delayed view widgets while Python and its GIL still exist.
        QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
        Gui.getMainWindow().close()
        QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
        QtGui.QApplication.processEvents()
    if collisions or not service_check['passed']:
        raise ValueError('Static or sampled service overlaps detected; inspect readback.json')


if __name__=='__main__':
    main()
