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
from typing import Any
from requests import Response  # requests is included in Blender 4.4
from ..utils.async_loop import AsyncModalOperatorMixin
from bpy.types import Operator, Context, UILayout, Event
from ..utils.utils import (
    class_to_register,
    catch_exception,
    progress,
)
from ..data import jobs
from ..utils import rest_client
from ..utils.models import Job
from ..utils.global_vars import rendergate_logger
from ..properties.properties import RendergateProperties


@class_to_register
class RENDERGATE_OT_render(Operator, AsyncModalOperatorMixin):
    bl_idname = "rendergate.render"
    bl_label = "Render"
    bl_description = ""
    bl_options = {"REGISTER", "INTERNAL"}

    def exception_callback(self, context: Context, context_pointers: dict[str, Any]):
        """Cleanup on uncaught exceptions of async operator."""

        props: RendergateProperties = context.scene.rendergate_properties
        props.render_job_progress = 1.0
        context.area.tag_redraw()

    @catch_exception(exception_callback)
    async def async_execute(self, context: Context, context_pointers: dict[str, Any]):
        """Render the job on Rendergate.ch."""

        props: RendergateProperties = context.scene.rendergate_properties

        props.render_job_progress_text = "Sending..."
        await progress(props, "render_job_progress", 0.1, context)

        selected_job: Job = jobs.get_selected_render_job(context)

        headers: dict = {"auth": props.aws_token}
        payload: dict = {
            "fromBeginning": True,
            "chips": float(props.render_credits),
        }

        # render the job
        response: Response | None = await rest_client.request(
            url=f"{props.rendergate_api_url}/project/{selected_job.identifier}/startPay",
            headers=headers,
            payload=payload,
            request="POST",
        )

        # error occured
        if isinstance(response, str):
            await progress(props, "render_job_progress", 1.0, context)
            if response.startswith("Token expired"):
                props.aws_token = ""
                self.report({"INFO"}, response)
            else:
                self.report({"ERROR"}, response)
            self.quit()
            return

        response_json: dict = response.json()
        rendergate_logger.info(f"Render started {response_json}")

        props.render_job_progress_text = "Job rendering"
        await progress(props, "render_job_progress", 0.999, context, sleep=1)
        await progress(props, "render_job_progress", 1.0, context)
        self.report({"INFO"}, "Job rendering.")
        self.quit()
        return


@class_to_register
class RENDERGATE_OT_invoke_render(Operator):
    bl_idname: str = "rendergate.invoke_render"
    bl_label: str = "Render..."
    bl_description: str = ""
    bl_options = {"REGISTER", "INTERNAL"}

    @classmethod
    def poll(cls, context: Context):
        """Enable the operator if the job is ready to render."""

        selected_job: Job = jobs.get_selected_render_job(context)

        if selected_job is not None:
            return True if selected_job.stage in ["UPLOADED"] else False
        else:
            return False

    @classmethod
    def description(cls, context: Context, properties):
        """Change operator description depending on required fields."""

        if cls.poll(context):
            return f"Pay and render the selected job on rendergate.ch"
        else:
            return (
                f"Render job is not ready to render yet, or has been rendered already"
            )

    def invoke(self, context: Context, event: Event):
        """This extra operator is necessary to trigger the async operator."""

        props: RendergateProperties = context.scene.rendergate_properties
        selected_job: Job = jobs.get_selected_render_job(context)
        if selected_job is None:
            return

        # apply the cost estimation to the render credits,
        # use string to avoid floating point error
        props.render_credits = str(selected_job.cost_estimation)

        return context.window_manager.invoke_props_dialog(operator=self)

    def draw(self, context: Context):
        """Layout of dialog."""

        props: RendergateProperties = context.scene.rendergate_properties

        layout: UILayout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        selected_job: Job = jobs.get_selected_render_job(context)
        if selected_job is None:
            return

        layout.label(text=f"The render will use your rendergate.ch balance.")
        layout.label(text=f"Make sure you have enough.")

        credits: UILayout = layout.row(align=True)
        credits.enabled = False
        credits.prop(props, "render_credits", text="Estimated cost is: $")

    def execute(self, context: Context):
        """This triggers the actual async operator."""

        bpy.ops.rendergate.render("INVOKE_DEFAULT")
        return {"FINISHED"}
