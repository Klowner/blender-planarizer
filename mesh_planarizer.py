# ##### BEGIN GPL LICENSE BLOCK #####
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
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

bl_info = {
    'name': 'Planarizer',
    'author': "Mark Riedesel",
    'version': (0, 1, 1),
    'blender': (2, 66, 3),
    'location': "Editmode > D",
    'warning': "",
    'description': "Corrects non-planar quads",
    'category': 'Mesh',
    'support': 'COMMUNITY'}

import bmesh
import mathutils
import bpy
import itertools
from bpy_extras import view3d_utils


def project_to_plane_normal(point, normal):
    normal.normalize()
    adjust = normal.dot(point)
    return normal.xyz * adjust


def project_to_plane(point, va, vb):
    va.normalize()
    vb.normalize()
    normal = va.cross(vb)
    return project_to_plane_normal(point, normal)


def get_face_closest_to_3dcursor(faces, context, cursor):
    print(cursor)


def get_face_closest_to_mouse(faces, context, mouse_pos):
    ob = context.active_object
    region = context.region
    region_3d = context.space_data.region_3d

    optimal_faces = []
    min_dist = False

    for face in faces:
        face_pos = face.calc_center_median()
        world_face_pos = ob.matrix_world * face_pos
        screen_face_pos = view3d_utils.location_3d_to_region_2d(region,
                                                                region_3d,
                                                                world_face_pos)
        dist = (mouse_pos - screen_face_pos).length
        if not min_dist or dist < min_dist[0]:
            min_dist = (dist, face)

    return min_dist[1]


def fix_nonplanar_face(bm, vert_sel, cursor, context, event):
    ob = context.active_object
    region = context.region
    region_3d = context.space_data.region_3d

    # Find linked edges that are connected to faces
    edges = [edge for edge in vert_sel.link_edges if len(edge.link_faces) > 0]

    # Get all connected quads
    faces = [face for face in vert_sel.link_faces if len(face.verts) == 4]

    # Find edges that do not contain selected vertex
    mouse_pos = mathutils.Vector([event.mouse_region_x, event.mouse_region_y])
    face = get_face_closest_to_mouse(faces, context, mouse_pos)
    get_face_closest_to_3dcursor(faces, context, cursor)

    # Find the unselected vertices of the face
    face_verts = [v for v in face.verts if not v.select]

    # Find the edges of the face that don't contain the selected vertex
    face_edges = [edge for edge in face.edges if vert_sel not in edge.verts]

    # Find the middle vertex shared between the two edges
    middle_vert = None
    for v in face_verts:
        middle_vert = (v if v in face_edges[0].verts and
                       v in face_edges[1].verts else None)
        if middle_vert:
            break

    other_verts = []
    for edge in face_edges:
        v = [v for v in edge.verts if not v == middle_vert]
        other_verts.append(v[0])

    selected_vect = vert_sel.co - middle_vert.co
    plane_va = middle_vert.co - other_verts[0].co
    plane_vb = middle_vert.co - other_verts[1].co

    new_vertex = project_to_plane(selected_vect, plane_va, plane_vb)

    vert_sel.co.xyz = (vert_sel.co - new_vertex)


def fix_multi_nonplanar_verts(bm, vert_sel, cursor, context, event):
    ob = context.active_object
    region = context.region
    region_3d = context.space_data.region_3d

    # Find face under mouse cursor
    mouse_pos = mathutils.Vector([event.mouse_region_x, event.mouse_region_y])
    face = get_face_closest_to_mouse(bm.faces, context, mouse_pos)

    # Find an unselected vertex shared by a selected vertices' edge
    ref_vert = None
    for v in vert_sel:
        for edge in v.link_edges:
            for edge_v in edge.verts:
                if edge_v not in vert_sel:
                    ref_vert = edge_v

        if ref_vert:
            ref_vert = ref_vert.co
            break

    # All connected verts must be selected, so we fall-back
    # to using the median point of the selected face
    if not ref_vert:
        ref_vert = face.calc_center_median()

    normal = face.normal

    # Project selected points to nearest point on plane defined
    # by the hovered face's surface normal
    for v in vert_sel:
        local_v = v.co - ref_vert
        adjustment = project_to_plane_normal(local_v, normal)
        v.co.xyz = (v.co.xyz - adjustment)


class MeshPlanarizer_old(bpy.types.Operator):
    """Adjusts selected vertices to lie on plane defined by """ \
    """face that is nearest to the 3D Cursor"""
    bl_idname = "mesh.planarizer"
    bl_label = "Fix non-planar face"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return (ob and ob.type == 'MESH' and context.mode == 'EDIT_MESH')

    def invoke(self, context, event):
        bm = bmesh.from_edit_mesh(context.active_object.data)
        selected_verts = [v for v in bm.verts if v.select]

        if not selected_verts:
            return {'CANCELLED': "Error"}

        cursor = self.getCursor()

        if len(selected_verts) > 1:
            fix_multi_nonplanar_verts(bm, selected_verts, cursor,
                                      context, event)
        else:
            fix_nonplanar_face(bm, selected_verts[0], cursor, context, event)

        bmesh.update_edit_mesh(context.active_object.data)

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}

    def execute(self, context):
        print('execute', self, context)
        return {'FINISHED'}

    @classmethod
    def getCursor(cls):
        spc = cls.findSpace()
        return spc.cursor_location

    @classmethod
    def setCursor(cls, coordinates):
        spc = cls.findSpace()
        spc.cursor_location = coordinates

    @classmethod
    def findSpace(cls):
        area = None
        for area in bpy.data.window_managers[0].windows[0].screen.areas:
            if area.type == 'VIEW_3D':
                break
        if area.type != 'VIEW_3D':
            return None
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                break
        if space.type != 'VIEW_3D':
            return None
        return space


class MeshPlanarizer(bpy.types.Operator):
    """Adjusts selected vertices to lie on plane """
    bl_idname = "mesh.planarizer"
    bl_label = "Planarizer"
    bl_options = {'REGISTER', 'UNDO'}

    plane_source_items = (
        ('cursor', "Face nearest to cursor",
            "Plane is defined by face nearest to 3dCursor"),
        ('average', "Average of selected",
            "Plane is defined by average of all selected faces"),
    )

    plane_anchor_items = (
        ('cursor', "Cursor",
            "Plane will be placed to intersect 3dCursor"),
        ('median', "Median",
            "Plane will be placed to itersect average position of selected "
            "vertices")
    )

    plane_source = bpy.props.EnumProperty(name="Plane Source",
                                          items=plane_source_items,
                                          description="Source for plane",
                                          default='cursor')

    plane_anchor = bpy.props.EnumProperty(name="Anchor to",
                                          items=plane_anchor_items,
                                          description="Plane anchor point",
                                          default='cursor')

    def execute(self, context):
        bm = bmesh.from_edit_mesh(context.active_object.data)
        selected_verts = [v for v in bm.verts if v.select]

        if not selected_verts:
            self.report({'ERROR'}, "No vertices selected")
            return {'CANCELLED'}

        if len(selected_verts) > 1:
            pass
        else:
            pass

        bmesh.update_edit_mesh(context.active_object.data)

        return {'FINISHED'}

    @classmethod
    def getCursor(cls):
        spc = cls.findSpace()
        return spc.cursor_location

    @classmethod
    def setCursor(cls, coordinates):
        spc = cls.findSpace()
        spc.cursor_location = coordinates

    @classmethod
    def findSpace(cls):
        area = None
        for area in bpy.data.window_managers[0].windows[0].screen.areas:
            if area.type == 'VIEW_3D':
                break
        if area.type != 'VIEW_3D':
            return None
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                break
        if space.type != 'VIEW_3D':
            return None
        return space

"""
class MeshPlanarizer(bpy.types.Operator, MeshPlanarizerBase):
    bl_idname = "mesh.planarizer"
    bl_options = {'REGISTER', 'UNDO'}
    bl_label = 'Planarizer'


class MeshPlanarizer3dCursor(bpy.types.Operator, MeshPlanarizerBase):
    bl_idname = "mesh.planarizer_3dcursor"
    bl_options = {'REGISTER', 'UNDO'}
    bl_label = 'Planarizer with 3dCursor'

"""
"""
def register():
    # add operator
    print(__name__)
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.VIEW3D_MT_edit_mesh_specials.append(menu_func)
    bpy.types.VIEW3D_MT_edit_mesh_vertices.append(menu_func)

    #bpy.types.WindowManager.planarizer = bpy.props.PointerProperty(\
    #    type = PlanarizerProps)

    # add keymap entry
    #km = bpy.context.window_manager.keyconfigs.addon.keymaps.new(
    #    name='Mesh',
    #    space_type='EMPTY')
    #kmi = km.keymap_items.new("mesh.planarizer", "D", "PRESS")
    #addon_keymaps.append(km)


def unregister():
    # remove operator
    for c in classes:
        bpy.utils.unregister_class(c)

    bpy.types.VIEW3D_MT_edit_mesh_specials.remove(menu_func)
    bpy.types.VIEW3D_MT_edit_mesh_vertices.append(menu_func)

    #try:
    #    del bpy.types.WindowManager.planarizer
    #except:
    #    pass
    # remove keymap
    #for km in addon_keymaps:
    #    bpy.context.window_manager.keyconfigs.addon.keymaps.remove(km)
    #addon_keymaps.clear()
"""

classes = [
    MeshPlanarizer]


def menu_func(self, context):
    self.layout.operator(MeshPlanarizer.bl_idname)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.VIEW3D_MT_edit_mesh_specials.append(menu_func)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.types.VIEW3D_MT_edit_mesh_specials.remove(menu_func)

if __name__ == '__main__':
    register()
