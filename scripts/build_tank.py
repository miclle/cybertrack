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
from head_lift import LIFT, add_neck, apply as lift_head, check as check_head_lift
from rear_armor import mirrored_profile, check_rear_armor
from top_feed import check_top_feed
from bottle_backpack import apply as add_bottle_backpack, check as check_bottle_backpack, render as render_bottle_backpack
from refine_assembly import refine, service_groups, check_service_paths
from breadboard_layout import apply as add_breadboard, check as check_breadboard, render as render_breadboard
from water_gun_layout import add_water_gun, check_water_gun, check_other_service_sweeps
from bubble_gun_layout import add_bubble_gun, check_bubble_gun
from ultrasonic_layout import add_ultrasonic, check_ultrasonic, render_ultrasonic
from ultrasonic_integration import apply as integrate_ultrasonic, check as check_ultrasonic_integration, render as render_ultrasonic_integration
from effects_mount import apply as add_effects_mount, check as check_effects_mount, render as render_effects_mount
from l298n_layout import add_l298n, check_l298n, render_l298n
from l298n_mount import apply as add_l298n_mount, check as check_l298n_mount, render as render_l298n_mount, export_carrier
from speaker_layout import speaker_shape, LABEL as SPEAKER_LABEL, BASIS as SPEAKER_BASIS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'hardware/model'
LEGACY_PREVIEWS = {'arc-layout.png','arc-top.png','controller-layout.png',
                   'controller-access.png','controller-service.png','speaker-layout.png','speaker-top.png'}
V = App.Vector
COLORS = {'body': (0.25, 0.36, 0.43), 'dark': (0.075, 0.10, 0.12),
          'metal': (0.40, 0.48, 0.51), 'light': (0.82, 0.84, 0.80), 'accent': (0.98, 0.32, 0.07),
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
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Category not in ('envelope','clearance') or o.Name in ('WaterModule','BubbleModule','BackpackArcL','BackpackArcR')
            o.ViewObject.Transparency=40 if o.Name in ('WaterModule','BubbleModule') else 0
    for filename,direction in [('assembly.png','iso'),('front.png','front'),
                               ('side.png','side'),('right.png','right'),('rear.png','rear'),('top.png','top'),('rear-assembly.png','rear_iso')]:
        render(filename,direction)
    for o in doc.Objects:
        if hasattr(o,'Category'): o.ViewObject.Visibility=o.Category not in ('exterior','clearance')
    render('layout.png','iso')
    for name in ('WaterModule','BubbleModule','Electronics','AudioModule','LowerTub','KeelLid'):
        if doc.getObject(name): doc.getObject(name).ViewObject.Visibility=False
    render('lower-layout.png','iso')
    # Service diagram: exploded rigid groups; screws and flexible routes removed first.
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Category!='clearance' and not o.Name.startswith(('PowerCableRoute','WaterHoseRoute','BubbleGunHoseRoute','ControllerWireRoute','WaterGunLeadRoute','WaterGunLeadConnector')) and 'Screw' not in o.Name and not o.Name.endswith(('RetentionBand','StrapClosure'))
    from gun_pitch import moved,vector
    from bubble_gun_mount import body_service_shape
    def exploded(shape,group,offset):
        if group=='bubble_gun':return moved(body_service_shape(moved(shape,'bubble',True),15,(-90,10,3)),'bubble')
        s=shape.copy();s.translate(vector(tuple(offset)) if group.startswith('water_gun') else offset);return s
    original_shapes={}
    offsets={'cable_access':V(0,0,-25),'battery':V(0,0,-60),'crown':V(0,0,65),'electronics':V(0,0,35),'Water':V(0,0,150),'Bubble':V(0,0,150),'arc_left':V(-24.5,0,2),'arc_right':V(24.5,0,2),'water_gun':V(0,-45,0),'water_gun_cradle':V(0,0,0),'bubble_gun':V(0,-60,21),'bubble_gun_cradle':V()}
    for group,names in service_groups(doc).items():
        for name in names:
            obj=doc.getObject(name);original_shapes[name]=obj.Shape.copy()
            obj.Shape=exploded(obj.Shape,group,offsets[group])
    render('service.png','iso')
    for name,shape in original_shapes.items():doc.getObject(name).Shape=shape
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Category not in ('exterior','clearance')
            o.ViewObject.Transparency=75 if o.Category=='structure' else 0
    render('routing.png','rear_iso')
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=getattr(o,'ServiceGroup','')=='crown' or o.Name.startswith('CrownScrew')
            o.ViewObject.Transparency=0
    render('crown-effects.png','iso')
    render('crown-effects-top.png','top')
    render_breadboard(doc, output)
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Category not in ('exterior','clearance') or o.Name=='HeadShell'
            o.ViewObject.Transparency=85 if o.Name=='HeadShell' else 0
    render('water-gun-layout.png','iso')
    render('water-gun-side.png','side')
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Name in ('WaterGunBody','WaterGunInlet','WaterGunMaximumEnvelope','NeckCapL','BackpackShell')
            o.ViewObject.Transparency=85 if o.Name in ('WaterGunMaximumEnvelope','BackpackShell') else 0
    render('water-gun-clearance.png','iso')
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Name in ('WaterGunBody','WaterGunInlet')
            o.ViewObject.Transparency=0
    render('water-gun-component.png','iso')
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Name.startswith('WaterGun') and o.Category!='clearance'
            o.ViewObject.Transparency=0
    render('water-gun-mount.png','iso')
    mount_shapes={}
    for group,offset in [('water_gun',V(0,-110,2))]:
        for name in service_groups(doc)[group]:
            obj=doc.getObject(name);mount_shapes[name]=obj.Shape.copy()
            obj.Shape=exploded(obj.Shape,group,offset)
    render('water-gun-service.png','iso')
    for name,shape in mount_shapes.items():doc.getObject(name).Shape=shape
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Name.startswith('WaterGun') or o.Name=='WaterHoseRoute'
            o.ViewObject.Transparency=85 if o.Category=='clearance' else 0
    render('water-gun-spaces.png','iso')
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Name in ('BubbleGunShell','BubbleGunWheel','BubbleGunMotor','BubbleGunGearcase','BubbleGunMountingTab','BubbleGunFrontFoot')
            o.ViewObject.Transparency=0
    render('bubble-gun-component.png','iso')
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Name.startswith('BubbleGun') or o.Name in ('BubblePod','BubbleModule','RearBaseArmor','BackpackShell','BackpackSpine')
            o.ViewObject.Transparency=85 if o.Category=='clearance' or o.Name=='BubblePod' else 0
    render('bubble-gun-clearance.png','rear_iso')
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Category not in ('envelope','clearance') or o.Name in ('WaterModule','BubbleModule','BackpackArcL','BackpackArcR')
            o.ViewObject.Transparency=0
    render('bubble-gun-layout.png','iso')
    render('bubble-gun-side.png','side')
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Name.startswith('BubbleGun') and o.Category not in ('clearance','envelope')
            o.ViewObject.Transparency=0
    render('bubble-gun-mount.png','iso')
    original={}
    for group,offset in [('bubble_gun',V(-90,10,3))]:
        for name in service_groups(doc)[group]:
            obj=doc.getObject(name);original[name]=obj.Shape.copy();obj.Shape=exploded(obj.Shape,group,offset)
    render('bubble-gun-service.png','iso')
    for name,shape in original.items():doc.getObject(name).Shape=shape
    for o in doc.Objects:
        if hasattr(o,'Category'):
            o.ViewObject.Visibility=o.Name.startswith('BubbleGun') or o.Name in ('WaterHoseRoute','ShoulderRailR','StopControl')
            o.ViewObject.Transparency=85 if o.Category=='clearance' else 0
    render('bubble-gun-spaces.png','iso')
    for o in doc.Objects:
        if hasattr(o,'Category'):o.ViewObject.Transparency=40 if o.Name in ('WaterModule','BubbleModule') else 0
    for o in doc.Objects:
        if hasattr(o,'Category'): o.ViewObject.Visibility=o.Category not in ('envelope','clearance') or o.Name in ('WaterModule','BubbleModule','BackpackArcL','BackpackArcR')
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
    doc.Label = 'CyberTrack 双履带交互机器人 · 装配候选 0.43'
    doc.Comment = 'Concept only. Unmeasured hardware uses assumed envelopes. No manufacturing release.'
    groups = {}
    for key, label in [('drive','01 双履带与动力参考'),('structure','02 新底盘与分仓'),
                       ('exterior','03 角色头舱与功能外观'),('envelope','04 实测与暂定部件包络'),('clearance','05 检修与天线预留空间'),('component','06 实测部件／轮廓假设')]:
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
    add_neck(doc,add)
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
    head=head.cut(box(-8,-12,138,8,0,146))
    head=head.cut(box(-25,-40,191,25,0,199))
    rear_head_outer=[(-49,158),(-40,184),(40,184),(49,158),(34,150),(-34,150)]
    rear_head_inner=[(-43,160),(-36,179),(36,179),(43,160),(31,155),(-31,155)]
    head=head.cut(rear_profile(rear_head_outer,21,40))
    add('HeadShell','切面头盔／收窄下颌与后掠顶壳',head,'exterior')
    rim=face_profile(outer_mask,-69,-65).cut(face_profile(inner_mask,-70,-64))
    add('VisorRim','六边形前脸内框',rim,'exterior','dark')
    for side,sign in [('L',1),('R',-1)]:
        brow=[(sign*x,z) for x,z in [(0,179),(0,182),(50,190),(59,182),(56,175),(47,183)]]
        add('BrowArmor'+side,('左' if sign>0 else '右')+'折线眉甲',face_profile(brow,-72,-69),'exterior','body')
        cheek=[(sign*x,z) for x,z in [(39,151),(59,157),(64,171),(67,167),(64,151),(47,143),(36,143)]]
        cheek_shape=face_profile(cheek,-72,-68)
        add('CheekArmor'+side,('左' if sign>0 else '右')+'斜切颊部护板',cheek_shape,'exterior','metal')
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
    mask=face_profile(inner_mask,-65,-62)
    mask.translate(V(0,0,-4))
    add_ultrasonic(add,mask)
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
    # Closed, mirror-symmetric rear armor; both suction hoses enter from above.
    rear_profile0=mirrored_profile([(39,34),(47,42),(47,89),(39,97)])
    rear_profile1=mirrored_profile([(34,40),(42,48),(42,85),(34,93)])
    wires=[]
    for profile,y in [(rear_profile0,74),(rear_profile1,82)]:
        vs=[V(x,y,z) for x,z in profile];wires.append(Part.makePolygon(vs+[vs[0]]))
    rear_armor=Part.makeLoft(wires,True,True)
    rear_armor=rear_armor.cut(spine_seat)
    add('RearBaseArmor','底座斜面后护甲／背包下支座',rear_armor,'exterior','body')
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
                 ('AudioModule',SPEAKER_LABEL,speaker_shape(),'metal')]
    for name,label,shape,color in allocations:
        basis=('用户提供外形 120×73×31.5 mm，确认较重；低位平放位置获用户认可，端口、重量与实物适配未验证'
               if name=='PowerBank' else '空间分配假设；不是所购物料尺寸，不构成整套装入结论')
        if name=='AudioModule': basis=SPEAKER_BASIS
        add(name,label,shape,'envelope',color,basis)
    for side,sign in [('L',1),('R',-1)]:
        add('ArcModule'+side,('左' if sign>0 else '右')+'电弧模块预装占位 Ø25.5×70',
            Part.makeCylinder(12.75,70,V(sign*65.5,-66,156.5),V(0,1,0)),
            'envelope','accent','用户于 2026-10-24 指定预装尺寸 Ø25.5×70；非实测，仅被动机械包络，无高压引线、电极或驱动')
    controller_info=refine(doc,add)
    rail_bases={n:doc.getObject(n).Shape.copy() for n in ('ShoulderRailL','ShoulderRailR')}
    water_info=add_water_gun(doc,add,args.render)
    bubble_info=add_bubble_gun(doc,add,args.render)
    from gun_pitch import apply_pitch,local_frame
    pitch_info=apply_pitch(doc,rail_bases)
    from drive_mount import apply as apply_drive_mount
    apply_drive_mount(doc,add)
    from drive_service import apply as apply_drive_service
    apply_drive_service(doc,add)
    l298n_info=add_l298n(doc,add)
    l298n_mount_info=add_l298n_mount(doc,add)
    bottle_info=add_bottle_backpack(doc,add)
    lift_head(doc,controller_info,l298n_info)
    breadboard_info=add_breadboard(doc,add)
    ultrasonic_info=integrate_ultrasonic(doc,add,args.render)
    effects_info=add_effects_mount(doc,add)
    for kind,info in [('water',water_info),('bubble',bubble_info)]:
        info['pre_pitch_origin_mm']=info['origin_mm']
        info['origin_mm']=pitch_info['muzzle_centres_world_mm'][kind]
        info['orientation']=f"frontward with {pitch_info['elevation_degrees']:g}-degree upward elevation; +X unchanged"
        info['pre_pitch_rotation_degrees']=info.pop('rotation_degrees')
        info['placement_transform']='pre-pitch placement, then gun_pitch pivot rotation and translation'
        info['mount']['coordinate_frame']='pre-pitch module frame; apply gun_pitch for installed world coordinates'
        key='maximum_bbox_mm' if kind=='water' else 'inspection_bbox_mm'
        info['pre_pitch_'+key]=info[key]
        info[key]=describe(doc.getObject('WaterGunMaximumEnvelope' if kind=='water' else 'BubbleGunInspectionEnvelope'))['bbox_mm']
    doc.recompute()
    if args.render:
        for g in groups.values(): g.ViewObject.Visibility=True
        for key in ('envelope','clearance'):
            for o in groups[key].Group:o.ViewObject.Visibility=False
        Gui.activeDocument().activeView().viewAxonometric()
        Gui.activeDocument().activeView().fitAll()
    OUT.mkdir(exist_ok=True)
    cad=OUT/'CyberTrack.FCStd';step=OUT/'CyberTrack.step'
    print('Saving assembly',flush=True)
    doc.saveAs(str(cad))
    shapes=[o for o in doc.Objects if hasattr(o,'Category')]
    expected={o.Name:o.Shape.copy() for o in shapes}
    # Exclude fictional equipment blocks from neutral exterior assembly export.
    Part.export([o for o in shapes if o.Category not in ('envelope','clearance')],str(step))
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
    new=[o for o in saved.Objects if hasattr(o,'Category') and o.Category in ('structure','exterior','component')]
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
    print('Static checks complete; service checks',flush=True)
    service_check=check_service_paths(saved)
    with local_frame(saved,'water',service_check) as local_service:
        water_check=check_water_gun(saved)
        water_check['other_service_sweeps']=check_other_service_sweeps(saved,local_service)
    with local_frame(saved,'bubble',service_check) as local_service:
        bubble_check=check_bubble_gun(saved,local_service)
    for check in (water_check,bubble_check):
        check['coordinate_frame']='checks evaluated in inverse-pitched module frame; dimensions and displacement vectors use pre-pitch axes; see gun_pitch for world transform'
    water_check['passed']=water_check['passed'] and water_check['other_service_sweeps']['passed']
    print('Gun checks complete; breadboard and export',flush=True)
    breadboard_check=check_breadboard(saved)
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
        render_bottle_backpack(saved, OUT)
        render_ultrasonic(saved, OUT)
        render_ultrasonic_integration(saved, OUT)
        render_effects_mount(saved, OUT)
        render_l298n(saved, OUT)
        render_l298n_mount(saved, OUT)
        from drive_service import render_drive_views
        render_drive_views(saved, OUT)
        # Keep the exposed bottle envelopes visible in the saved assembly.
        for o in saved.Objects:
            if hasattr(o,'Category'):
                o.ViewObject.Visibility=o.Category not in ('envelope','clearance') or o.Name in ('WaterModule','BubbleModule','BackpackArcL','BackpackArcR')
                o.ViewObject.Transparency=40 if o.Name in ('WaterModule','BubbleModule') else 0
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
                    assert visible==(final_shapes[name].Category not in ('envelope','clearance') or name in ('WaterModule','BubbleModule','BackpackArcL','BackpackArcR')),name
    assert sha(source_path)==source_hash
    from drive_service_check import check as check_drive_mount
    print('Final readback; drive and bottle checks',flush=True)
    drive_mount_check=check_drive_mount(final,verbose=True)
    effects_check=check_effects_mount(final)
    report={'status':'preliminary_concept','design_revision':'0.43','coordinate_system':'mm; +X left, +Y rear, +Z up; front -Y',
            'drive_mount_check':drive_mount_check,
            'head_lift_check':check_head_lift(final),
            'rear_armor_symmetry_check':check_rear_armor(final),
            'top_feed_check':check_top_feed(final),
            'bottle_backpack':bottle_info,'bottle_backpack_check':check_bottle_backpack(final),
            'bounding_box_method':'optimalBoundingBox(useTriangulation=False, useShapeTolerance=False)',
            'power_bank_dimensions_mm':{'source':'user_measurement','length':120,'width':73,'thickness':31.5,
            'orientation':'length X, width Y, thickness Z; low horizontal placement retained from user-approved layout',
            'envelope_center_z_mm':48.75,'mass_kg':None,
            'reported_product_net_mass_kg':0.373,'mass_source':'P11; user-relayed product specification; not weighed',
            'port_face_source':'user confirmed 120 x 31.5 mm long side',
            'port_orientation_design':'+Y; lateral position and connector envelope are assumptions',
            'ports_and_cable_clearance_verified':False},
            'arc_module_envelopes':{'quantity':2,'status':'passive backpack-side body candidates; no HV leads, electrode or drive'},
            'crown_effect_locations':{'quantity':2,'center_x_mm':[51.5,-51.5],
                'outer_size_xyz_mm':[16,47,11],'y_range_mm':[-16,31],'z_range_mm':[192+LIFT,203+LIFT],
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
            'water_gun_layout':water_info,'water_gun_check':water_check,
            'bubble_gun_layout':bubble_info,'bubble_gun_check':bubble_check,'gun_pitch':pitch_info,
            'service_paths':service_check,'breadboard_layout':breadboard_info,'breadboard_check':breadboard_check,
            'l298n_layout':l298n_info, 'l298n_check':check_l298n(final),
            'l298n_mount':l298n_mount_info, 'l298n_mount_check':check_l298n_mount(final),
            'ultrasonic_check':check_ultrasonic(final),
            'ultrasonic_layout':ultrasonic_info,'ultrasonic_integration_check':check_ultrasonic_integration(final),
            'effects_layout':effects_info,'effects_mount_check':effects_check,
            'manufacturing_released':False,'physical_fit_verified':False,
            'assembly_paths_verified':False,'electrical_verified':False,
            'final_saved_audit':{'native_objects_verified':len(final_shapes),'gui_visibility_verified':args.render},
            'previews_generated':args.render,
            'historical_previews_not_current':sorted(LEGACY_PREVIEWS),
            'drive_preview_note':'Drive-only views use lighter technical colors; geometry is from the same final saved FCStd. Bottom view has front -Y downward.',
            'files_sha256':{p.name:sha(p) for p in [cad,step]+([p for p in sorted(OUT.glob('*.png')) if p.name not in LEGACY_PREVIEWS] if args.render else [])}}
    report['top_feed_check']['source_sha256']=sha(cad)
    report['effects_mount_check']['source_sha256']=sha(cad)
    report['effects_mount_check']['saved_and_reopened']=True
    (OUT/'effects-mount-audit.json').write_text(json.dumps(report['effects_mount_check'],ensure_ascii=False,indent=2)+'\n')
    board_audit={**effects_check['board_mount'],'source_sha256':sha(cad),'saved_and_reopened':True}
    (OUT/'effect-board-fit-audit.json').write_text(json.dumps(board_audit,ensure_ascii=False,indent=2)+'\n')
    report['top_feed_check']['saved_and_reopened']=True
    (OUT/'top-feed-audit.json').write_text(json.dumps(report['top_feed_check'],ensure_ascii=False,indent=2)+'\n')
    report['rear_armor_symmetry_check']['source_sha256']=sha(cad)
    report['rear_armor_symmetry_check']['saved_and_reopened']=True
    (OUT/'rear-armor-symmetry-audit.json').write_text(json.dumps(report['rear_armor_symmetry_check'],ensure_ascii=False,indent=2)+'\n')
    report['ultrasonic_check']['source_after_sha256']=sha(cad)
    report['ultrasonic_check']['saved_and_reopened']=True
    (OUT/'ultrasonic-fit-audit.json').write_text(json.dumps(report['ultrasonic_check'],ensure_ascii=False,indent=2)+'\n')
    report['ultrasonic_integration_check']['source_sha256']=sha(cad)
    (OUT/'ultrasonic-integration-audit.json').write_text(json.dumps(report['ultrasonic_integration_check'],ensure_ascii=False,indent=2)+'\n')
    report['breadboard_check']['source_sha256']=sha(cad)
    report['breadboard_check']['saved_and_reopened']=True
    (OUT/'breadboard-fit-audit.json').write_text(json.dumps(report['breadboard_check'],ensure_ascii=False,indent=2)+'\n')
    report['drive_mount_check']['source_sha256']=sha(cad)
    report['drive_mount_check']['saved_and_reopened']=True
    (OUT/'drive-mount-audit.json').write_text(json.dumps(report['drive_mount_check'],ensure_ascii=False,indent=2)+'\n')
    report['l298n_mount_check']['source_after_sha256']=sha(cad)
    report['l298n_mount_check']['saved_and_reopened']=True
    report['l298n_mount_check']['carrier_export']=export_carrier(final,OUT)
    (OUT/'l298n-mount-audit.json').write_text(json.dumps(report['l298n_mount_check'],ensure_ascii=False,indent=2)+'\n')
    report['l298n_check']['source_after_sha256']=sha(cad)
    report['l298n_check']['saved_and_reopened']=True
    (OUT/'l298n-fit-audit.json').write_text(json.dumps(report['l298n_check'],ensure_ascii=False,indent=2)+'\n')
    report['bottle_backpack_check']['source_sha256']=sha(cad)
    report['bottle_backpack_check']['saved_and_reopened']=True
    (OUT/'bottle-backpack-audit.json').write_text(json.dumps(report['bottle_backpack_check'],ensure_ascii=False,indent=2)+'\n')
    report['head_lift_check']['assembly_revision']=report['design_revision']
    report['head_lift_check']['source_sha256']=sha(cad)
    report['head_lift_check']['saved_and_reopened']=True
    (OUT/'head-lift-audit.json').write_text(json.dumps(report['head_lift_check'],ensure_ascii=False,indent=2)+'\n')
    (OUT/'readback.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('assembly_size_xyz_mm','step_readback','collision_check','service_paths')},ensure_ascii=False,indent=2))
    App.closeDocument(final.Name)
    if args.render:
        # Dispose delayed view widgets while Python and its GIL still exist.
        QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
        Gui.getMainWindow().close()
        QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.DeferredDelete)
        QtGui.QApplication.processEvents()
    if not effects_check['passed'] or not report['ultrasonic_integration_check']['passed'] or not report['head_lift_check']['passed'] or not report['bottle_backpack_check']['passed'] or not report['l298n_mount_check']['passed'] or not report['l298n_check']['passed'] or not drive_mount_check['passed'] or not report['top_feed_check']['passed'] or not report['rear_armor_symmetry_check']['passed'] or not report['ultrasonic_check']['passed'] or not bubble_check['passed'] or collisions or not service_check['passed'] or not breadboard_check['passed'] or not water_check['passed'] or not water_check['removal']['passed']:
        raise ValueError('Static or sampled service overlaps detected; inspect readback.json')


if __name__=='__main__':
    main()
