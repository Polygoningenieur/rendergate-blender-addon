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
import boto3
import asyncio
from pathlib import PurePath
from requests import Response  # requests is included in Blender 4.4
from functools import partial
from typing import Any
from asyncio import AbstractEventLoop
from json.decoder import JSONDecodeError
from ..utils.async_loop import AsyncModalOperatorMixin
from bpy.types import Operator, Context
from ..utils.utils import (
    class_to_register,
    catch_exception,
    progress,
    is_string_blank,
)
from ..data import jobs
from ..utils import rest_client
from ..utils.models import Job
from ..properties.properties import RendergateProperties, RendergatePreferences
from ..utils.global_vars import rendergate_logger


@class_to_register
class RENDERGATE_OT_download_images(Operator, AsyncModalOperatorMixin):
    bl_idname = "rendergate.download_images"
    bl_label = "Download"
    bl_description = ""
    bl_options = {"REGISTER", "INTERNAL"}

    @classmethod
    def poll(cls, context: Context):
        """Enable the operator if the job is ready to download."""

        props: RendergateProperties = context.scene.rendergate_properties
        prefs: RendergatePreferences = RendergatePreferences.preferences(context)

        selected_job: Job = jobs.get_selected_render_job(context)

        if (
            not props.async_op_running
            and selected_job is not None
            and not is_string_blank(prefs.download_folder)
            and selected_job.stage in ["FINISHED"]
        ):
            return True
        else:
            return False

    @classmethod
    def description(cls, context: Context, properties):
        """Change operator description."""

        selected_job: Job = jobs.get_selected_render_job(context)
        props: RendergateProperties = context.scene.rendergate_properties
        prefs: RendergatePreferences = RendergatePreferences.preferences(context)

        description: str = "Download rendered images to the download folder"
        if props.async_op_running:
            description += (
                "\nPlease wait until other Rendergate addon operation is finished"
            )
        if selected_job is None:
            description += "\nNo render job selected"
        if is_string_blank(prefs.download_folder):
            description += "\nPlease specify a download folder before downloading"
        if selected_job is not None and selected_job.stage not in ["FINISHED"]:
            description += "\nRender job is not done rendering yet"

        return description

    def _cleanup(self, context: Context, context_pointers: dict[str, Any] = {}) -> None:
        """Cleanup of operator after terminating or a raised error."""

        props: RendergateProperties = context.scene.rendergate_properties
        props.download_images_progress = 1.0
        props.async_op_running = False
        context.area.tag_redraw()

    @catch_exception(_cleanup)
    async def async_execute(self, context: Context, context_pointers: dict[str, Any]):
        """Download the rendered results from Rendergate.ch."""

        # TODO check for downloadable images frequently, not only on button click (app timer handler)

        loop: AbstractEventLoop = asyncio.get_event_loop()

        props: RendergateProperties = context.scene.rendergate_properties
        prefs: RendergatePreferences = RendergatePreferences.preferences(context)

        props.async_op_running = True

        # set download folder already here, so if user changes it mid-download,
        # we still download to the same initial folder
        download_folder: PurePath = PurePath(bpy.path.abspath(prefs.download_folder))

        progress_start: int = 0.1
        progress_end: int = 0.999

        props.download_images_progress_text = "10% - Downloading..."
        await progress(props, "download_images_progress", progress_start, context)

        selected_job: Job = jobs.get_selected_render_job(context)

        headers: dict = {"auth": prefs.aws_token}

        # download render job
        response: Response | str = await rest_client.request(
            url=f"{props.rendergate_api_url}/project/{selected_job.identifier}/downloadPerm",
            headers=headers,
            request="GET",
        )

        # error occured
        if isinstance(response, str):
            await progress(props, "download_images_progress", 1.0, context)
            if response.startswith("Token expired"):
                prefs.aws_token = ""
                self.report({"INFO"}, response)
            else:
                self.report({"ERROR"}, response)
            self._cleanup(context)
            self.quit()
            return

        try:
            response_json: dict = response.json()
        except JSONDecodeError as e:
            await progress(props, "download_images_progress", 1.0, context)
            self.report({"ERROR"}, f"Couldn't decode boto3 s3 response: {e}")
            self._cleanup(context)
            self.quit()
            return

        credentials: dict = response_json.get("credentials", {})
        BUCKET: str = response_json.get("bucket")
        BASEKEY: str = response_json.get("baseKey")
        ACCESS_KEY: str = credentials.get("AccessKeyId")
        SECRET_KEY: str = credentials.get("SecretAccessKey")
        SESSION_TOKEN: str = credentials.get("SessionToken")
        if (
            not BUCKET
            or not BASEKEY
            or not ACCESS_KEY
            or not SECRET_KEY
            or not SESSION_TOKEN
        ):
            await progress(props, "download_images_progress", 1.0, context)
            self.report(
                {"ERROR"},
                f"Couldn't get s3 credentials to initiate download.\n{BUCKET = }\n{BASEKEY = }\n{ACCESS_KEY = }\n{SECRET_KEY = }\n{SESSION_TOKEN = }",
            )
            self._cleanup(context)
            self.quit()
            return

        props.download_images_progress_text = "15% - Downloading..."
        await progress(props, "download_images_progress", 0.15, context)

        # create s3 client
        client = boto3.client(
            "s3",
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            aws_session_token=SESSION_TOKEN,
        )

        # get list of downloadable images
        list_objects_partial = partial(
            client.list_objects_v2, Bucket=BUCKET, Prefix=BASEKEY
        )
        s3_response: dict = await loop.run_in_executor(None, list_objects_partial)
        if not isinstance(s3_response, dict):
            await progress(props, "download_images_progress", 1.0, context)
            self.report(
                {"ERROR"},
                f"Error getting images to download, response was not a dictionary.",
            )
            self._cleanup(context)
            self.quit()
            return

        props.download_images_progress_text = "20% - Downloading..."
        await progress(props, "download_images_progress", 0.2, context)

        # list of downloadable images is in Contents
        contents: list[dict[str, Any]] = s3_response.get("Contents", [])
        if len(contents) == 0:
            await progress(props, "download_images_progress", 1.0, context)
            self.report({"INFO"}, f"Nothing to download")
            self._cleanup(context)
            self.quit()
            return

        # download images
        current_progress: float = 0.2
        progress_steps: float = (progress_end - current_progress) / len(contents)
        for content in contents:
            key: str = content.get("Key")
            if key is None:
                continue

            # download to specified folder
            file_name: str = f"{PurePath(key).stem}{PurePath(key).suffix}"
            file_path: PurePath = PurePath(download_folder / file_name)

            download_file_partial = partial(
                client.download_file, BUCKET, key, file_path
            )
            await loop.run_in_executor(None, download_file_partial)

            current_progress += progress_steps
            download_percentage: int = round(current_progress * 100)
            props.download_images_progress_text = (
                f"{download_percentage}% - Downloading..."
            )
            await progress(props, "download_images_progress", current_progress, context)

            rendergate_logger.info(
                f"{download_percentage}% - Downloaded image to {file_path}"
            )

        # finished
        props.download_images_progress_text = "100% - Downloaded"
        await progress(
            props, "download_images_progress", progress_end, context, sleep=1
        )
        await progress(props, "download_images_progress", 1.0, context)

        self._cleanup(context)

        self.report({"INFO"}, "Images downloaded.")
        self.quit()
        return
