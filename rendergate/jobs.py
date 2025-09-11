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
from pathlib import PurePath
from bpy.types import Context
from . import download
from ..utils import utils, rest_client
from ..utils.models import Job, Image
from ..utils.enums import Stage, ImageState, DownloadTrigger
from ..utils.global_vars import rendergate_logger

_jobs: list[Job] = []
_previous_job: str = ""
_previous_download_folder: str = ""
# a list of tasks, since there can be multiple downloads happening at the same time
_previous_tasks: list[Task] = []


def clear() -> None:
    """Clear jobs."""

    _jobs.clear()


def get_jobs() -> list[Job]:
    """Return all rendergate render jobs."""

    return _jobs


def add_job(job: Job) -> Job:
    """Add a rendergate render job."""

    _jobs.append(job)

    return job


def get_selected_job(context: Context) -> Job | None:
    """Get the job that is selected in the enum property."""

    from ..properties.properties import RendergatePreferences

    prefs: RendergatePreferences = RendergatePreferences.preferences(context)

    try:
        selected_job: Job = next(
            (j for j in get_jobs() if j.identifier == prefs.jobs), None
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
        bpy.app.timers.register(lambda: run_task_on_main_thread(task))
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

    # create corresponding bpy properties job
    from ..properties.properties import JobProperties

    all_jobs_props: set[JobProperties] = bpy.context.scene.rendergate_jobs
    new_job_props: JobProperties = all_jobs_props.add()
    new_job_props.identifier = job_id
    new_job_props.active_download = False

    return Job(
        identifier=job_id,
        number=index,
        name=job_name,
        display_name=f'"{job_name}" {created_ago}',
        description=description,
        created=created_ago,
        project_name=project_name,
        stage=stage,
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


def check_for_downloads(context: Context, trigger: DownloadTrigger) -> None:
    """
    Start a timer that frequently checks if we can download images and downloads them.
    """

    from ..properties.properties import RendergatePreferences

    try:
        bpy.app.timers.unregister(bpy.__rendergate_download)
    except Exception:
        pass

    # only if logged in
    prefs: RendergatePreferences = RendergatePreferences.preferences(context)
    if not prefs.aws_token:
        return

    selected_job: Job = get_selected_job(context)

    # there was an update made (downloads folder changed for example),
    # so we want to stop all timers and tasks that are running with old data
    if hasattr(selected_job, "images"):
        selected_job.images.clear()

    # use a partial to have a reference of the function, using lambda doesn't work
    download_images_partial: partial = partial(
        download_images_timer,
        context=context,
        job=selected_job,
        trigger=trigger,
    )
    # add timer that constantly checks for downloadable images
    bpy.app.timers.register(download_images_partial)
    # keep reference so we can unregister anytime anywhere
    bpy.__rendergate_download = download_images_partial


def download_images_timer(
    context: Context, job: Job, trigger: DownloadTrigger
) -> None | float:
    """
    Downloads all rendered images of selected job into specified download folder.

    Runs as a blender app timer called on property updates on blenders main thread.
    Returning None stops the timer.

    Everytime this function is called, we might want to stop the previous download.
    For example when changing the download folder or the selected job.
    """

    global _previous_job
    global _previous_download_folder

    from ..properties.properties import RendergatePreferences

    loop: AbstractEventLoop = asyncio.get_event_loop()

    prefs: RendergatePreferences = RendergatePreferences.preferences(context)
    if not prefs.aws_token:
        return None

    if job is None:
        return None

    if trigger == DownloadTrigger.JOB:
        if job.name != _previous_job:
            _previous_job = job.name
            stop_previous_download()

    elif trigger == DownloadTrigger.FOLDER:
        if prefs.download_folder != _previous_download_folder:
            _previous_download_folder = prefs.download_folder
            stop_previous_download()

    if not job.stage == Stage.FINISHED:
        return None

    if not prefs.download_folder:
        return None

    if not prefs.auto_download:
        stop_previous_download()
        return None

    task: Task = loop.create_task(download_images(context, job))
    _previous_tasks.append(task)

    bpy.app.timers.register(lambda: run_task_on_main_thread(task))

    return 60.0


def stop_previous_download():
    """Cancels the running download tasks."""

    for task in _previous_tasks:
        if isinstance(task, Task):
            task.cancel()
            task = None

    _previous_tasks.clear()


async def download_images(context: Context, job: Job):
    """Download missing images."""

    from ..properties.properties import RendergatePreferences

    prefs: RendergatePreferences = RendergatePreferences.preferences(context)

    # set download folder already here, so if user changes it mid-download,
    # we still download to the same initial folder
    download_folder: PurePath = PurePath(bpy.path.abspath(prefs.download_folder))

    selected_job: Job = get_selected_job(context)
    if selected_job is None:
        return

    # get list of downloadable images
    contents: list[dict[str, Any]] | None = await download.get_download_content(context)
    if contents is None:
        return
    if len(contents) == 0:
        return

    # download images
    for content in contents:
        key: str = content.get("Key")
        if key is None:
            continue

        # download to specified folder
        file_name: str = f"{PurePath(key).stem}{PurePath(key).suffix}"
        file_dir: PurePath = PurePath(download_folder / selected_job.name)
        file_path: PurePath = PurePath(file_dir / file_name)

        # get the current image from the job
        image: Image = next((i for i in job.images if i.file_path == file_path), None)
        if image is None:
            image = Image(
                file_path=file_path,
                file_name=file_name,
                file_dir=download_folder,
                state=ImageState.MISSING,
            )
            job.images.append(image)

        # check if image is not in folder yet
        if os.path.isfile(file_path):
            image.state = ImageState.DOWNLOADED
            continue

        # check if image is not being downloaded currently
        elif image.state == ImageState.DOWNLOADING:
            continue

        # the directory was not found when trying to download the image
        # when the user changes the download folder, new images will be created
        # and their state starts with MISSING again
        elif image.state == ImageState.DIRNOTFOUND:
            continue

        # image is neither present nor is it being downloaded at the moment
        else:
            image.state = ImageState.MISSING

        # download image
        image.state = ImageState.DOWNLOADING
        try:
            await download.download_image(key, file_dir, file_name)
        except FileNotFoundError as e:
            image.state = ImageState.DIRNOTFOUND
            rendergate_logger.info(f"Image {file_name} could not be downlaoded: {e}")
        else:
            image.state = ImageState.DOWNLOADED
            rendergate_logger.info(f"Downloaded image {file_name}.")


def run_task_on_main_thread(task: Task):
    """Runs the task as a timer on the blender main thread."""

    # let the event loop process pending tasks
    loop: AbstractEventLoop = asyncio.get_event_loop()
    loop.call_soon(loop.stop)
    loop.run_forever()

    utils.update_ui()

    if task.cancelling() or task.cancelled() or task.done():
        return None
    else:
        return 0.1
