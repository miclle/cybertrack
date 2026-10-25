"""Third P01 mechanical carrier only; no ESP32 pin or power wiring implementation."""
import FreeCAD as App
import Part
from breadboard_layout import box
from effect_board_mount import zc,vertical_sweep

V=App.Vector
PREFIX='IgnitionMOS'
BASIS='用户确认两只点火模块共用第三块同款P01；33×17平面、总高12及PCB/空白边沿用既有候选，非实测；只做安装位，不构成电气选型或通电验收'


def apply(doc,add):
    def put(n,label,q,category='structure',color='metal'):
        return add(PREFIX+n,label,q.removeSplitter(),category,color,BASIS)
    delta=V(-23,-48.25,-12)
    copies={'EffectMOSL':'Board','EffectSupportLMOS':'Support','EffectRetainerLMOS':'Retainer'}
    for end in ('Inner','Outer'):
        for kind in ('Insert','Screw'):
            copies['EffectRetainer'+kind+'LMOS'+end]='Retainer'+kind+end
    for old,new in copies.items():
        q=doc.getObject(old).Shape.copy();q.translate(delta)
        put(new,'点火P01独立安装位／'+new,q,'envelope' if new=='Board' else 'structure','electronics' if new=='Board' else 'metal')
    tray=box(-18,-90.5,54.5,18,-70.5,56.5)
    tray=tray.cut(box(-17,-89.5,55.5,17,-71.5,56.6))
    wall=box(-18,-90.5,56.5,18,-70.5,57.5).cut(box(-17,-89.5,56.4,17,-71.5,57.6))
    tray=tray.fuse(wall)
    for x in (-20.5,20.5):
        tray=tray.fuse(box(x-3,-83.5,54.5,x+3,-77.5,56.5)).fuse(zc(2.5,56.5,58,x,-80.5))
        tray=tray.cut(zc(1.5,54.9,58.1,x,-80.5))
    lid=doc.KeelLid.Shape.copy()
    for side,x in [('L',23),('R',-23)]:
        y=-88
        tray=tray.fuse(box(min(x-2.8,17.5 if x>0 else -17.5),y-2.8,54.5,max(x+2.8,17.5 if x>0 else -17.5),y+2.8,56.5)).fuse(box(x-2.8,y-2.8,56.5,x+2.8,y+2.8,58.5))
        tray=tray.cut(zc(1.4,54.4,58.6,x,y)).cut(zc(2.6,54.4,56.1,x,y))
        contact=zc(2.8,58.5,100,x,y).common(lid)
        assert contact.Volume>1
        top=contact.BoundBox.ZMin+.5
        lid=lid.fuse(zc(2.8,58.5,top,x,y)).cut(zc(2.1,58.4,63.6,x,y))
        put('MountInsert'+side,'点火MOS托架吊柱嵌件候选 '+side,zc(2,58.6,63.5,x,y).cut(zc(1.25,58.5,63.6,x,y)))
        screw=zc(1.2,56.1,63.1,x,y).fuse(zc(2.4,54.6,56.1,x,y))
        screw=screw.cut(box(x-1.4,y-.5,54.5,x+1.4,y+.5,55.1))
        put('MountScrew'+side,'点火MOS独立托架底部M2.5级候选螺钉 '+side,screw)
    tray=tray.cut(box(-17,-89.5,55.5,17,-71.5,56.6))
    doc.KeelLid.Shape=lid.removeSplitter()
    put('Carrier','点火P01前舱独立可拆托架／两点吊装',tray)
    for side,x0,x1 in [('L',16.5,20.5),('R',-20.5,-16.5)]:
        put('Port'+side,'点火P01板端接线空间假设 '+side,box(x0,-84.5,61,x1,-76.5,65.5),'clearance','signal')
    return dict(board_quantity=1,controlled_modules=2,controller='ESP32-S3; pin unassigned',
        board_lwh_mm=[33,17,12],height_and_edge_geometry_assumed=True,
        board_bbox_mm=[-16.5,-89,56,16.5,-72,68],carrier_floor_z_mm=[54.5,56.5],
        mount_centres_xy_mm=[[23,-88],[-23,-88]],battery_top_z_mm=52.5,
        battery_to_carrier_mm=2,battery_to_mount_screw_mm=2.1,
        removal='remove bottom cover and battery; disconnect low-voltage leads, remove two mount screws; lower complete carrier',
        electrical_design_implemented=False,physical_fit_verified=False)


def check(doc):
    objects={o.Name:o for o in doc.Objects if hasattr(o,'Category')}
    selected={n:o for n,o in objects.items() if n.startswith(PREFIX)}
    def hits(shape,obstacles):
        rows=[]
        for n,o in obstacles.items():
            if shape.BoundBox.intersect(o.Shape.BoundBox):
                v=shape.common(o.Shape).Volume
                if v>.01:rows.append(dict(object=n,volume_mm3=v))
        return rows
    static={n:hits(o.Shape,{k:v for k,v in objects.items() if k!=n and v.Category!='clearance'}) for n,o in selected.items()}
    reserved={n:hits(o.Shape,{k:v for k,v in objects.items() if v.Category=='clearance' and k not in selected})
              for n,o in selected.items() if o.Category!='clearance'}
    moving={n:o for n,o in selected.items() if o.Category!='clearance' and not n.startswith((PREFIX+'Mount',))}
    removed={'PowerBank','BatteryHatch','BatteryPullStrap','BottomServiceCover','PowerCableRoute'}
    removed.update(n for n in objects if n.startswith(('Battery','BottomCoverScrew',PREFIX+'MountScrew')))
    fixed={n:o for n,o in objects.items() if o.Category!='clearance' and n not in moving and n not in removed}
    sweeps={n:hits(vertical_sweep(o.Shape,-80),fixed) for n,o in moving.items()}
    valid=all(o.Shape.isValid() and len(o.Shape.Solids)==(2 if o.Name==PREFIX+'Support' else 1) for o in selected.values())
    return dict(valid=valid,static=static,reserved_spaces=reserved,carrier_down_80=sweeps,
        removal_prerequisites=sorted(removed),passed=valid and not any(static.values()) and not any(reserved.values()) and not any(sweeps.values()),
        physical_fit_verified=False,electrical_verified=False)


def render(doc,output):
    import FreeCADGui as Gui
    from PySide import QtGui
    objects=[o for o in doc.Objects if hasattr(o,'Category')]
    old={o.Name:(o.ViewObject.Visibility,o.ViewObject.Transparency) for o in objects}
    view=Gui.activeDocument().activeView();rot=view.getCameraOrientation()
    try:
        for o in objects:
            o.ViewObject.Visibility=(o.Name.startswith((PREFIX,'Effect')) and o.Category!='clearance') or o.Name in ('PowerBank','KeelLid')
            o.ViewObject.Transparency=85 if o.Name in ('KeelLid','LowerTub') else 60 if o.Name=='PowerBank' else 70 if o.Category=='clearance' else 0
        view.setCameraOrientation(App.Rotation(V(1,1,0),V(-1,1,3),V(1,-1,.75),'ZXY').Q);view.fitAll()
        for _ in range(10):QtGui.QApplication.processEvents()
        view.saveImage(str(output/'ignition-mos-layout.png'),1600,1200,'White')
    finally:
        for o in objects:o.ViewObject.Visibility,o.ViewObject.Transparency=old[o.Name]
        view.setCameraOrientation(rot.Q);view.fitAll()
