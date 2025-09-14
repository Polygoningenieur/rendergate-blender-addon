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
from ..utils.global_vars import rendergate_images
from ..properties.properties import RendergatePreferences, RendergateProperties
from ..operators.login import RENDERGATE_OT_login
from ..operators.open_prefs import RENDERGATE_OT_open_prefs
from ..operators.new_job import RENDERGATE_OT_invoke_new_job


class RendergatePanel:
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "output"
    bl_options = {"DEFAULT_CLOSED"}


@class_to_register
class RENDERGATE_PT_rendergate(RendergatePanel, Panel):
    """
    Creates a Panel in the output properties.
    TODO implement log out operator
    """

    bl_idname = "RENDERGATE_PT_rendergate"
    bl_label = "       Rendergate"
    bl_options = {"HEADER_LAYOUT_EXPAND"}

    def draw_header(self, context: Context):
        """Show green logged in status if user is logged in."""

        prefs: RendergatePreferences = RendergatePreferences.preferences(context)

        layout: UILayout = self.layout
        split = layout.split(factor=1 / 5)
        left = split.row()
        left.alignment = "LEFT"
        try:
            left.label(icon_value=rendergate_images["main"]["rendergate_logo"].icon_id)
        except (KeyError, AttributeError):
            left.label(icon="RENDERLAYERS")

        if prefs.aws_token:
            right = split.row()
            right.alignment = "RIGHT"
            right.label(
                text="Logged In",
                icon="NODE_SOCKET_SHADER",
            )
            right.separator(factor=0)

    def draw(self, context: Context):
        """Show UI for rendergate login, create new project, render and download."""

        props: RendergateProperties = context.scene.rendergate_properties
        prefs: RendergatePreferences = RendergatePreferences.preferences(context)

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
        if not prefs.aws_token:
            layout.prop(data=prefs, property="username")
            layout.prop(data=prefs, property="password")

            login_operator: UILayout = layout.row(align=True)
            if props.logging_in:
                login_operator.enabled = False
                login_operator.alignment = "CENTER"
                login_operator.label(text="Logging in...")
            else:
                login_operator.operator(operator=RENDERGATE_OT_login.bl_idname)
            return

        # create new project
        project_settings: UILayout = layout.column(align=True)
        project_settings.prop(data=prefs, property="job_name")
        # project_settings.prop(data=prefs, property="project_name")
        new_job: UILayout = layout.row(align=True)
        if props.create_job_progress < 1.0:
            # fix for Blender display bug
            progress_sandbox: UILayout = new_job.row(align=True)
            progress_sandbox.separator(factor=0)
            progress_sandbox.progress(
                factor=props.create_job_progress,
                type="BAR",
                text=props.create_job_progress_text,
            )
        else:
            new_job.operator(
                operator=RENDERGATE_OT_invoke_new_job.bl_idname, icon="ADD"
            )
