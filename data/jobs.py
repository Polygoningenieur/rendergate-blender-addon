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
import boto3
import asyncio
from asyncio import AbstractEventLoop, Task
import decimal
from decimal import Decimal, InvalidOperation
import humanize
from dateutil import tz
from datetime import datetime, tzinfo, timedelta
from typing import Any
from pathlib import PurePath
from bpy.types import Context
from ..utils.models import Job
from ..utils.enums import Stage
from ..utils.global_vars import rendergate_logger

_jobs: list[Job] = []


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


def construct_render_job(job_data: dict, index: int) -> Job:
    """Create the Job dataclass from the response job dict."""

    job_id: str = job_data.get("id")
    job_name: str = job_data.get("name", "")
    project_name: str = job_data.get("project")
    # parse incoming stage string onto strEnum Stage
    try:
        stage: Stage = Stage[job_data.get("stage", Stage.UNKNOWN)]
    except KeyError:
        stage: Stage = Stage.UNKNOWN
    progress: str = job_data.get("progress", "")

    # create decimals for the prices to not have floating point precision errors
    # and make sure we have enough precision to quantize
    decimal.getcontext().prec = 28
    cost_estimation_number: float = job_data.get("costEst", 0.00)
    try:
        cost_estimation: Decimal = Decimal(f"{cost_estimation_number}")
        cost_estimation = cost_estimation.quantize(Decimal(".01"))
    except InvalidOperation:
        cost_estimation: Decimal = Decimal("0.00")

    cost_number: float = job_data.get("cost", 0.0)
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
    time_estimation: float = job_data.get("timeEst", 0.0)
    time_estimation_delta: timedelta = timedelta(milliseconds=time_estimation)
    time_estimation_human: str = humanize.precisedelta(
        time_estimation_delta, minimum_unit="minutes"
    )

    # human readable time
    time: float = job_data.get("time", 0.0)
    time_delta: timedelta = timedelta(milliseconds=time)
    time_human: str = humanize.precisedelta(time_delta, minimum_unit="minutes")

    description: str = (
        f"Job {index}\nCreated: {created_ago}\nProject: {project_name}\nStage: {stage}\nProgress: {progress}\nCost Estimation: ${cost_estimation}\nCost: {cost}\nTime Estimation: {time_estimation_human}\nTime: {time_human}"
    )

    return Job(
        identifier=job_id,
        number=index,
        name=job_name,
        display_name=f'"{job_name}" {created_ago}',
        description=description,
        created=created_ago,
        project_name=project_name,
        stage=stage,
        progress=progress,
        cost_estimation=cost_estimation,
        cost=cost,
        time_estimation=time_estimation,
        time_estimation_human=time_estimation_human,
        time=time,
        time_human=time_human,
        preview_link=preview,
        images=[],
    )


def download_images_timer(context: Context, job: Job) -> None | float:
    """
    Downloads all rendered images of selected job into specified download folder.

    Runs as a blender app timer called on property updates on blenders main thread.
    Returning None stops the timer.

    """

    from ..properties.properties import RendergatePreferences
    from ..operators.download_images import RENDERGATE_OT_download_images as download

    loop: AbstractEventLoop = asyncio.get_event_loop()

    prefs: RendergatePreferences = RendergatePreferences.preferences(context)
    if not prefs.aws_token:
        return None

    if job is None:
        return None

    # TODO if job has no downloadable images (check status)

    if not prefs.download_folder:
        return None

    task: Task = loop.create_task(download_wrapper(context))

    bpy.app.timers.register(lambda: run_download_task_timer(task))

    print(f"download check for {job.display_name}.")

    return 2.0


async def download_wrapper(context: Context):
    """Download missing images.

    # TODO don't download images that are currently being downloaded again
    # TODO optimize: get download credentials only once (are valid for 1 hour)
    # TODO then use the same client
    """

    from ..properties.properties import RendergatePreferences
    from ..operators.download_images import RENDERGATE_OT_download_images as download

    prefs: RendergatePreferences = RendergatePreferences.preferences(context)

    # set download folder already here, so if user changes it mid-download,
    # we still download to the same initial folder
    download_folder: PurePath = PurePath(bpy.path.abspath(prefs.download_folder))

    # get download credentials
    BUCKET, BASEKEY, ACCESS_KEY, SECRET_KEY, SESSION_TOKEN = (
        await download.get_download_credentials(context)
    )
    if (
        not BUCKET
        or not BASEKEY
        or not ACCESS_KEY
        or not SECRET_KEY
        or not SESSION_TOKEN
    ):
        return

    # create s3 client
    client = boto3.client(
        "s3",
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        aws_session_token=SESSION_TOKEN,
    )

    # get list of downloadable images
    contents: list[dict[str, Any]] | None = await download.get_download_content(
        client, BUCKET, BASEKEY
    )
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
        file_path: PurePath = PurePath(download_folder / file_name)

        # check if image is not in folder yet
        if os.path.isfile(file_path):
            rendergate_logger.info(f"File {file_name} exists.")
        else:
            await download.download_image(client, BUCKET, key, file_path)
            rendergate_logger.info(f"Downloaded image {file_name}.")


def run_download_task_timer(task: Task):
    """Runs the task as a timer on the blender main thread."""

    # Let the event loop process pending tasks
    loop: AbstractEventLoop = asyncio.get_event_loop()
    loop.call_soon(loop.stop)
    loop.run_forever()

    if task.done():
        return None
    else:
        return 0.1
