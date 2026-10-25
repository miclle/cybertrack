"""Passive space study for two pairs of user-specified 1.5 mm leads.

These are clearance volumes, not conductors, protective ducts or HV interfaces.
Module exit orientation, cable length and minimum bend radius remain unknown.
"""
import FreeCAD as App
import Part
from front_effects import ROOTS_XZ

V = App.Vector
PREFIX = 'IgnitionRoute'
TRUNK = [(74,85,130),(62,80,130),(60,30,100),(58,28,79),(58,-17,79),
         (55,-29,59),(55,-86,59)]
BASIS = ('用户给定单线外径1.5 mm、每侧两根；背包附近向内收，经电机顶面内侧，'
         '从前舱肩部入壳并从前脸出线；走廊是空间预算，不是实际线束或绝缘规格。'
         '模块出线端、弯曲半径、固定护盖及实物穿线仍待验证')


def capsule(points, radius):
    # Connected straight clearance segments; square-ended junctions are not
    # a specified cable bend or a protective duct surface.
    shapes=[]
    for a,b in zip(points,points[1:]):
        a,b=V(*a),V(*b)
        shapes.append(Part.makeCylinder(radius,(b-a).Length,a,b-a))
    return shapes[0] if len(shapes)==1 else shapes[0].multiFuse(shapes[1:]).removeSplitter()



def paths():
    result=[]
    for side,sign in [('L',1),('R',-1)]:
        result.append((PREFIX+side,[(sign*x,y,z) for x,y,z in TRUNK],2,None))
        for index,(x,z) in enumerate(ROOTS_XZ,1):
            points=([(sign*55,-86,59),(sign*x,-95,z),(sign*x,-111,z)] if index==1 else
                    [(sign*55,-86,59),(sign*x,-93,59),(sign*x,-97,z),(sign*x,-111,z)])
            result.append((f'{PREFIX}Branch{side}{index}',points,1,
                f'FrontEffectLead{side}{index}'))
    return result


def apply(doc,add):
    allocations=[];cuts=[]
    # Only the front tub, front armour and visual sleeves are perforated.
    # No rear liquid-bay or motor mounting interface is cut.
    for name,points,radius,target in paths():
        tool=capsule(points,radius+.3 if target else radius+.4)
        side='L' if 'L' in name else 'R'
        targets=['LowerTub']+(['ChestGuard'+side,target.replace('Lead','Sleeve')] if target else [])
        for key in targets:
            obj=doc.getObject(key);before=obj.Shape.Volume
            obj.Shape=obj.Shape.cut(tool).removeSplitter()
            cuts.append(dict(route=name,object=key,removed_mm3=before-obj.Shape.Volume,
                             valid=obj.Shape.isValid(),solids=len(obj.Shape.Solids)))
    for name,points,radius,target in paths():
        label=('前端单线接近区' if target else '底盘上表面内收至前舱的双线走廊')
        obj=add(name,label+' '+name,capsule(points,radius),'clearance','signal',BASIS)
        obj.addProperty('App::PropertyString','InterfaceStatus','Evidence')
        obj.InterfaceStatus='front mechanical passages modeled; module terminal and protective fittings unresolved'
        allocations.append(dict(name=name,points_mm=points,allocation_diameter_mm=radius*2,
            polyline_length_mm=sum((V(*b)-V(*a)).Length for a,b in zip(points,points[1:])),
            intended_front_overlap=target))
    return dict(revision='0.48',wire_outer_diameter_mm=1.5,diameter_source='user supplied',
                wires_per_side=2,location='inboard over motor deck; enters front bay at shoulder, exits front face',
                allocations=allocations,front_passage_cuts=cuts,basis=BASIS,
                main_entry_bore_budget_mm=4.8,front_exit_bore_budget_mm=2.6,
                lengths_are_cut_lengths=False,bend_radius_verified=False,
                module_exit_verified=False,physical_fit_verified=False,
                protective_cover_designed=False,electrical_verified=False)


def check(doc):
    routes={o.Name:o for o in doc.Objects if o.Name.startswith(PREFIX)}
    others=[o for o in doc.Objects if hasattr(o,'Category') and o.Name not in routes]
    unexpected=[];interfaces=[];near=[]
    for name,points,radius,target in paths():
        obj=routes[name];area=App.BoundBox(obj.Shape.BoundBox);area.enlarge(6)
        distances=[]
        for other in others:
            if not area.intersect(other.Shape.BoundBox):continue
            volume=0
            if obj.Shape.BoundBox.intersect(other.Shape.BoundBox):
                volume=obj.Shape.common(other.Shape).Volume
            if other.Name==target:
                interfaces.append(dict(route=name,object=other.Name,volume_mm3=volume,
                    distance_mm=obj.Shape.distToShape(other.Shape)[0]))
            elif volume>.01:
                unexpected.append(dict(route=name,object=other.Name,volume_mm3=volume))
            if other.Name!=target:
                distances.append(dict(object=other.Name,category=other.Category,
                                      distance_mm=obj.Shape.distToShape(other.Shape)[0]))
        near.append(dict(route=name,nearest=sorted(distances,key=lambda r:r['distance_mm'])[:8]))
    connections=[]
    for side in ('L','R'):
        for i in (1,2):
            a=routes[PREFIX+side].Shape;b=routes[f'{PREFIX}Branch{side}{i}'].Shape
            connections.append(dict(side=side,branch=i,overlap_mm3=a.common(b).Volume))
    # Reuse exactly the existing sampled service motions, temporarily treating
    # the reserved corridors as installed obstacles. Restore categories even
    # when a check fails; no document geometry or saved category is changed.
    from refine_assembly import check_service_paths
    try:
        for obj in routes.values():obj.Category='envelope'
        service=check_service_paths(doc)
    finally:
        for obj in routes.values():obj.Category='clearance'
    valid=all(o.Shape.isValid() and len(o.Shape.Solids)==1 for o in routes.values())
    return dict(scope='geometric allocation only; no electrical or installation acceptance',
        objects=len(routes),representation='connected straight clearance segments; not manufactured parts',valid=valid,unexpected_overlaps=unexpected,planned_front_interfaces=interfaces,
        nearest_geometry=near,branch_connections=connections,
        sampled_service_with_corridors=service,
        service_with_corridors_passed=service['passed'],
        passed=valid and not unexpected and len(interfaces)==4 and all(r['distance_mm']<1e-5 for r in interfaces) and all(r['overlap_mm3']>.01 for r in connections),
        routing_ready_for_installation=False,module_terminal_connection_complete=False,
        protective_cover_designed=False,bend_radius_verified=False,electrical_verified=False)


def show_default(doc):
    """Persist discoverable route visibility without showing other clearances."""
    group=doc.getObject('FrontIgnitionRouting')
    if group is None:
        group=doc.addObject('App::DocumentObjectGroup','FrontIgnitionRouting')
    group.Label='07 点火线走线（橙色空间）'
    routes=[o for o in doc.Objects if o.Name.startswith(PREFIX) and hasattr(o,'Category')]
    assert len(routes)==6
    clearance=doc.getObject('Clearance')
    for obj in routes:
        if clearance and obj in clearance.Group:clearance.removeObject(obj)
        if obj not in group.Group:group.addObject(obj)
    group.ViewObject.Visibility=True
    for obj in routes:
        obj.ViewObject.ShapeColor=(.98,.38,.03)
        obj.ViewObject.Transparency=15
        obj.ViewObject.Visibility=True


def render(doc,output):
    import FreeCADGui as Gui
    from PySide import QtGui
    objects=[o for o in doc.Objects if hasattr(o,'Category')]
    original={o.Name:(o.ViewObject.Visibility,o.ViewObject.Transparency,o.ViewObject.ShapeColor) for o in objects}
    view=Gui.activeDocument().activeView();rotation=view.getCameraOrientation()
    try:
        for obj in objects:
            obj.ViewObject.Visibility=((obj.Category not in ('envelope','clearance') and obj.Shape.BoundBox.ZMax<130)
                or obj.Name.startswith((PREFIX,'BackpackArc','IgnitionMOS'))
                or obj.Name in ('PowerBank','MotorL','MotorR','WaterModule','BubbleModule'))
            if obj.Name.startswith(PREFIX):obj.ViewObject.ShapeColor=(0.98,0.38,0.03)
            obj.ViewObject.Transparency=(15 if obj.Name.startswith(PREFIX) else 85 if obj.Name in ('LowerTub','KeelLid')
                else 65 if obj.Name in ('PowerBank','WaterModule','BubbleModule') else 0)
        for filename,orientation in [
            ('ignition-routing.png',App.Rotation(V(1,1,0),V(-1,1,3),V(1,-1,.75),'ZXY')),
            ('ignition-routing-rear.png',App.Rotation(V(-1,1,0),V(-1,-1,3),V(1,1,.75),'ZXY')),
            ('ignition-routing-top.png',App.Rotation()),
        ]:
            view.setCameraOrientation(orientation.Q);view.fitAll()
            for _ in range(10):QtGui.QApplication.processEvents()
            view.saveImage(str(output/filename),1600,1200,'White')
    finally:
        for obj in objects:obj.ViewObject.Visibility,obj.ViewObject.Transparency,obj.ViewObject.ShapeColor=original[obj.Name]
        view.setCameraOrientation(rotation.Q);view.fitAll()
