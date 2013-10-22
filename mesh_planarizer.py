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
# $Id:$
# <pep8 compliant>

bl_info = {
    'name': 'Planarizer',
    'author': "Mark Riedesel (Klowner)",
    'version': (0, 2, 2),
    'blender': (2, 66, 3),
    'location': "View3D > Specials (W-key)",
    'warning': "",
    'description': "Corrects non-planar quads",
    'category': 'Mesh',
    'wiki_url': "http://wiki.blender.org/index.php/Extensions:2.6/Py/"
            "Scripts/Modeling/Planarizer",
    'support': 'COMMUNITY'}

import bmesh
import mathutils
import bpy


def convert_vectors_to_plane(va, vb, vc):
    vect_a = vb - va
    vect_b = vb - vc
    normal = vect_a.cross(vect_b)
    normal.normalize()
    return normal


def project_vertex_onto_plane(vert, anchor, plane):
    point = vert.co - anchor
    return vert.co - plane * plane.dot(point)


def get_face_closest_to_point(faces, point):
    min_dist = False

    for face in faces:
        face_pos = face.calc_center_median()
        dist = (face_pos - point).length
        if not min_dist or dist < min_dist[0]:
            min_dist = (dist, face)

    return min_dist[1]


def sort_verts_distance_from_point(verts, point, reverse=False):
    vert_dists = [(v, (v.co - point).magnitude) for v in verts]
    vert_dists.sort(key=lambda x: x[1], reverse=reverse)
    return [v[0] for v in vert_dists]


class MeshPlanarizer(bpy.types.Operator):
    """Adjusts selected vertices to lie on plane """
    bl_idname = "mesh.planarizer"
    bl_label = "Planarizer"
    bl_options = {'REGISTER', 'UNDO'}

    plane_source_items = (
        ('average', "Average",
            "Plane is defined by average of all selected faces"),
        ('cursor', "Face nearest to cursor",
            "Plane is defined by face nearest to 3dCursor"),
        ('connected', "Connected Face nearest to cursor",
            "Plane is defined by connected face which is nearest to 3dCursor"),
    )

    plane_anchor_items = (
        ('average', "Average",
            "Plane will be placed so as to intersect average position of "
            "selected vertices"),
        ('cursor', "Cursor",
            "Plane will be placed so as to intersect the cursor"),
        ('connected', 'Connected Vertex',
            "Result will lie on the same plane a another connected vertex"),
    )

    iteration_mode_items = (
        ('grouped', "Grouped",
            "Selection will be processed as a single group"),
        ('individual', "Individual",
            "Selection will be iterated over and processed in succession"),
    )

    plane_source = bpy.props.EnumProperty(name="Plane Source",
                                          items=plane_source_items,
                                          description="Source for plane",
                                          default='connected')

    plane_anchor = bpy.props.EnumProperty(name="Anchor To",
                                          items=plane_anchor_items,
                                          description="Anchor Point",
                                          default='average')

    iteration_mode = bpy.props.EnumProperty(name="Grouping",
                                            items=iteration_mode_items,
                                            description="Selection Grouping",
                                            default='grouped')

    def execute(self, context):
        bm = bmesh.from_edit_mesh(context.active_object.data)
        selected_verts = [v for v in bm.verts if v.select]

        self.num_verts = len(selected_verts)
        self.bmesh = bm
        self.inv_world_matrix = context.active_object.matrix_world.inverted()

        if self.num_verts == 1 or self.iteration_mode == 'individual':
            self.plane_anchor = 'connected'
            self.plane_source = 'connected'

        if not selected_verts:
            self.report({'ERROR'}, "No vertices selected")
            return {'CANCELLED'}

        if self.iteration_mode == 'grouped':
            plane_vector = self.getPlane(selected_verts, bm)
            anchor_vector = self.getAnchor(selected_verts, bm)
            for v in selected_verts:
                v.co = project_vertex_onto_plane(v,
                                                 anchor_vector,
                                                 plane_vector)

        elif self.iteration_mode == 'individual':
            cursor_pos = self.inv_world_matrix * self.getCursor()
            selected_verts = sort_verts_distance_from_point(selected_verts,
                                                            cursor_pos)
            for v in selected_verts:
                plane_vector = self.getPlane([v], bm)
                anchor_vector = self.getAnchor([v], bm)
                v.co = project_vertex_onto_plane(v, anchor_vector,
                                                 plane_vector)

        bmesh.update_edit_mesh(context.active_object.data)
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout

        layout.prop(self, 'iteration_mode')

        col = layout.column()
        col.prop(self, 'plane_anchor')
        col.prop(self, 'plane_source')

        if self.num_verts == 1 or self.iteration_mode == 'individual':
            col.enabled = False

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

    def getPlane(self, selected_verts, bm):
        plane_methods = {
            'cursor': self.getPlaneFromCursor,
            'average': self.getPlaneFromAverage,
            'connected': self.getPlaneFromCursorConnected}

        return plane_methods[self.plane_source](selected_verts, bm)

    def getPlaneFromCursor(self, selected_verts, bm, connected=False):
        cursor_pos = self.inv_world_matrix * self.getCursor()
        faces = self.getFaces(selected_verts, connected)
        face = get_face_closest_to_point(faces, cursor_pos)

        if len(selected_verts) > 1:
            return face.normal
        else:
            return self.getPlaneFromDiagonal(selected_verts[0], face)

    def getPlaneFromCursorConnected(self, selected_verts, bm):
        return self.getPlaneFromCursor(selected_verts, bm, connected=True)

    def getPlaneFromAverage(self, selected_verts, bm):
        #faces = self.getConnectedFaces(selected_verts)
        faces = self.getFaces(selected_verts, connected=True)
        scale = 1.0 / len(faces)
        normal = mathutils.Vector([0, 0, 0])
        for f in faces:
            normal += f.normal * scale
        normal.normalize()
        return normal

    def getAnchor(self, selected_verts, bm):
        anchor_methods = {
            'cursor': self.getAnchorCursor,
            'average': self.getAnchorAverage,
            'connected': self.getAnchorConnected}

        return anchor_methods[self.plane_anchor](selected_verts, bm)

    def getAnchorCursor(self, selected_verts, bm):
        return self.inv_world_matrix * self.getCursor()

    def getAnchorAverage(self, selected_verts, bm):
        avg_vertex = mathutils.Vector()
        scale = 1.0 / len(selected_verts)
        for v in selected_verts:
            avg_vertex += (v.co * scale)
        return avg_vertex

    def getAnchorConnected(self, selected_verts, bm):
        if len(selected_verts) == 1:
            cursor_pos = self.getCursor()
            #faces = self.getConnectedFaces(selected_verts)
            faces = self.getFaces(selected_verts, connected=True)
            face = get_face_closest_to_point(faces, cursor_pos)
            return self.getVectFromDiagonal(selected_verts[0], face)[1]

        # Find an unselected vertex shared by a selected vertices' edge
        ref_vert = None
        for v in selected_verts:
            for edge in v.link_edges:
                for edge_v in edge.verts:
                    if edge_v not in selected_verts:
                        ref_vert = edge_v

            if ref_vert:
                ref_vert = ref_vert.co
                break

        return ref_vert

    def getFaces(self, selected_verts, connected=False):
        faces = []
        if connected:
            for vert in selected_verts:
                for face in [f for f in vert.link_faces if len(f.verts) > 3]:
                    if face not in faces:
                        faces.append(face)
        else:
            faces = self.bmesh.faces

        return faces

    def getVectFromDiagonal(self, vert, face):
        # Find the edges of the face that don't contain the selected vertex
        face_edges = [edge for edge in face.edges if vert not in edge.verts]

        # Get all connected ngons
        # faces = [f for f in vert.link_faces if len(face.verts) > 3]

        # Find the unselected vertices of the face
        face_verts = [v for v in face.verts if not v.select]

        # If all verts in the face are selected, avoid using the active one
        if len(face_verts) < 3:
            face_verts = [v for v in face.verts if v not in [vert]]

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

        #
        #   B----C
        #   |    |
        #   A----D <- D is selected
        #
        # returns vertices (A, B, C)

        # In cases where all the face's vertices are selected
        if len(other_verts) < 2 or not middle_vert:
            return None

        return (other_verts[0].co, middle_vert.co, other_verts[1].co)

    def getPlaneFromDiagonal(self, vert, face):
        try:
            (va, vb, vc) = self.getVectFromDiagonal(vert, face)
            return convert_vectors_to_plane(va, vb, vc)
        except TypeError:
            return face.normal


classes = [MeshPlanarizer]


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
