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
import random
import string
import asyncio
import traceback
from typing import Any
from warrant import Cognito
from functools import partial
from pathlib import Path, PurePath
from asyncio import AbstractEventLoop
from bpy.types import Operator, Context
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

        loop: AbstractEventLoop = asyncio.get_event_loop()

        props: RendergateProperties = context.scene.rendergate_properties
        prefs: RendergatePreferences = RendergatePreferences.preferences(context)

        props.async_op_running = True
        props.logging_in = True

        # aws authentication
        # TODO change to production
        REGION: str = "us-east-2"
        USER_POOL_ID: str = "us-east-2_0iJztlRUB"
        USER_POOL_WEB_CLIENT_ID: str = "6m7eldka3q9f20nmev7smovnf6"

        try:
            user: Cognito = Cognito(
                user_pool_id=USER_POOL_ID,
                client_id=USER_POOL_WEB_CLIENT_ID,
                user_pool_region=REGION,
                username=prefs.username,
            )
            authenticate_partial = partial(user.authenticate, password=prefs.password)
            await loop.run_in_executor(None, authenticate_partial)

        except Exception as e:
            rendergate_logger.error(traceback.format_exc())
            self._cleanup()
            self.report({"ERROR"}, f"Login failed: {str(e)}")
            self.quit()
            return

        # login sucessfull
        prefs.aws_token = user.id_token

        # from Blender ID Authentication Addon:
        # Prevent saving the password in user preferences
        # Overwrite the password with a random string,
        # as just setting to '' might only replace the first byte with 0
        password_length: int = len(prefs.password)
        random_string: str = "".join(
            random.choice(string.ascii_uppercase + string.digits)
            for _ in range(password_length + 16)
        )
        prefs.password = random_string
        prefs.password = ""

        # set initial download folder
        if prefs.download_folder == "":

            if bpy.data.is_saved:
                file_dir: PurePath = PurePath(os.path.dirname(bpy.data.filepath))
                prefs.download_folder = str(file_dir / PurePath("rendergate"))
            else:
                downloads_folder: Path = Path(Path.home()) / PurePath("rendergate")
                downloads_folder.mkdir(exist_ok=True)
                prefs.download_folder = str(downloads_folder)

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

            bpy.ops.rendergate.get_jobs("EXEC_DEFAULT")

            return None

        try:
            bpy.app.timers.register(get_jobs_timer_wrapper)
        except Exception as e:
            rendergate_logger.info(f"Error getting jobs: {e}")

        self.report({"INFO"}, "Login successfull.")
        self.quit()
        return
