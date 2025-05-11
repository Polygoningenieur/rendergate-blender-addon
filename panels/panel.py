# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.


import bpy
from bpy.types import Panel, Context, UILayout
from ..utils.utils import class_to_register
from ..properties.properties import RendergateProperties
from ..operators.login import RENDERGATE_OT_login
from ..operators.new_job import RENDERGATE_OT_invoke_new_job
from ..operators.open_prefs import RENDERGATE_OT_open_prefs
from ..operators.download import RENDERGATE_OT_download
from ..operators.open_folder import RENDERGATE_OT_open_folder


class RendergatePanel:
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render"
    bl_options = {"DEFAULT_CLOSED"}


@class_to_register
class RENDERGATE_PT_rendergate(RendergatePanel, Panel):
    """
    Creates a Panel in the render properties window.
    TODO implement log out operator
    """

    bl_idname = "RENDERGATE_PT_rendergate"
    bl_label = "Rendergate"
    bl_options = {"HEADER_LAYOUT_EXPAND"}

    def draw_header(self, context: Context):
        """Show green logged in status if user is logged in."""

        props: RendergateProperties = context.scene.rendergate_properties

        if props.aws_token:

            layout: UILayout = self.layout
            split = layout.split(factor=1 / 5)
            left = split.row()
            left.alignment = "LEFT"

            right = split.row()
            right.alignment = "RIGHT"
            right.label(
                text="Logged In",
                icon="KEYTYPE_JITTER_VEC",
            )
            right.separator(factor=0)

    def draw(self, context: Context):
        """Show UI for rendergate login, create new project, render and download."""

        props: RendergateProperties = context.scene.rendergate_properties

        layout: UILayout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False

        # user disabled blender online access
        if not bpy.app.online_access:
            layout.label(text="Please allow Blender to access the internet.")
            layout.operator(
                operator=RENDERGATE_OT_open_prefs.bl_idname,
                text="Open Blender System Settings",
            )
            return

        # not logged in yet
        if not props.aws_token:
            layout.prop(data=props, property="username")
            layout.prop(data=props, property="password")

            layout.operator(operator=RENDERGATE_OT_login.bl_idname)
            return
