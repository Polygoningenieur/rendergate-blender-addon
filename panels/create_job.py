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
from .panel import RendergatePanel
from ..utils.utils import class_to_register
from ..properties.properties import RendergateProperties
from ..operators.new_job import RENDERGATE_OT_invoke_new_job


@class_to_register
class RENDERGATE_PT_create_job(RendergatePanel, Panel):
    """Shows all jobs of the user in a list."""

    bl_idname = "RENDERGATE_PT_create_job"
    bl_label = "       Create Render Job"
    bl_parent_id = "RENDERGATE_PT_rendergate"
    bl_order = 0
    bl_options = {"HEADER_LAYOUT_EXPAND"}

    def draw_header(self, context: Context):
        """Draw an icon in the header"""

        layout: UILayout = self.layout
        layout.label(text="", icon="EVENT_NDOF_BUTTON_PLUS")

    @classmethod
    def poll(cls, context: Context):
        """Show panel only if user is logged in and online access is allowed."""

        props: RendergateProperties = context.scene.rendergate_properties

        return bpy.app.online_access and props.aws_token

    def draw(self, context: Context):
        """Show UI for creating a new job."""

        props: RendergateProperties = context.scene.rendergate_properties

        layout: UILayout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False

        # create new project
        project_settings: UILayout = layout.column(align=True)
        project_settings.prop(data=props, property="job_name")
        # project_settings.prop(data=props, property="project_name")
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

        layout.separator()
