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


from typing import Any
from bpy.types import Operator, Context
from requests import Response  # requests is included in Blender 4.4
from ..utils.async_loop import AsyncModalOperatorMixin
from ..utils import rest_client
from ..utils.utils import class_to_register, catch_exception
from ..properties.properties import RendergateProperties
from ..utils.global_vars import rendergate_logger
from ..utils.models import Job
from ..data import jobs


@class_to_register
class RENDERGATE_OT_get_jobs(Operator, AsyncModalOperatorMixin):
    bl_idname = "rendergate.get_jobs"
    bl_label = ""
    bl_description = ""
    bl_options = {"REGISTER", "INTERNAL"}

    @classmethod
    def description(cls, context: Context, properties: RendergateProperties):
        """Change operator description depending on required fields."""

        props: RendergateProperties = context.scene.rendergate_properties

        if props.getting_jobs:
            return "Getting jobs.."
        elif props.async_op_running:
            return "Wait until other Rendergate addon operation is finished"
        else:
            return "Get your render jobs from rendergate.ch"

    @classmethod
    def poll(cls, context: Context):
        """Enable the operator only if we are not already getting projects."""

        props: RendergateProperties = context.scene.rendergate_properties
        return not props.getting_jobs and not props.async_op_running

    def _cleanup(self, context: Context, context_pointers: dict[str, Any] = {}) -> None:
        """Cleanup on uncaught exceptions of async operator."""

        props: RendergateProperties = context.scene.rendergate_properties
        props.getting_jobs = False
        props.async_op_running = False
        context.area.tag_redraw()

    @catch_exception(_cleanup)
    async def async_execute(self, context: Context, context_pointers: dict[str, Any]):
        """Upload this blend-file and create a new render job."""

        props: RendergateProperties = context.scene.rendergate_properties
        props.async_op_running = True
        props.getting_jobs = True
        context.area.tag_redraw()

        no_jobs: bool = True if not jobs.get_jobs() else False

        headers: dict = {"auth": props.aws_token}

        # create rendergate job/project
        response: Response | None = await rest_client.request(
            url=f"{props.rendergate_api_url}/project",
            headers=headers,
            request="GET",
        )

        # error occured
        if isinstance(response, str):
            rendergate_logger.error(f"{response}")
            if response.startswith("Token expired"):
                props.aws_token = ""
                if self is not None:
                    self.report({"INFO"}, response)
            else:
                if self is not None:
                    self.report({"ERROR"}, response)
            if self is not None:
                self.quit()
                self._cleanup(context)
            props.async_op_running = False
            props.getting_jobs = False
            return

        response_json: dict = response.json()

        if not isinstance(response_json, list):
            props.async_op_running = False
            props.getting_jobs = False
            if self is not None:
                self._cleanup(context)
                self.report({"WARNING"}, "No jobs.")
                self.quit()
            return

        for index, job_data in enumerate(response_json):
            if not isinstance(job_data, dict):
                continue
            if job_data.get("id") is None:
                continue
            # add new job to list
            new_job: Job = jobs.add_job(jobs.construct_render_job(job_data, index))

        # set last job,
        # but only if there where no jobs before,
        # otherwise we want to still have the job that was selected before
        if no_jobs:
            jobs.set_selected_render_job(
                context, jobs.get_jobs()[len(jobs.get_jobs()) - 1].identifier
            )

        props.getting_jobs = False
        props.async_op_running = False
        context.area.tag_redraw()
        if self is not None:
            self._cleanup(context)
            self.report({"INFO"}, "Job list updated.")
            self.quit()
        return
