import math
import tempfile
from pathlib import Path
import unittest
import cadquery as cq
from geometry import make_part, generate, check_plate, bounds, tessellate_faces

class KernelTests(unittest.TestCase):
    def setUp(self):
        self.part={'id':'knob-01','kind':'cylinder','radius':18,'height':12,'position':[30,6,14]}
    def test_boolean_volume_and_open_axis(self):
        before=make_part(self.part)
        after=make_part(dict(self.part,centerHoleDiameter=8))
        self.assertTrue(after.isValid())
        self.assertEqual(len(after.Solids()),1)
        self.assertAlmostEqual(before.Volume()-after.Volume(),math.pi*4**2*12,places=6)
        for z in [-5.99,0,5.99]: self.assertFalse(after.isInside(cq.Vector(0,0,z),1e-6))
        self.assertTrue(after.isInside(cq.Vector(10,0,0),1e-6))
        for dimension in ['xlen','ylen','zlen']:
            self.assertAlmostEqual(getattr(before.BoundingBox(),dimension),getattr(after.BoundingBox(),dimension),places=6)
    def test_step_and_mesh_come_from_drilled_solid(self):
        with tempfile.TemporaryDirectory() as root:
            result=generate({'revision':'r2','parts':[dict(self.part,centerHoleDiameter=8)]},Path(root)/'out')
            self.assertTrue(result['parts']['knob-01']['stepHoleVoidVerified'])
            self.assertTrue(result['meshes']['knob-01']['indices'])
            shape=cq.importers.importStep(str(Path(root)/'out/knob-01.step')).val()
            for z in [8.01,14,19.99]:self.assertFalse(shape.isInside(cq.Vector(30,6,z),1e-6))
            self.assertAlmostEqual(shape.Volume(),math.pi*(18**2-4**2)*12,places=5)
    def test_face_ranges_cover_mesh_and_distinguish_hole_wall(self):
        shape=make_part(dict(self.part,centerHoleDiameter=8))
        mesh=tessellate_faces(shape)
        self.assertEqual(len(mesh['faces']),len(shape.Faces()))
        cursor=0
        for face in mesh['faces']:
            self.assertEqual(face['start'],cursor)
            self.assertGreater(face['count'],0)
            cursor+=face['count']
        self.assertEqual(cursor*3,len(mesh['indices']))
        walls=[f for f in mesh['faces'] if f['type']=='CYLINDER']
        self.assertEqual(len(walls),2)
        self.assertNotEqual(walls[0]['id'],walls[1]['id'])

    def test_invalid_diameter(self):
        for d in [-8,36,80]:
            with self.assertRaises(ValueError):make_part(dict(self.part,centerHoleDiameter=d))
    def test_spacer_step_dimensions_and_bottom_anchor(self):
        part={'id':'spacer-01','kind':'cylinder','profile':'spacer','radius':10,
              'height':12,'centerHoleDiameter':6.5,'position':[0,0,6]}
        with tempfile.TemporaryDirectory() as root:
            result=generate({'revision':'r2','parts':[part]},Path(root)/'spacer')
            summary=result['parts']['spacer-01']
            self.assertTrue(summary['bottomAnchoredVerified'])
            self.assertTrue(summary['stepBoundsVerified'])
            self.assertTrue(summary['stepWallSolidVerified'])
            shape=cq.importers.importStep(str(Path(root)/'spacer/spacer-01.step')).val()
            self.assertEqual(len(shape.Solids()),1)
            self.assertAlmostEqual(shape.BoundingBox().zmin,0,places=6)
            self.assertAlmostEqual(shape.BoundingBox().zmax,12,places=6)
            # Radius sampled at the inner and outer walls after STEP re-import.
            self.assertFalse(shape.isInside(cq.Vector(3.24,0,6),1e-6))
            self.assertTrue(shape.isInside(cq.Vector(3.26,0,6),1e-6))
            self.assertTrue(shape.isInside(cq.Vector(9.99,0,6),1e-6))
            self.assertFalse(shape.isInside(cq.Vector(10.01,0,6),1e-6))
    def test_empty_document_has_preview_but_no_step(self):
        with tempfile.TemporaryDirectory() as root:
            output=Path(root)/'empty'
            result=generate({'revision':'r1','parts':[]},output)
            self.assertEqual(result['meshes'],{})
            self.assertEqual(result['parts'],{})
            self.assertEqual([p.name for p in output.iterdir()],['preview.json'])
    def plate(self):
        return {'id':'plate-01','kind':'box','profile':'mounting-plate','size':[60,30,4],
                'holeDiameter':6.5,'holeSpacing':40,'position':[0,0,2]}
    def test_plate_step_has_two_exact_holes_and_bottom_anchor(self):
        part=self.plate()
        with tempfile.TemporaryDirectory() as root:
            output=Path(root)/'plate'
            result=generate({'revision':'r2','parts':[part]},output)
            summary=result['parts']['plate-01']
            for key in ['bottomAnchoredVerified','stepBoundsVerified','stepHoleGeometryVerified',
                        'stepHoleVoidVerified','stepWallSolidVerified']:
                self.assertTrue(summary[key],key)
            self.assertEqual(summary['holeCentersMm'],[[-20,0],[20,0]])
            self.assertTrue(result['meshes']['plate-01']['indices'])
            shape=cq.importers.importStep(str(output/'plate-01.step')).val()
            self.assertAlmostEqual(shape.Volume(),7200-2*math.pi*3.25**2*4,places=5)
            for x in [-20,20]:
                for z in [0.01,2,3.99]:
                    self.assertFalse(shape.isInside(cq.Vector(x+3.24,0,z),1e-6))
                    self.assertTrue(shape.isInside(cq.Vector(x+3.26,0,z),1e-6))
            self.assertTrue(shape.isInside(cq.Vector(0,0,2),1e-6))
    def test_plate_check_detects_wrong_positions_even_with_identical_volume(self):
        expected=self.plate()
        wrong=make_part(dict(expected,holeSpacing=44))
        self.assertAlmostEqual(wrong.Volume(),make_part(expected).Volume(),places=5)
        with self.assertRaisesRegex(ValueError,'center, radius or axis'):
            check_plate(wrong,expected)
        tilted=make_part(expected).rotate((0,0,0),(1,0,0),180)
        self.assertTrue(check_plate(tilted,expected)['holeGeometryVerified'])
    def test_exact_bounds_do_not_depend_on_preview_tessellation(self):
        shape=make_part(self.plate())
        before=bounds(shape)
        shape.tessellate(0.05,0.1)
        for actual,expected in zip(bounds(shape),before):
            self.assertAlmostEqual(actual,expected,places=6)
    def test_spacing_edit_step_moves_holes_without_changing_bounds_or_volume(self):
        with tempfile.TemporaryDirectory() as root:
            for spacing in [40,44]:
                part=dict(self.plate(),holeSpacing=spacing)
                output=Path(root)/str(spacing)
                summary=generate({'revision':'r2','parts':[part]},output)['parts']['plate-01']
                self.assertEqual(summary['holeCentersMm'],[[-spacing/2,0],[spacing/2,0]])
                shape=cq.importers.importStep(str(output/'plate-01.step')).val()
                self.assertTrue(check_plate(shape,part,world=True)['holeGeometryVerified'])
                self.assertAlmostEqual(shape.Volume(),7200-2*math.pi*3.25**2*4,places=5)
                # Far edges of the previous holes become solid when spacing expands.
                if spacing==44:
                    for x in [-17,17]:
                        self.assertTrue(shape.isInside(cq.Vector(x,0,2),1e-6))
    def test_plate_kernel_rejects_invalid_geometry(self):
        for patch in [{'holeSpacing':6.5},{'holeSpacing':5},{'holeSpacing':53.5},
                      {'holeDiameter':30},{'size':[60,30,0]},{'size':[float('inf'),30,4]},
                      {'position':[0,0,0]}]:
            with self.assertRaises(ValueError):make_part(dict(self.plate(),**patch))
if __name__=='__main__':unittest.main()
