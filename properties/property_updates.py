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


from bpy.types import Context
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
                        "Please refresh the jobs with the button on the right of this list",0
                    )
                ]

        return enums
