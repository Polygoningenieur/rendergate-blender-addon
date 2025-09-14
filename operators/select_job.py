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


# pyright: reportInvalidTypeForm=false

import bpy
from ..rendergate import jobs
from bpy.types import Operator, Context
from ..utils.utils import class_to_register
from ..properties.properties import RendergatePreferences


@class_to_register
class RENDERGATE_OT_select_job(Operator):
    bl_idname: str = "rendergate.select_job"
    bl_label: str = "Select Job"
    bl_description: str = "Selects this job"
    bl_options = {"REGISTER", "INTERNAL"}

    # properties
    job_name: bpy.props.StringProperty(options={"HIDDEN"})
    job_identifier: bpy.props.StringProperty(options={"HIDDEN"})

    @classmethod
    def description(cls, context: Context, properties):
        return f"Select Job {properties.job_name}"

    def execute(self, context: Context):
        """Selects the job."""

        jobs.set_selected_render_job(context, self.job_identifier)

        return {"FINISHED"}
