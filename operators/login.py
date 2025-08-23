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


import os
import bpy
import traceback
from typing import Any
from pathlib import Path, PurePath
from bpy.types import Operator, Context
from ..rendergate import jobs, login
from ..utils.global_vars import rendergate_logger
from ..utils.async_loop import AsyncModalOperatorMixin
from ..utils.utils import class_to_register, catch_exception
from ..properties.properties import RendergateProperties, RendergatePreferences
from ..operators.get_jobs import RENDERGATE_OT_get_jobs


@class_to_register
class RENDERGATE_OT_login(Operator, AsyncModalOperatorMixin):
    bl_idname = "rendergate.login"
    bl_label = "Login"
    bl_description = "Login into you Rendergate.ch account."
    bl_options = {"REGISTER", "INTERNAL"}

    def _cleanup(self, context: Context, context_pointers: dict[str, Any] = {}) -> None:
        """Cleanup of operator after terminating or a raised error."""

        props: RendergateProperties = context.scene.rendergate_properties
        prefs: RendergatePreferences = RendergatePreferences.preferences(context)

        prefs.aws_token = ""
        props.async_op_running = False
        props.logging_in = False

        try:
            if context:
                context.area.tag_redraw()
            else:
                bpy.context.area.tag_redraw()
        except:
            pass

    @catch_exception(_cleanup)
    async def async_execute(self, context: Context, context_pointers: dict[str, Any]):
        """
        Logs into AWS cognito with warrant (using boto3).
        """

        props: RendergateProperties = context.scene.rendergate_properties
        prefs: RendergatePreferences = RendergatePreferences.preferences(context)

        props.async_op_running = True
        props.logging_in = True

        try:
            await login.login(context)
        except Exception as e:
            rendergate_logger.error(traceback.format_exc())
            self._cleanup(context)
            self.report({"ERROR"}, f"Login failed: {str(e)}")
            self.quit()
            return

        # set initial download folder
        if prefs.download_folder == "":

            if bpy.data.is_saved:
                file_dir: PurePath = PurePath(os.path.dirname(bpy.data.filepath))
                prefs.download_folder = str(file_dir / PurePath("rendergate"))
            else:
                downloads_folder: Path = Path(Path.home()) / PurePath("rendergate")
                downloads_folder.mkdir(exist_ok=True)
                prefs.download_folder = str(downloads_folder)
            jobs._previous_download_folder = prefs.download_folder

        props.async_op_running = False
        props.logging_in = False

        try:
            if context:
                context.area.tag_redraw()
            else:
                bpy.context.area.tag_redraw()
        except:
            pass

        # needs to be last,
        # because the self.quit() in the other async_execute also quits this method
        try:
            # pass self as None,
            # so self.quit() in get_jobs.async_execute doesn't also quit this async method here
            await RENDERGATE_OT_get_jobs.async_execute(None, context, {})
        except Exception as e:
            rendergate_logger.error(f"{repr(e)}")

        self.report({"INFO"}, "Login successfull.")
        self.quit()
        return
