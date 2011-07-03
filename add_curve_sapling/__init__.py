#====================== BEGIN GPL LICENSE BLOCK ======================
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
#======================= END GPL LICENSE BLOCK ========================

bl_info = {
    "name": "Sapling",
    "author": "Andrew Hale (TrumanBlending)",
    "version": (0, 2, 1),
    "blender": (2, 5, 8),
    "api": 37702,
    "location": "View3D > Add > Curve",
    "description": ("Adds a parametric tree. The method is presented by "
    "Jason Weber & Joseph Penn in their paper 'Creation and Rendering of "
    "Realistic Trees'."),
    "warning": "",  # used for warning icon and text in addons panel
    "wiki_url": "",
    "tracker_url": "",
    "category": "Add Curve"}

if "bpy" in locals():
    import imp
    imp.reload(utils)
else:
    from add_curve_sapling import utils

import bpy
import time
import os

#from utils import *
from mathutils import *
from math import pi, sin, degrees, radians, atan2, copysign
from random import random, uniform, seed, choice, getstate, setstate
from bpy.props import *

from add_curve_sapling.utils import *

#global splitError
useSet = False

shapeList = [('0', 'Conical', 'Shape = 0'),
            ('1', 'Spherical', 'Shape = 1'),
            ('2', 'Hemispherical', 'Shape = 2'),
            ('3', 'Cylindrical', 'Shape = 3'),
            ('4', 'Tapered Cylindrical', 'Shape = 4'),
            ('5', 'Flame', 'Shape = 5'),
            ('6', 'Inverse Conical', 'Shape = 6'),
            ('7', 'Tend Flame', 'Shape = 7')]

handleList = [('0', 'Auto', 'Auto'),
                ('1', 'Vector', 'Vector')]

settings = [('0', 'Geometry', 'Geometry'),
            ('1', 'Branch Splitting', 'Branch Splitting'),
            ('2', 'Branch Growth', 'Branch Growth'),
            ('3', 'Pruning', 'Pruning'),
            ('4', 'Leaves', 'Leaves'),
            ('5', 'Armature', 'Armature')]


class ExportData(bpy.types.Operator):
    '''This operator handles writing presets to file'''
    bl_idname = 'sapling.export'
    bl_label = 'Export Preset'

    data = StringProperty()

    def execute(self, context):
        # Unpack some data from the input
        data, filename = eval(self.data)
        try:
            # Check whether the file exists by trying to open it.
            f = open(os.path.join(bpy.utils.script_paths()[0], 'addons', 'add_curve_sapling', 'presets', filename + '.py'), 'r')
            f.close()
            # If it exists then report an error
            self.report({'ERROR_INVALID_INPUT'}, 'Preset Already Exists')
            return {'CANCELLED'}
        except IOError:
            if data:
                # If it doesn't exist, create the file with the required data
                f = open(os.path.join(bpy.utils.script_paths()[0], 'addons', 'add_curve_sapling', 'presets', filename + '.py'), 'w')
                f.write(data)
                f.close()
                return {'FINISHED'}
            else:
                return {'CANCELLED'}


class ImportData(bpy.types.Operator):
    '''This operator handles importing existing presets'''
    bl_idname = 'sapling.import'
    bl_label = 'Import Preset'

    filename = StringProperty()

    def execute(self, context):
        # Make sure the operator knows about the global variables
        global settings, useSet
        # Read the preset data into the global settings
        f = open(os.path.join(bpy.utils.script_paths()[0], 'addons', 'add_curve_sapling', 'presets', self.filename), 'r')
        settings = f.readline()
        f.close()
        settings = eval(settings)
        # Set the flag to use the settings
        useSet = True
        return {'FINISHED'}


class PresetMenu(bpy.types.Menu):
    '''Create the preset menu by finding all preset files
    in the preset directory
    '''
    bl_idname = "sapling.presetmenu"
    bl_label = "Presets"

    def draw(self, context):
        # Get all the sapling presets
        presets = [a for a in os.listdir(os.path.join(bpy.utils.script_paths()[0], 'addons', 'add_curve_sapling', 'presets')) if a[-3:] == '.py']
        layout = self.layout
        # Append all to the menu
        for p in presets:
            layout.operator("sapling.import", text=p[:-3]).filename = p


class AddTree(bpy.types.Operator):
    bl_idname = "curve.tree_add"
    bl_label = "Sapling"
    bl_options = {'REGISTER', 'UNDO'}

    chooseSet = EnumProperty(name='Settings',
        description='Choose the settings to modify',
        items=settings,
        default='0')
    bevel = BoolProperty(name='Bevel',
        description='Whether the curve is bevelled',
        default=False)
    prune = BoolProperty(name='Prune',
        description='Whether the tree is pruned',
        default=False)
    showLeaves = BoolProperty(name='Show Leaves',
        description='Whether the leaves are shown',
        default=False)
    useArm = BoolProperty(name='Use Armature',
        description='Whether the armature is generated',
        default=False)
    seed = IntProperty(name='Random Seed',
        description='The seed of the random number generator',
        default=0)
    handleType = IntProperty(name='Handle Type',
        description='The type of curve handles',
        min=0,
        max=1,
        default=0)
    levels = IntProperty(name='Levels',
        description='Number of recursive branches (Levels)',
        min=1,
        max=6,
        default=3)
    length = FloatVectorProperty(name='Length',
        description='The relative lengths of each branch level (nLength)',
        min=0.0,
        default=[1, 0.3, 0.6, 0.45],
        size=4)
    lengthV = FloatVectorProperty(name='Length Variation',
        description='The relative length variations of each level (nLengthV)',
        min=0.0,
        default=[0, 0, 0, 0],
        size=4)
    branches = IntVectorProperty(name='Branches',
        description='The number of branches grown at each level (nBranches)',
        min=0,
        default=[50, 30, 10, 10],
        size=4)
    curveRes = IntVectorProperty(name='Curve Resolution',
        description='The number of segments on each branch (nCurveRes)',
        min=1,
        default=[3, 5, 3, 1],
        size=4)
    curve = FloatVectorProperty(name='Curvature',
        description='The angle of the end of the branch (nCurve)',
        default=[0, -40, -40, 0],
        size=4)
    curveV = FloatVectorProperty(name='Curvature Variation',
        description='Variation of the curvature (nCurveV)',
        default=[20, 50, 75, 0],
        size=4)
    curveBack = FloatVectorProperty(name='Back Curvature',
        description='Curvature for the second half of a branch (nCurveBack)',
        default=[0, 0, 0, 0],
        size=4)
    baseSplits = IntProperty(name='Base Splits',
        description='Number of trunk splits at its base (nBaseSplits)',
        min=0,
        default=0)
    segSplits = FloatVectorProperty(name='Segment Splits',
        description='Number of splits per segment (nSegSplits)',
        min=0,
        default=[0, 0, 0, 0],
        size=4)
    splitAngle = FloatVectorProperty(name='Split Angle',
        description='Angle of branch splitting (nSplitAngle)',
        default=[0, 0, 0, 0],
        size=4)
    splitAngleV = FloatVectorProperty(name='Split Angle Variation',
        description='Variation in the split angle (nSplitAngleV)',
        default=[0, 0, 0, 0],
        size=4)
    scale = FloatProperty(name='Scale',
        description='The tree scale (Scale)',
        min=0.0,
        default=13.0)
    scaleV = FloatProperty(name='Scale Variation',
        description='The variation in the tree scale (ScaleV)',
        default=3.0)
    attractUp = FloatProperty(name='Vertical Attraction',
        description='Branch upward attraction',
        default=0.0)
    shape = EnumProperty(name='Shape',
        description='The overall shape of the tree (Shape)',
        items=shapeList,
        default='7')
    baseSize = FloatProperty(name='Base Size',
        description='Fraction of tree height with no branches (BaseSize)',
        min=0.0,
        max=1.0,
        default=0.4)
    ratio = FloatProperty(name='Ratio',
        description='Base radius size (Ratio)',
        min=0.0,
        default=0.015)
    taper = FloatVectorProperty(name='Taper',
        description='The fraction of tapering on each branch (nTaper)',
        min=0.0,
        max=1.0,
        default=[1, 1, 1, 1],
        size=4)
    ratioPower = FloatProperty(name='Branch Radius Ratio',
        description=('Power which defines the radius of a branch compared to '
        'the radius of the branch it grew from (RatioPower)'),
        min=0.0,
        default=1.2)
    downAngle = FloatVectorProperty(name='Down Angle',
        description=('The angle between a new branch and the one it grew '
        'from (nDownAngle)'),
        default=[90, 60, 45, 45],
        size=4)
    downAngleV = FloatVectorProperty(name='Down Angle Variation',
        description='Variation in the down angle (nDownAngleV)',
        default=[0, -50, 10, 10],
        size=4)
    rotate = FloatVectorProperty(name='Rotate Angle',
        description=('The angle of a new branch around the one it grew from '
        '(nRotate)'),
        default=[140, 140, 140, 77],
        size=4)
    rotateV = FloatVectorProperty(name='Rotate Angle Variation',
        description='Variation in the rotate angle (nRotateV)',
        default=[0, 0, 0, 0],
        size=4)
    scale0 = FloatProperty(name='Radius Scale',
        description='The scale of the trunk radius (0Scale)',
        min=0.0,
        default=1.0)
    scaleV0 = FloatProperty(name='Radius Scale Variation',
        description='Variation in the radius scale (0ScaleV)',
        default=0.2)
    pruneWidth = FloatProperty(name='Prune Width',
        description='The width of the envelope (PruneWidth)',
        min=0.0,
        default=0.4)
    pruneWidthPeak = FloatProperty(name='Prune Width Peak',
        description=('Fraction of envelope height where the maximum width '
        'occurs (PruneWidthPeak)'),
        min=0.0,
        default=0.6)
    prunePowerHigh = FloatProperty(name='Prune Power High',
        description=('Power which determines the shape of the upper portion '
        'of the envelope (PrunePowerHigh)'),
        default=0.5)
    prunePowerLow = FloatProperty(name='Prune Power Low',
        description=('Power which determines the shape of the lower portion '
        'of the envelope (PrunePowerLow)'),
        default=0.001)
    pruneRatio = FloatProperty(name='Prune Ratio',
        description='Proportion of pruned length (PruneRatio)',
        min=0.0,
        max=1.0,
        default=1.0)
    leaves = IntProperty(name='Leaves',
        description='Maximum number of leaves per branch (Leaves)',
        default=25)
    leafScale = FloatProperty(name='Leaf Scale',
        description='The scaling applied to the whole leaf (LeafScale)',
        min=0.0,
        default=0.17)
    leafScaleX = FloatProperty(name='Leaf Scale X',
        description=('The scaling applied to the x direction of the leaf '
        '(LeafScaleX)'),
        min=0.0,
        default=1.0)
    bend = FloatProperty(name='Leaf Bend',
        description='The proportion of bending applied to the leaf (Bend)',
        min=0.0,
        max=1.0,
        default=0.0)
    leafDist = EnumProperty(name='Leaf Distribution',
        description='The way leaves are distributed on branches',
        items=shapeList,
        default='4')
    bevelRes = IntProperty(name='Bevel Resolution',
        description='The bevel resolution of the curves',
        min=0,
        default=0)
    resU = IntProperty(name='Curve Resolution',
        description='The resolution along the curves',
        min=1,
        default=4)
    handleType = EnumProperty(name='Handle Type',
        description='The type of handles used in the spline',
        items=handleList,
        default='1')
    frameRate = FloatProperty(name='Frame Rate',
        description=('The number of frames per second which can be used to '
        'adjust the speed of animation'),
        min=0.001,
        default=1)
    windSpeed = FloatProperty(name='Wind Speed',
        description='The wind speed to apply to the armature (WindSpeed)',
        default=2.0)
    windGust = FloatProperty(name='Wind Gust',
        description='The greatest increase over Wind Speed (WindGust)',
        default=0.0)
    armAnim = BoolProperty(name='Armature Animation',
        description='Whether animation is added to the armature',
        default=False)

    presetName = StringProperty(name='Preset Name',
        description='The name of the preset to be saved',
        default='',
        subtype='FILENAME')
    limitImport = BoolProperty(name='Limit Import',
        description='Limited imported tree to 2 levels & no leaves for speed',
        default=True)

    startCurv = FloatProperty(name='Trunk Starting Angle',
        description=('The angle between vertical and the starting direction '
        'of the trunk'),
        min=0.0,
        max=360,
        default=0.0)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def draw(self, context):

            layout = self.layout

            # Branch specs
            #layout.label('Tree Definition')

#            row = layout.row()
#            row.prop(self, 'chooseSet')

#        if self.chooseSet == '0':
            box = layout.box()
            box.label('Geometry')
            row = box.row()
            row.prop(self, 'bevel')
            row = box.row()
            row.prop(self, 'bevelRes')
            row.prop(self, 'resU')
            row = box.row()
            row.prop(self, 'handleType')
            row = box.row()
            row.prop(self, 'shape')
            row = box.row()
            row.prop(self, 'seed')
            row = box.row()
            row.prop(self, 'ratio')
            row = box.row()
            col = row.column()
            col.prop(self, 'scale')
            col = row.column()
            col.prop(self, 'scaleV')
            row = box.row()
            col = row.column()
            col.prop(self, 'scale0')
            col = row.column()
            col.prop(self, 'scaleV0')

            # Here we create a dict of all the properties.
            # Unfortunately as_keyword doesn't work with vector properties,
            # so we need something custom. This is it
            data = []
            for a, b in (self.as_keywords(ignore=("presetName", ))).items():
                # If the property is a vector property then evaluate it and
                # convert to a string
                if (repr(b))[:3] == 'bpy':
                    data.append((a, eval('(self.' + a + ')[:]')))
                # Otherwise, it is fine so just add it
                else:
                    data.append((a, b))
            # Create the dict from the list
            data = dict(data)

            row = box.row()
            row.prop(self, 'presetName')
            # Send the data dict and the file name to the exporter
            row.operator('sapling.export').data = repr([repr(data),
                                                       self.presetName])
            row = box.row()
            row.menu('sapling.presetmenu', text='Load Preset')
            row.prop(self, 'limitImport')

#        if self.chooseSet == '1':
            box = layout.box()
            box.label('Branch Splitting')
            row = box.row()
            row.prop(self, 'levels')
            row = box.row()
            row.prop(self, 'baseSplits')
            row = box.row()
            row.prop(self, 'baseSize')
            row = box.row()
            col = row.column()
            col.prop(self, 'branches')
            col = row.column()
            col.prop(self, 'segSplits')
            row = box.row()
            col = row.column()
            col.prop(self, 'splitAngle')
            col = row.column()
            col.prop(self, 'splitAngleV')
            row = box.row()
            col = row.column()
            col.prop(self, 'downAngle')
            col = row.column()
            col.prop(self, 'downAngleV')
            row = box.row()
            col = row.column()
            col.prop(self, 'rotate')
            col = row.column()
            col.prop(self, 'rotateV')
            row = box.row()
            col = row.column()
            col.prop(self, 'ratioPower')

#        if self.chooseSet == '2':
            box = layout.box()
            box.label('Branch Growth')
            row = box.row()
            row.prop(self, 'startCurv')
            row = box.row()
            row.prop(self, 'attractUp')
            row = box.row()
            col = row.column()
            col.prop(self, 'length')
            col = row.column()
            col.prop(self, 'lengthV')
            row = box.row()
            col = row.column()
            col.prop(self, 'curve')
            col = row.column()
            col.prop(self, 'curveV')
            row = box.row()
            col = row.column()
            col.prop(self, 'curveBack')
            col = row.column()
            col.prop(self, 'taper')
            row = box.row()
            col = row.column()
            col.prop(self, 'curveRes')

#        if self.chooseSet == '3':
            box = layout.box()
            box.label('Pruning')
            row = box.row()
            row.prop(self, 'prune')
            row = box.row()
            row.prop(self, 'pruneRatio')
            row = box.row()
            row.prop(self, 'pruneWidth')
            row = box.row()
            row.prop(self, 'pruneWidthPeak')
            row = box.row()
            row.prop(self, 'prunePowerHigh')
            row.prop(self, 'prunePowerLow')

#        if self.chooseSet == '4':
            box = layout.box()
            box.label('Leaves')
            row = box.row()
            row.prop(self, 'showLeaves')
            row = box.row()
            row.prop(self, 'leaves')
            row = box.row()
            row.prop(self, 'leafDist')
            row = box.row()
            col = row.column()
            col.prop(self, 'leafScale')
            col = row.column()
            col.prop(self, 'leafScaleX')
            row = box.row()
            row.prop(self, 'bend')

#        if self.chooseSet == '5':
            box = layout.box()
            box.label('Armature and Animation')
            row = box.row()
            row.prop(self, 'useArm')
            row.prop(self, 'armAnim')
            row = box.row()
            row.prop(self, 'windSpeed')
            row.prop(self, 'windGust')
            row = box.row()
            row.prop(self, 'frameRate')

    def execute(self, context):
        # Ensure the use of the global variables
        global settings, useSet
        # If we need to set the properties from a preset then do it here
        if useSet:
            for a, b in settings.items():
                setattr(self, a, b)
            if self.limitImport:
                setattr(self, 'levels', 2)
                setattr(self, 'showLeaves', False)
            useSet = False
        addTree(self)

        return {'FINISHED'}


def menu_func(self, context):
    self.layout.operator(AddTree.bl_idname, text="Add Tree", icon='PLUGIN')


def register():
    bpy.utils.register_module(__name__)

    bpy.types.INFO_MT_curve_add.append(menu_func)


def unregister():
    bpy.utils.unregister_module(__name__)

    bpy.types.INFO_MT_curve_add.remove(menu_func)

if __name__ == "__main__":
    register()