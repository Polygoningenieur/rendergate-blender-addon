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
from bpy.types import Operator
from ..utils.utils import class_to_register


@class_to_register
class RENDERGATE_OT_open_website(Operator):
    bl_idname = "rendergate.open_website"
    bl_label = "Open"
    bl_description = "Open Website"
    bl_options = {"REGISTER", "INTERNAL"}

    # properties
    url: bpy.props.StringProperty(options={"HIDDEN"})

    @classmethod
    def description(cls, context, properties):
        return "Open Website in Browser:\n" + properties.url

    def execute(self, context):

        bpy.ops.wm.url_open(url=self.url)

        return {"FINISHED"}
