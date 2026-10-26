"""Local printable repairs; preserve existing mounting coordinates and other parts."""
import FreeCAD as A
import Part


def connect_lid_posts(lid, obstacles):
    """Join rear tray posts inward around the lower tub, retaining screw bores.

    Two 3 mm ribs run from X=±49 to ±40, Y=-28..-25, Z=79..89.
    Small translated obstacle cuts provide a 0.3 mm axis-wise fitting budget.
    """
    ribs=Part.makeBox(9,3,10,A.Vector(40,-28,79)).fuse(
        Part.makeBox(9,3,10,A.Vector(-49,-28,79)))
    for obstacle in obstacles:
        for offset in [(0,0,0),(.3,0,0),(-.3,0,0),(0,.3,0),(0,-.3,0),(0,0,.3),(0,0,-.3)]:
            tool=obstacle.copy();tool.translate(A.Vector(*offset))
            ribs=ribs.cut(tool)
    result=lid.fuse(ribs).removeSplitter()
    assert result.isValid() and len(result.Solids)==1, 'Lid ribs must connect both tray posts'
    return result
