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
import humanize
from decimal import Decimal
from datetime import timedelta
from bpy.types import Panel, Context, UILayout
from .panel import RendergatePanel
from ..utils.utils import class_to_register
from ..utils.models import Job
from ..data import jobs
from ..properties.properties import RendergateProperties
from ..operators.get_jobs import RENDERGATE_OT_get_jobs
from ..operators.render import RENDERGATE_OT_invoke_render
from ..operators.download import RENDERGATE_OT_download
from ..operators.open_folder import RENDERGATE_OT_open_folder
from ..operators.open_website import RENDERGATE_OT_open_website


@class_to_register
class RENDERGATE_PT_manage_job(RendergatePanel, Panel):
    """
    Shows all jobs of the user in a list and allows to render and download render results.
    """

    bl_idname = "RENDERGATE_PT_manage_job"
    bl_label = "       Manage Render Job"
    bl_parent_id = "RENDERGATE_PT_rendergate"
    bl_order = 1
    bl_options = {"HEADER_LAYOUT_EXPAND"}

    def draw_header(self, context: Context):
        """Draw an icon in the header"""

        layout: UILayout = self.layout
        layout.label(text="", icon="RENDER_ANIMATION")

    @classmethod
    def poll(cls, context: Context):
        """Show panel only if user is logged in and online access is allowed."""

        props: RendergateProperties = context.scene.rendergate_properties

        return bpy.app.online_access and props.aws_token

    def draw(self, context: Context):
        """
        Show UI for rendergate jobs list, and buttons to render/download job.
        """

        props: RendergateProperties = context.scene.rendergate_properties

        layout: UILayout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False

        container: UILayout = layout.column(align=True)
        jobs_row: UILayout = container.row(align=True)
        jobs_row.scale_y = 1.2
        jobs_row.prop(data=props, property="jobs", text="")
        get_jobs_icon: str = "SORTTIME" if props.getting_jobs else "FILE_REFRESH"
        refresh_op: UILayout = jobs_row.row(align=True)
        refresh_op.scale_x = 1.2
        refresh_op.operator(
            operator=RENDERGATE_OT_get_jobs.bl_idname, text="", icon=get_jobs_icon
        )

        # show job details of selected job
        selected_job: Job = jobs.get_selected_render_job(context)
        if selected_job:
            job_details: UILayout = container.box()
            # TODO display preview image
            # job_details.label(text=f"preview: {selected_job.preview_link}")
            # job_details.label(text=f"project_name: {selected_job.project_name}")
            if selected_job.cost_estimation > Decimal("0.00"):
                job_details.label(
                    text=f"Cost Estimation: ${selected_job.cost_estimation}",
                    icon="TAG",
                )
            else:
                job_details.label(
                    text=f"Cost Estimation: -",
                    icon="TAG",
                )
            if selected_job.time_estimation > Decimal("0.00"):
                delta: timedelta = timedelta(milliseconds=selected_job.time_estimation)
                job_details.label(
                    text=f"Time Estimation: {humanize.precisedelta(delta, minimum_unit='minutes')}",
                    icon="TEMP",
                )
            else:
                job_details.label(
                    text=f"Time Estimation: -",
                    icon="TEMP",
                )
            job_details.label(
                text=f"Stage: {selected_job.stage}", icon="SEQ_STRIP_DUPLICATE"
            )
            job_details.label(
                text=f"Progress: {selected_job.progress}", icon="SORTSIZE"
            )

        buttons: UILayout = layout.split()

        # open web
        open_button: UILayout = buttons.row(align=True)
        open_web: RENDERGATE_OT_open_website = open_button.operator(
            operator=RENDERGATE_OT_open_website.bl_idname,
            icon="INTERNET",
        )
        if selected_job:
            open_web.url = f"https://rendergate.ch/en/details/{selected_job.identifier}"
        else:
            open_button.enabled = False

        # render
        render: UILayout = buttons.row(align=True)
        if props.render_job_progress < 1.0:
            # fix for Blender display bug
            progress_sandbox: UILayout = render.row(align=True)
            progress_sandbox.separator(factor=0)
            progress_sandbox.progress(
                factor=props.render_job_progress,
                type="BAR",
                text=props.render_job_progress_text,
            )
        else:
            render.operator(
                operator=RENDERGATE_OT_invoke_render.bl_idname,
                icon="RENDER_STILL",
            )

        # download render results
        download: UILayout = buttons.row(align=True)
        if props.download_job_progress < 1.0:
            # fix for Blender display bug
            progress_sandbox: UILayout = download.row(align=True)
            progress_sandbox.separator(factor=0)
            progress_sandbox.progress(
                factor=props.download_job_progress,
                type="BAR",
                text=props.download_job_progress_text,
            )
        else:
            download.operator(
                operator=RENDERGATE_OT_download.bl_idname,
                icon="RENDER_RESULT",
            )

        download_folder_row: UILayout = layout.row(align=True)
        download_folder_row.prop(
            data=props,
            property="download_folder",
            text="Download to",
        )
        download_folder_row.separator()
        download_folder_row.operator(
            operator=RENDERGATE_OT_open_folder.bl_idname,
            text="",
            icon="FOLDER_REDIRECT",
        )
