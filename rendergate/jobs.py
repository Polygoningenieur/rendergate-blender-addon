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
import asyncio
from requests import Response  # requests is included in Blender 4.5
from asyncio import AbstractEventLoop, Task
import decimal
from decimal import Decimal, InvalidOperation
import humanize
from dateutil import tz
from datetime import datetime, tzinfo, timedelta
from functools import partial
from typing import Any
from bpy.types import Context
from ..utils import utils, rest_client
from ..utils.models import Job, Image
from ..utils.enums import Stage, StageIcon
from ..utils.global_vars import rendergate_logger

_jobs: list[Job] = []
_previous_job: str = ""
_previous_download_folder: str = ""


def clear() -> None:
    """Clear jobs."""

    _jobs.clear()


def get_all() -> list[Job]:
    """Return all rendergate render jobs."""

    return _jobs


def untouch_all() -> None:
    """
    Set all jobs to be untouched, meaning they neither got added nor updated.
    Used for checking if a job needs to be deleted after jobs have been updated or added.
    Jobs that didn't get updated or added, still have 'touched' false.
    """

    for job in _jobs:
        job.touched = False


def add_job(job_data: dict, index: int) -> Job:
    """Add a rendergate render job."""

    new_job: Job = construct_render_job(job_data, index)

    _jobs.append(new_job)

    return new_job


def update_job(job_data: dict, index: int, identifier: str) -> Job | None:
    """Update a job while keeping certain attributes."""

    try:
        job: Job = next((j for j in _jobs if j.identifier == identifier))
    except (StopIteration, IndexError):
        return None

    # temporary save images list
    images: list[Image] = job.images

    updated_job: Job = construct_render_job(job_data, index)
    # update attributes of the existing job object
    for attribute, value in updated_job.__dict__.items():
        setattr(job, attribute, value)

    # new index
    job.number = index

    # keep list of images from original job
    job.images = images

    return job


def delete_job(job: Job) -> None:
    """Delete job and its properties."""

    # TODO implement

    pass


def get_selected_job(context: Context) -> Job | None:
    """Get the job that is selected in the enum property."""

    from ..properties.properties import RendergatePreferences

    prefs: RendergatePreferences = RendergatePreferences.preferences(context)

    try:
        selected_job: Job = next(
            (j for j in get_all() if j.identifier == prefs.jobs), None
        )
    except IndexError as e:
        rendergate_logger.error(repr(e))
        return None
    else:
        return selected_job


def set_selected_render_job(context: Context, identifier: str) -> None:
    """Set the selected enum job by job identifier."""

    from ..properties.properties import RendergatePreferences

    prefs: RendergatePreferences = RendergatePreferences.preferences(context)

    prefs.jobs = identifier


def get_properties(context: Context, job: Job) -> Any | None:
    """Get the bpy properties of the job, returns JobProperties."""

    from ..properties.properties import JobProperties

    all_jobs_props: set[JobProperties] = context.scene.rendergate_jobs

    try:
        return next((j for j in all_jobs_props if job.identifier == j.identifier), None)
    except IndexError:
        return None


def update_selected_job_timer(context: Context, job: Job) -> None:
    """Updates the meta data / status of the currently selected render job."""

    try:
        loop: AbstractEventLoop = asyncio.get_event_loop()
        task: Task = loop.create_task(update_selected_job(context, job))
        bpy.app.timers.register(lambda: utils.run_task_on_main_thread(task))
    except Exception as e:
        rendergate_logger.error(f"{e}")
        return None

    # periodically update the job if we expect changes, otherwise only update once
    if job.stage not in [
        Stage.INIT,
        Stage.CALCULATING,
        Stage.PAYING,
        Stage.RENDERING,
    ]:
        return 5.0
    else:
        return None


async def update_selected_job(context: Context, job: Job) -> None:
    """Requests the job details from rendergate."""

    from ..properties.properties import RendergatePreferences, RendergateProperties

    props: RendergateProperties = context.scene.rendergate_properties
    prefs: RendergatePreferences = RendergatePreferences.preferences(context)

    # get rendergate jobs
    response: Response | str = await rest_client.request(
        url=f"{props.rendergate_api_url}/project/{job.identifier}",
        headers={"auth": prefs.aws_token},
        request_type="GET",
    )

    # error occured
    if isinstance(response, str):
        rendergate_logger.error(f"{response}")
        return

    response_json: dict = response.json()

    if not isinstance(response_json, dict):
        return

    # update details
    updated_job: Job = construct_render_job(response_json, job.number, True)
    for job_attribute in updated_job.__dict__:

        setattr(job, job_attribute, getattr(updated_job, job_attribute))


def construct_render_job(
    job_data: dict, index: int, from_update_api: bool = False
) -> Job:
    """Create the Job dataclass from the response job dict."""

    job_id: str = job_data.get("id")
    job_name: str = job_data.get("name", "")
    project_name: str = job_data.get("project")
    # parse incoming stage string onto strEnum Stage
    try:
        stage: Stage = Stage[job_data.get("stage", Stage.UNKNOWN)]
    except KeyError:
        stage: Stage = Stage.UNKNOWN
    # parse incoming stage string onto strEnum StageIcon
    try:
        stage_icon: StageIcon = StageIcon[job_data.get("stage", Stage.UNKNOWN)]
    except KeyError:
        stage_icon: StageIcon = StageIcon.UNKNOWN

    # check if time and cost has been calculated yet, if not, stage is CALCULATING
    time_est_key: str = "timeEstimate" if from_update_api else "timeEst"
    if stage == Stage.UPLOADED and job_data.get(time_est_key) is None:
        stage = Stage.CALCULATING

    progress: float | dict = job_data.get("progress", "")
    num_frames: int = 0
    if from_update_api:
        progress_amount_dict: float = progress.get("progress", {})
        file_settings: dict = job_data.get("fileSettings", {})
        start_frame: int = file_settings.get("start", 1)
        stop_frame: int = file_settings.get("end", 1)
        num_frames = stop_frame - start_frame + 1
        if num_frames <= 0:
            progress_amount: float = 0.0
        else:
            progress_amount: float = progress_amount_dict.get("current", 0) / num_frames
    else:
        progress_amount: float = job_data.get("progress", 0.0)

    # API responses are not consitent for /project/{id} and /project
    # so we need to make a distinction
    estimation_dict: dict = progress if from_update_api else job_data

    # create decimals for the prices to not have floating point precision errors
    # and make sure we have enough precision to quantize
    decimal.getcontext().prec = 28
    if from_update_api:
        cost_est_dict: dict = estimation_dict.get("cost", {})
        cost_estimation_number: float = cost_est_dict.get("total", 0.00)
    else:
        cost_estimation_number: float = estimation_dict.get("costEst", 0.00)
    try:
        cost_estimation: Decimal = Decimal(f"{cost_estimation_number}")
        cost_estimation = cost_estimation.quantize(Decimal(".01"))
    except InvalidOperation:
        cost_estimation: Decimal = Decimal("0.00")

    if from_update_api:
        cost_est_dict: dict = estimation_dict.get("cost", {})
        cost_number: float = cost_est_dict.get("current", 0.0)
    else:
        cost_number: float = estimation_dict.get("cost", 0.0)
    try:
        cost: Decimal = Decimal(f"{cost_number}")
        cost = cost.quantize(Decimal(".01"))
    except InvalidOperation as e:
        cost: Decimal = Decimal("0.00")

    preview: str = job_data.get("preview", "")

    # created time
    created: str = job_data.get("creationDate")
    from_zone: tzinfo = tz.tzutc()
    to_zone: tzinfo = tz.tzlocal()
    date_time_utc: datetime = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ")
    # tell the datetime object that it's in UTC time zone since
    # datetime objects are naive by default
    date_time_utc = date_time_utc.replace(tzinfo=from_zone)
    # convert to local time zone
    date_time_local = date_time_utc.astimezone(to_zone)
    created_ago: str = humanize.naturaltime(date_time_local)

    # human readable time estimation
    if from_update_api:
        time_est_dict: dict = estimation_dict.get("time", {})
        time_estimation: float = time_est_dict.get("total", 0.0)
    else:
        time_estimation: float = estimation_dict.get("timeEst", 0.0)
    time_estimation_delta: timedelta = timedelta(milliseconds=time_estimation)
    time_estimation_human: str = humanize.precisedelta(
        time_estimation_delta, minimum_unit="minutes"
    )

    # human readable time
    if from_update_api:
        time_est_dict: dict = estimation_dict.get("time", {})
        time: float = time_est_dict.get("current", 0.0)
    else:
        time: float = estimation_dict.get("time", 0.0)
    time_delta: timedelta = timedelta(milliseconds=time)
    time_human: str = humanize.precisedelta(time_delta, minimum_unit="minutes")

    description: str = (
        f"Job {index}\nCreated: {created_ago}\nProject: {project_name}\nStage: {stage}\nProgress: {progress_amount}\nCost Estimation: ${cost_estimation}\nCost: {cost}\nTime Estimation: {time_estimation_human}\nTime: {time_human}"
    )

    # TODO outsource
    # create corresponding bpy properties job
    from ..properties.properties import JobProperties

    all_jobs_props: set[JobProperties] = bpy.context.scene.rendergate_jobs
    new_job_props: JobProperties = all_jobs_props.add()
    new_job_props.identifier = job_id
    new_job_props.active_download = False

    return Job(
        identifier=job_id,
        touched=True,
        number=index,
        name=job_name,
        display_name=f'"{job_name}" {created_ago}',
        description=description,
        created=created_ago,
        project_name=project_name,
        stage=stage,
        stage_icon=stage_icon,
        progress=progress_amount,
        cost_estimation=cost_estimation,
        cost=cost,
        time_estimation=time_estimation,
        time_estimation_human=time_estimation_human,
        time=time,
        time_human=time_human,
        preview_link=preview,
        images=[],
        frames=num_frames,
    )


def check_for_job_updates(context: Context) -> None:
    """
    Check if we should request rendergate frequently with a timer
    for updates on its status.
    """

    from ..properties.properties import RendergatePreferences

    try:
        try:
            bpy.app.timers.unregister(bpy.__rendergate_job_status_update)
        except Exception:
            pass

        # only if logged in
        prefs: RendergatePreferences = RendergatePreferences.preferences(context)
        if not prefs.aws_token:
            return

        selected_job: Job = get_selected_job(context)
        if not selected_job:
            return

        # use a partial to have a reference of the function, using lambda doesn't work
        update_job_status_partial: partial = partial(
            update_selected_job_timer,
            context=context,
            job=selected_job,
        )
        # add timer that constantly checks for downloadable images
        bpy.app.timers.register(update_job_status_partial)
        # keep reference so we can unregister anytime anywhere
        bpy.__rendergate_job_status_update = update_job_status_partial
    except Exception as er:
        rendergate_logger.error(f"{er}")
