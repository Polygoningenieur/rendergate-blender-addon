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
from bpy.types import Context
from functools import partial
from ..utils.models import Job
from ..data import jobs


class RendergatePropertyUpdates:

    def create_job_list(self, context: Context):
        """Create the enum list to show jobs in a dropdown."""

        from .properties import RendergateProperties

        props: RendergateProperties = context.scene.rendergate_properties

        enums: list[tuple[str, str, str, int]] = []

        for job in jobs.get_jobs():
            if not isinstance(job, Job):
                continue
            # make tuple for enum
            enums.append(
                (
                    job.identifier,
                    job.display_name,
                    job.description,
                    job.number,
                )
            )

        if len(enums) == 0:
            if props.getting_jobs:
                enums = [("0", "Loading...", "Loading...", 0)]
            else:
                enums = [
                    (
                        "0",
                        "Please Refresh ->",
                        "Please refresh the jobs with the button on the right of this list",
                        0,
                    )
                ]

        return enums

    def check_for_downloads(self, context: Context) -> None:
        """
        Start a timer that frequently checks if we can download images and downloads them.
        """

        try:
            bpy.app.timers.unregister(bpy.__rendergate_download)
        except Exception:
            pass

        selected_job: Job = jobs.get_selected_job(context)

        # use a partial to have a reference of the function, using lambda doesn't work
        download_images_partial: partial = partial(
            jobs.download_images_timer,
            context=context,
            job=selected_job,
        )
        # add timer that constantly checks for downloadable images
        bpy.app.timers.register(download_images_partial)
        # keep reference so we can unregister anytime anywhere
        bpy.__rendergate_download = download_images_partial
