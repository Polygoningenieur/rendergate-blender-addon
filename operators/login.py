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

        # NOTE bpy operators (regular or async) need to be called
        # to run in Blenders main thread, if called from async mixin
        # use bpy.app.timers to schedule a function to run in the main thread
        # also the app timer expects None if the timer should stop,
        # so we wrap get_jobs in another function
        def get_jobs_timer_wrapper():
            """Wraps get_jobs to return None, which an bpy app timer expects."""

            # sometimes error occurs when calling the operator
            # (might only happen in dev env)
            try:
                bpy.ops.rendergate.get_jobs("EXEC_DEFAULT")
            except RuntimeError as e:
                rendergate_logger.error(f"Error trying to get jobs: {e}")
                props.getting_jobs = False
                props.async_op_running = False

            return None

        try:
            bpy.app.timers.register(get_jobs_timer_wrapper)
        except Exception as e:
            rendergate_logger.info(f"Error getting jobs: {e}")

        self.report({"INFO"}, "Login successfull.")
        self.quit()
        return
