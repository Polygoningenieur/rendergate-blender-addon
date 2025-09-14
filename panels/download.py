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
from ..utils.models import Job
from ..rendergate import jobs
from ..utils.models import Image
from ..utils.enums import ImageState
from ..operators.open_folder import RENDERGATE_OT_open_folder
from ..operators.select_job import RENDERGATE_OT_select_job
from ..properties.properties import RendergatePreferences


@class_to_register
class RENDERGATE_PT_download(RendergatePanel, Panel):
    """Shows all active downloads."""

    bl_idname = "RENDERGATE_PT_download"
    bl_label = "Downloads"
    bl_parent_id = "RENDERGATE_PT_rendergate"
    bl_order = 1

    @classmethod
    def poll(cls, context: Context):
        """Show panel only if user is logged in and online access is allowed."""

        prefs: RendergatePreferences = RendergatePreferences.preferences(context)

        return bpy.app.online_access and prefs.aws_token

    def draw(self, context: Context):
        """
        Show UI for all active downloads
        (job name, progress, pause/resume/cancel download, open folder).
        """

        prefs: RendergatePreferences = RendergatePreferences.preferences(context)

        layout: UILayout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False

        download_container: UILayout = layout.column(align=True)
        download_container.label(text="Parent Download Folder,")
        download_container.label(text="Jobs Get Their Own Subfolder.")
        download_folder_row: UILayout = download_container.row(align=True)
        download_folder_row.prop(
            data=prefs,
            property="download_folder",
            text="",
        )
        download_folder_row.separator()
        download_folder_row.operator(
            operator=RENDERGATE_OT_open_folder.bl_idname,
            text="",
            icon="FOLDER_REDIRECT",
        )

        layout.separator()

        split: UILayout = layout.split(factor=1 / 3)
        left: UILayout = split.column(align=True)
        right: UILayout = split.column(align=True)

        for job in jobs.get_all():
            if not job.active_download:
                continue

            downloaded_images: list[Image] = [
                i for i in job.images if i.state == ImageState.DOWNLOADED
            ]
            error_images: list[Image] = [
                i for i in job.images if i.state == ImageState.DIRNOTFOUND
            ]

            # get download progress
            progress_normalized: float = 0.0
            progress: str = f"0/0"
            if job.frames > 0:
                progress_normalized: float = len(downloaded_images) / job.frames
                progress: str = f"{len(downloaded_images)}/{job.frames}"

            # display count of erroneous images
            if len(error_images) > 0:
                progress += f" ({len(error_images)} Errors)"

            left.label(text=str(job.name))

            right_row: UILayout = right.row(align=True)
            right_row.progress(factor=progress_normalized, type="BAR", text=progress)

            select_operator_layout: UILayout = right_row.row(align=True)
            select_operator_layout.enabled = not job.selected
            select_operator: RENDERGATE_OT_select_job = select_operator_layout.operator(
                operator=RENDERGATE_OT_select_job.bl_idname,
                text="",
                icon="RESTRICT_SELECT_OFF",
            )
            select_operator.job_name = job.name
            select_operator.job_identifier = job.identifier
