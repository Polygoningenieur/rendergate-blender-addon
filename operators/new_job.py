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
import math
from bpy.props import BoolProperty
from bpy.types import Operator, Context, Event, UILayout
from typing import Any
from requests import Response  # requests is included in Blender 4.4
from .get_jobs import RENDERGATE_OT_get_jobs
from ..data import jobs
from ..utils.async_loop import AsyncModalOperatorMixin
from ..utils import rest_client
from ..utils.global_vars import rendergate_logger
from ..utils.utils import (
    class_to_register,
    catch_exception,
    get_file_size,
    path_leaf,
    is_string_blank,
    progress,
)
from ..properties.properties import RendergateProperties


@class_to_register
class RENDERGATE_OT_new_job(Operator, AsyncModalOperatorMixin):
    bl_idname = "rendergate.new_job"
    bl_label = "New Job"
    bl_description = "Upload this blend-file and create a new render job"
    bl_options = {"REGISTER", "INTERNAL"}

    def exception_callback(self, context: Context, context_pointers: dict[str, Any]):
        """Cleanup on uncaught exceptions of async operator."""

        props: RendergateProperties = context.scene.rendergate_properties
        props.create_job_progress = 1.0
        context.area.tag_redraw()

    @catch_exception(exception_callback)
    async def async_execute(self, context: Context, context_pointers: dict[str, Any]):
        """Upload this blend-file and create a new render job."""

        props: RendergateProperties = context.scene.rendergate_properties

        props.create_job_progress_text = "Creating Job..."
        await progress(props, "create_job_progress", 0.1, context)

        headers: dict = {"auth": props.aws_token}

        # construct payload
        file_name: str = path_leaf(props.blend_file_path)
        if not file_name:
            file_name = "unknown_blend_file"
        payload: dict = {
            "name": props.job_name,
            "file": {
                "type": "blend",
                "name": file_name,
            },
        }
        if not is_string_blank(props.project_name):
            payload.update({"project": props.project_name})

        # create rendergate job/project
        response: Response | None = await rest_client.request(
            url=f"{props.rendergate_api_url}/project",
            headers=headers,
            payload=payload,
            request="POST",
        )

        # error occured
        if isinstance(response, str):
            await progress(props, "create_job_progress", 1.0, context)
            if response.startswith("Token expired"):
                props.aws_token = ""
                self.report({"INFO"}, response)
            else:
                self.report({"ERROR"}, response)
            self.quit()
            return

        response_json: dict = response.json()

        # or is it the job id?
        job_id: str = response_json.get("id")
        upload_data: dict[str] = response_json.get("uploadData")
        upload_id: str = upload_data.get("uploadId")
        upload_urls: list[str] = upload_data.get("uploadUrls", [])
        complete_url: str = upload_data.get("completeUrl")

        # multipart upload
        props.create_job_progress_text = "Uploading Blend-file..."
        await progress(props, "create_job_progress", 0.2, context)

        MB: int = 2**20
        min_part_size: int = 10 * MB  # actual min: 5MB
        part_count: int = len(upload_urls)
        part_size: int = math.ceil(props.blend_file_size / part_count)
        upload_step: float = 0.6 / part_count
        if part_size < min_part_size:
            part_count = math.ceil(props.blend_file_size / min_part_size)
            part_size = min_part_size

        rendergate_logger.info(
            f"Uploading blend-file in {part_count} parts each {part_size} bytes."
        )

        entity_tags: list[str | None] = [None for _ in range(part_count)]
        with open(props.blend_file_path, "rb") as f:
            for i, upload_url in enumerate(upload_urls[:part_count]):

                await progress(
                    props,
                    "create_job_progress",
                    props.create_job_progress + upload_step,
                    context,
                )

                f.seek(i * min_part_size)
                segment: bytes = f.read(part_size)

                part_response: Response | None = await rest_client.request(
                    url=upload_url,
                    payload=segment,
                    request="PUT",
                )

                # error occured
                if isinstance(part_response, str):
                    await progress(props, "create_job_progress", 1.0, context)
                    self.report({"ERROR"}, part_response)
                    self.quit()
                    return

                entity_tags[i] = part_response.headers["ETag"]

                rendergate_logger.info(f"Part: {i} - {len(segment)} bytes")

        # completing upload
        props.create_job_progress_text = "Finishing Upload..."
        await progress(props, "create_job_progress", 0.8, context)

        complete_body: str = (
            '<CompleteMultipartUpload xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        )
        for i, entity_tag in enumerate(entity_tags):
            complete_body += f"<Part><PartNumber>{i + 1}</PartNumber><ETag>{entity_tag}</ETag></Part>"
        complete_body += "</CompleteMultipartUpload>"

        complete_resp: Response | None = await rest_client.request(
            url=complete_url,
            payload=complete_body,
            request="POST-DATA",
        )
        # error occured
        if isinstance(complete_resp, str):
            await progress(props, "create_job_progress", 1.0, context)
            self.report({"ERROR"}, complete_resp)
            self.quit()
            return

        if complete_resp.status_code == 200:
            rendergate_logger.info("Blend-file uploaded.")
        else:
            await progress(props, "create_job_progress", 1.0, context)
            rendergate_logger.info(f"Upload: {complete_resp.status_code}")
            self.report(
                {"WARNING"}, "Could not upload Blend-File, please check online."
            )
            self.quit()
            return

        # needs to be last,
        # because the self.quit() in the other async_execute also quits this method
        props.create_job_progress_text = "Updating Job List..."
        await progress(props, "create_job_progress", 0.9, context)
        try:
            # pass self as None,
            # so self.quit() in get_jobs.async_execute doesn't also quit this async method here
            await RENDERGATE_OT_get_jobs.async_execute(None, context, {})
        except Exception as e:
            rendergate_logger.error(f"{repr(e)}")
        else:
            jobs.set_selected_render_job(context, job_id)

        props.create_job_progress_text = "Job created"
        await progress(props, "create_job_progress", 0.999, context, sleep=1)
        await progress(props, "create_job_progress", 1.0, context)
        self.report({"INFO"}, "New job created.")
        self.quit()
        return


@class_to_register
class RENDERGATE_OT_invoke_new_job(Operator):
    bl_idname: str = "rendergate.invoke_new_job"
    bl_label: str = "Create Job..."
    bl_description: str = ""
    bl_options = {"REGISTER", "INTERNAL"}

    all_satisfied: BoolProperty(default=False, options={"HIDDEN"})

    @classmethod
    def description(cls, context: Context, properties):
        """Change operator description depending on required fields."""

        props: RendergateProperties = context.scene.rendergate_properties

        if props.create_job_progress < 1.0:
            return "Creating project.."
        elif not is_string_blank(props.job_name):
            return "Create a new job under the specified project name"
        else:
            return "Please specify a job name first"

    @classmethod
    def poll(cls, context: Context):
        """Enable the operator if all required fields are filled in."""

        props: RendergateProperties = context.scene.rendergate_properties
        return not is_string_blank(props.job_name) and props.create_job_progress == 1.0

    def invoke(self, context: Context, event: Event):
        """This extra operator is necessary to trigger the async operator."""

        props: RendergateProperties = context.scene.rendergate_properties

        if bpy.data.is_saved:
            props.blend_file_path = bpy.data.filepath
            props.blend_file_size = get_file_size(props.blend_file_path)

        return context.window_manager.invoke_props_dialog(operator=self)

    def draw(self, context: Context):
        """Layout of dialog."""

        props: RendergateProperties = context.scene.rendergate_properties

        layout: UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        prerequisites: dict[str, bool] = {
            "Logged into Rendergate": bool(props.aws_token),
            "Blend-File Saved": bpy.data.is_saved,
            "Current Changes Saved": bpy.data.is_saved and not bpy.data.is_dirty,
            "External Resources Packed": bpy.data.use_autopack,
            "Use Cycles": bpy.context.scene.render.engine == "CYCLES",
        }
        self.all_satisfied: bool = all((p for p in prerequisites.values()))

        yes_icon: str = "KEYTYPE_JITTER_VEC"
        no_icon: str = "KEYTYPE_EXTREME_VEC"

        for key, value in prerequisites.items():
            layout.label(
                text=key,
                icon=yes_icon if value else no_icon,
            )

        layout.separator()

        if self.all_satisfied:
            layout.box().label(text="Create New Job?")
        else:
            layout.box().label(text="Make sure all prerequisites are met first.")

    def execute(self, context: Context):
        """This triggers the actual async operator."""

        if self.all_satisfied:
            bpy.ops.rendergate.new_job("INVOKE_DEFAULT")
        else:
            self.report({"WARNING"}, "Make sure all prerequisites are met first.")
        return {"FINISHED"}
