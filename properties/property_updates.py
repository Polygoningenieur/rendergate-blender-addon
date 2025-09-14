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
from ..rendergate import jobs


def create_job_list(self, context: Context):
    """Create the enum list to show jobs in a dropdown."""

    from .properties import RendergateProperties

    props: RendergateProperties = context.scene.rendergate_properties

    enums: list[tuple[str, str, str, int]] = []

    for job in jobs.get_all():
        if not isinstance(job, Job):
            continue
        # make tuple for enum
        enums.append(
            (
                job.identifier,
                job.display_name,
                job.description,
                job.stage_icon,
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


def update_selected_job(self, context: Context) -> None:
    """Check for downloads, letting it know what property was changed."""

    from ..properties.properties import RendergatePreferences

    prefs: RendergatePreferences = RendergatePreferences.preferences(context)

    jobs.check_for_job_updates(context)

    # deselect other job
    for job in jobs.get_all():
        job.selected = False

    selected_job: Job = jobs.get_selected_job(context)
    if selected_job is not None:
        # set job as selected
        selected_job.selected = True
        # set the unified active download property to the value that is set for this job
        prefs.active_download = selected_job.active_download


def update_active_download(self, context: Context) -> None:
    """
    Update the bool flag active download for the currently selected job.
    We have a unified bool flag for all jobs, and determine which one is toggled
    by which one is selected. We do this because we don't have a PropertyGroupd
    for each job, because changing values of a PropertyGroup changes the file,
    which then the user would need to save again before creating a new job.
    """

    from ..properties.properties import RendergatePreferences

    prefs: RendergatePreferences = RendergatePreferences.preferences(context)

    selected_job: Job = jobs.get_selected_job(context)
    if selected_job is not None:
        selected_job.active_download = prefs.active_download


def update_download_folder(self, context: Context) -> None:
    """Reset all images."""

    from ..properties.properties import RendergateProperties

    props: RendergateProperties = context.scene.rendergate_properties

    props.stop_download = True

    [job.images.clear() for job in jobs.get_all()]
