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
import httpx
from typing import Any, Callable
from pathlib import PurePath
from requests import Response  # requests is included in Blender 4.4
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
from ..properties.properties import RendergateProperties
from ..utils.global_vars import rendergate_logger


@class_to_register
class RENDERGATE_OT_download(Operator, AsyncModalOperatorMixin):
    bl_idname = "rendergate.download"
    bl_label = "Download"
    bl_description = ""
    bl_options = {"REGISTER", "INTERNAL"}

    @classmethod
    def poll(cls, context: Context):
        """Enable the operator if the job is ready to download."""

        props: RendergateProperties = context.scene.rendergate_properties
        selected_job: Job = jobs.get_selected_render_job(context)

        if (
            not props.async_op_running
            and selected_job is not None
            and not is_string_blank(props.download_folder)
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

        description: str = "Download render job zip-file to download folder"
        if props.async_op_running:
            description += (
                "\nPlease wait until other Rendergate addon operation is finished"
            )
        if selected_job is None:
            description += "\nNo render job selected"
        if is_string_blank(props.download_folder):
            description += "\nPlease specify a download folder before downloading"
        if selected_job is not None and selected_job.stage not in ["FINISHED"]:
            description += "\nRender job is not done rendering yet"

        return description

    def _cleanup(self, context: Context, context_pointers: dict[str, Any] = {}) -> None:
        """Cleanup of operator after terminating or a raised error."""

        props: RendergateProperties = context.scene.rendergate_properties
        props.download_job_progress = 1.0
        props.async_op_running = False
        context.area.tag_redraw()

    @catch_exception(_cleanup)
    async def async_execute(self, context: Context, context_pointers: dict[str, Any]):
        """Download the rendered results from Rendergate.ch."""

        props: RendergateProperties = context.scene.rendergate_properties
        props.async_op_running = True

        progress_start: int = 0.1
        progress_end: int = 0.999

        props.download_job_progress_text = "10% - Downloading..."
        await progress(props, "download_job_progress", progress_start, context)

        selected_job: Job = jobs.get_selected_render_job(context)

        headers: dict = {"auth": props.aws_token}

        # download render job
        response: Response | None = await rest_client.request(
            url=f"{props.rendergate_api_url}/project/{selected_job.identifier}/download",
            headers=headers,
            request="POST",
        )

        # error occured
        if isinstance(response, str):
            await progress(props, "download_job_progress", 1.0, context)
            if response.startswith("Token expired"):
                props.aws_token = ""
                self.report({"INFO"}, response)
            else:
                self.report({"ERROR"}, response)
            self._cleanup(context)
            self.quit()
            return

        response_json: dict = response.json()

        download_link: str | None = response_json.get("link", None) or None
        if download_link is None:
            props.download_job_progress_text = "100% - Not downloaded!"
            await progress(
                props, "download_job_progress", progress_end, context, sleep=1
            )
            await progress(props, "download_job_progress", 1.0, context)
            self._cleanup(context)
            self.report({"WARNING"}, f"Could not get download link. {response_json}")
            self.quit()
            return

        # download to specified folder
        file_path: PurePath = PurePath(
            PurePath(bpy.path.abspath(props.download_folder))
            / PurePath(f"{selected_job.name}.zip")
        )

        try:
            await self._download_file_async(
                download_link,
                file_path,
                lambda d, t: self._progress_callback(
                    d, t, progress_start, progress_end, props, context
                ),
            )
        except FileNotFoundError as e:
            props.download_job_progress_text = "100% - Not downloaded!"
            await progress(
                props, "download_job_progress", progress_end, context, sleep=1
            )
            await progress(props, "download_job_progress", 1.0, context)
            self._cleanup(context)
            self.report({"WARNING"}, f"The download folder does not exist. {repr(e)}")
            self.quit()
            return
        except Exception as e:
            props.download_job_progress_text = "100% - Not downloaded!"
            await progress(
                props, "download_job_progress", progress_end, context, sleep=1
            )
            await progress(props, "download_job_progress", 1.0, context)
            self._cleanup(context)
            self.report({"WARNING"}, f"Could not download zip-file. {repr(e)}")
            self.quit()
            return
        else:
            rendergate_logger.info(f"Downloaded file to: {file_path}")

        props.download_job_progress_text = "100% - Downloaded"
        await progress(props, "download_job_progress", progress_end, context, sleep=1)
        await progress(props, "download_job_progress", 1.0, context)
        self._cleanup(context)
        self.report({"INFO"}, "Zip-file downloaded.")
        self.quit()
        return

    async def _download_file_async(
        self, url: str, file_path: str, progress_callback: Callable = None
    ):
        """Download a file asynchronous and non-blocking."""

        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                total: int = int(response.headers.get("Content-Length", 0))
                downloaded: int = 0
                with open(file_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if (
                            isinstance(progress_callback, Callable)
                            and progress_callback
                            and total
                        ):
                            await progress_callback(downloaded, total)

    async def _progress_callback(
        self,
        downloaded: int,
        total: int,
        progress_start: int,
        progress_end: int,
        props: RendergateProperties,
        context: Context,
    ):
        """Report the progress of a download."""

        progress_normalized: float = round(downloaded / total, 2)
        progress_normalized *= progress_end - progress_start
        progress_normalized += progress_start
        progress_normalized = round(progress_normalized, 2)
        percent: int = int(progress_normalized * 100)
        mb: float = round(downloaded / (1024 * 1024), 2)
        total_mb: float = round(total / (1024 * 1024), 2)

        progress_text: str = f"{percent}% - {mb}/{total_mb} MB"
        props.download_job_progress_text = progress_text

        await progress(
            props,
            "download_job_progress",
            progress_normalized,
            context,
        )

        rendergate_logger.info(progress_text)
