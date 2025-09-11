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
from decimal import Decimal
from pathlib import PurePath
from bpy.types import Panel, Context, UILayout
from .panel import RendergatePanel
from ..utils.utils import class_to_register
from ..utils.models import Job
from ..utils.enums import ImageState
from ..rendergate import jobs
from ..properties.properties import (
    RendergateProperties,
    RendergatePreferences,
    JobProperties,
)
from ..operators.get_jobs import RENDERGATE_OT_get_jobs
from ..operators.render import RENDERGATE_OT_invoke_render
from ..operators.download_images import RENDERGATE_OT_download_images
from ..operators.open_folder import RENDERGATE_OT_open_folder
from ..operators.open_website import RENDERGATE_OT_open_website


@class_to_register
class RENDERGATE_PT_manage_job(RendergatePanel, Panel):
    """
    Shows all jobs of the user in a list and allows to render and download render results.
    """

    bl_idname = "RENDERGATE_PT_manage_job"
    bl_label = "Manage Render Job"
    bl_parent_id = "RENDERGATE_PT_rendergate"
    bl_order = 1

    @classmethod
    def poll(cls, context: Context):
        """Show panel only if user is logged in and online access is allowed."""

        prefs: RendergatePreferences = RendergatePreferences.preferences(context)

        return bpy.app.online_access and prefs.aws_token

    def draw(self, context: Context):
        """
        Show UI for rendergate jobs list, and buttons to render/download job.
        """

        prefs: RendergatePreferences = RendergatePreferences.preferences(context)
        props: RendergateProperties = context.scene.rendergate_properties
        all_jobs_props: set[JobProperties] = context.scene.rendergate_jobs

        layout: UILayout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False

        container: UILayout = layout.column(align=True)
        jobs_row: UILayout = container.row(align=True)
        jobs_row.scale_y = 1.2
        jobs_row.prop(data=prefs, property="jobs", text="")
        get_jobs_icon: str = "SORTTIME" if props.getting_jobs else "FILE_REFRESH"
        refresh_op: UILayout = jobs_row.row(align=True)
        refresh_op.scale_x = 1.2
        refresh_op.operator(
            operator=RENDERGATE_OT_get_jobs.bl_idname, text="", icon=get_jobs_icon
        )

        # show job details of selected job
        selected_job: Job = jobs.get_selected_job(context)
        if selected_job:
            job_details: UILayout = container.box()
            # TODO display preview image
            # job_details.label(text=f"preview: {selected_job.preview_link}")
            # job_details.label(text=f"project_name: {selected_job.project_name}")
            job_details.label(text=f"{selected_job.stage}", icon="SEQ_STRIP_DUPLICATE")
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
                job_details.label(
                    text=f"Time Estimation: {selected_job.time_estimation_human}",
                    icon="TEMP",
                )
            else:
                job_details.label(
                    text=f"Time Estimation: -",
                    icon="TEMP",
                )

            if not isinstance(selected_job.progress, float):
                progress: int = 0.0
            else:
                progress: int = int(selected_job.progress * 100)
            job_details.label(text=f"Render Progress: {progress}%", icon="SORTSIZE")

            downloaded_images: int = 0
            loading_images: int = 0
            erroneous_images: int = 0
            for image in selected_job.images:
                if PurePath(image.file_dir) != PurePath(prefs.download_folder):
                    continue
                if image.state == ImageState.DOWNLOADED:
                    downloaded_images += 1
                elif (
                    image.state == ImageState.DOWNLOADING
                    or image.state == ImageState.MISSING
                ):
                    loading_images += 1
                elif image.state == ImageState.DIRNOTFOUND:
                    erroneous_images += 1
                else:  # unknown image state
                    erroneous_images += 1

            # show downloaded, loading and erroneous images
            images_text: str = f"Downloaded Images:"
            if downloaded_images > 0:
                images_text += f" {downloaded_images}"
            if loading_images > 0:
                images_text += f" ({loading_images} loading)"
            if erroneous_images > 0:
                images_text += f" Errors with {erroneous_images} images"
            if downloaded_images > 0 or loading_images > 0 or erroneous_images > 0:
                job_details.label(text=images_text, icon="NODE_COMPOSITING")

            # checkbox to say if job should be downloaded or not
            job_props: JobProperties = jobs.get_properties(context, selected_job)
            job_details.prop(job_props, "active_download")

        buttons: UILayout = layout.split()

        # open web
        open_button: UILayout = buttons.row(align=True)
        open_web: RENDERGATE_OT_open_website = open_button.operator(
            operator=RENDERGATE_OT_open_website.bl_idname,
            icon="INTERNET",
        )
        if selected_job:
            # different for production and dev
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

        download_folder_row: UILayout = layout.row(align=True)
        download_folder_row.prop(
            data=prefs,
            property="download_folder",
            text="Download to",
        )
        download_folder_row.separator()
        download_folder_row.operator(
            operator=RENDERGATE_OT_open_folder.bl_idname,
            text="",
            icon="FOLDER_REDIRECT",
        )

        auto_download: UILayout = layout.row(align=True)
        auto_download.prop(data=prefs, property="auto_download")

        if not prefs.auto_download or props.download_images_progress < 1.0:
            # download render results
            download: UILayout = auto_download.row(align=True)
            if props.download_images_progress < 1.0:
                # fix for Blender display bug
                progress_sandbox: UILayout = download.row(align=True)
                progress_sandbox.separator(factor=0)
                progress_sandbox.progress(
                    factor=props.download_images_progress,
                    type="BAR",
                    text=props.download_images_progress_text,
                )
            else:
                download.operator(
                    operator=RENDERGATE_OT_download_images.bl_idname,
                    icon="RENDER_RESULT",
                )
