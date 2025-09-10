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
from ..properties.properties import RendergateProperties, RendergatePreferences
from ..operators.get_jobs import RENDERGATE_OT_get_jobs
from ..operators.render import RENDERGATE_OT_invoke_render
from ..operators.download_images import RENDERGATE_OT_download_images
from ..operators.open_folder import RENDERGATE_OT_open_folder
from ..operators.open_website import RENDERGATE_OT_open_website


@class_to_register
class RENDERGATE_PT_download(RendergatePanel, Panel):
    """Shows all active downloads."""

    bl_idname = "RENDERGATE_PT_download"
    bl_label = "Downloads"
    bl_parent_id = "RENDERGATE_PT_rendergate"
    bl_order = 2

    @classmethod
    def poll(cls, context: Context):
        """Show panel only if user is logged in and online access is allowed."""

        prefs: RendergatePreferences = RendergatePreferences.preferences(context)

        return bpy.app.online_access and prefs.aws_token

    def draw(self, context: Context):
        """
        Show UI for all active downloads
        (job name, progress, pause/resume/cancel download).
        """

        props: RendergateProperties = context.scene.rendergate_properties
        prefs: RendergatePreferences = RendergatePreferences.preferences(context)

        layout: UILayout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False

        container: UILayout = layout.column(align=True)
