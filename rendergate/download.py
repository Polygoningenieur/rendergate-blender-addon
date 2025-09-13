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

__all__ = ["get_download_content", "s3_download_file"]


import os
import bpy
import boto3
import asyncio
from typing import Any
from pathlib import PurePath, Path
from functools import partial
from requests import Response  # requests is included in Blender 4.5
from asyncio import AbstractEventLoop, Task
from bpy.app.handlers import persistent
from bpy.types import Context
from json.decoder import JSONDecodeError
from botocore import exceptions
from dataclasses import asdict
from . import jobs
from ..utils import utils, rest_client
from ..utils.models import Job, S3Credentials, Image, ImageState
from ..utils.global_vars import rendergate_logger
from ..utils.enums import Stage


_s3_client = None
_credentials: S3Credentials | None = None


class CredentialsError(Exception):
    pass


@persistent
def load_handler(_):
    """On file load, add a timer that periodically checks for downloads."""


    try:
        bpy.app.timers.unregister(bpy.__rendergate_downloads)
    except Exception:
        pass

    try:
        # add timer that constantly checks for downloadable images
        bpy.app.timers.register(check_for_downloads)
    except Exception as e:
        rendergate_logger.error(f"Could not register download timer: {e}")

    # keep reference so we can unregister anytime anywhere
    bpy.__rendergate_downloads = check_for_downloads


def check_for_downloads() -> None:
    """
    Timer that periodically checks all jobs with active downloads
    and downloads images if there are any.
    """

    from ..properties.properties import RendergatePreferences, JobProperties

    frequency: float = 5.0

    loop: AbstractEventLoop = asyncio.get_event_loop()
    prefs: RendergatePreferences = RendergatePreferences.preferences()
    all_jobs: list[Job] = jobs.get_jobs()

    if not prefs.aws_token:
        return frequency

    for job in all_jobs:
        job_props: JobProperties = jobs.get_properties(bpy.context, job)
        if job_props is None:
            continue
        # download images if the job is done or currently rendering
        if job.stage in [Stage.FINISHED, Stage.RENDERING] and job_props.active_download:
            task: Task = loop.create_task(download_images(bpy.context, job))
            bpy.app.timers.register(lambda: utils.run_task_on_main_thread(task))

    return frequency


async def _set_client(context: Context) -> None:
    """Set the s3 client, creates it if client doesn't exist yet."""

    global _s3_client, _credentials

    try:

        if _s3_client is None:

            rendergate_logger.info("No client, creating...")

            if _credentials is None or None in asdict(_credentials).values():
                rendergate_logger.info("No creds, requesting...")
                try:
                    _credentials = await _get_download_credentials(context)
                except CredentialsError as e:
                    rendergate_logger.error(f"Error getting credentials: {e}")
                    # TODO what to do, retry?
                    _s3_client = None
                    return
                else:
                    rendergate_logger.info(
                        f"New credentials: {str(_credentials)[:100]}..."
                    )

            # create s3 client
            _s3_client = boto3.client(
                "s3",
                aws_access_key_id=_credentials.access_key,
                aws_secret_access_key=_credentials.secret_access_key,
                aws_session_token=_credentials.session_token,
            )
    except Exception as err:
        rendergate_logger.error(f"{err}")


async def _get_download_credentials(context: Context) -> S3Credentials | None:
    """Get the download credentials from AWS."""

    global _credentials

    from ..properties.properties import RendergateProperties, RendergatePreferences

    props: RendergateProperties = context.scene.rendergate_properties
    prefs: RendergatePreferences = RendergatePreferences.preferences(context)

    selected_job: Job = jobs.get_selected_job(context)
    if selected_job is None:
        raise CredentialsError(f"No job selected.")

    # download render job
    response: Response | str = await rest_client.request(
        url=f"{props.rendergate_api_url}/project/{selected_job.identifier}/downloadPerm",
        headers={"auth": prefs.aws_token},
        request_type="GET",
    )

    # error occured
    if isinstance(response, str):
        raise CredentialsError(f"Error getting download credentials: {response}")

    try:
        response_json: dict = response.json()
    except JSONDecodeError as e:
        raise CredentialsError(f"Couldn't decode boto3 s3 response: {e}")

    credentials_obj: dict = response_json.get("credentials", {})
    _credentials = S3Credentials(
        bucket=response_json.get("bucket"),
        basekey=response_json.get("baseKey"),
        access_key=credentials_obj.get("AccessKeyId"),
        secret_access_key=credentials_obj.get("SecretAccessKey"),
        session_token=credentials_obj.get("SessionToken"),
    )
    if None in asdict(_credentials).values():
        message: str = f"Got invalid credentials: {_credentials}"
        _credentials = None
        raise CredentialsError(message)

    return _credentials


async def get_download_content(context: Context) -> list:
    """
    Get the Contents list of the download, containing the files that can be downloaded.
    """

    loop: AbstractEventLoop = asyncio.get_event_loop()

    await _set_client(context)
    if _s3_client is None:
        rendergate_logger.error(f"Client is None.")
        return []

    s3_response: dict | None = None

    try:
        list_objects_partial = partial(
            _s3_client.list_objects_v2,
            Bucket=_credentials.bucket,
            Prefix=_credentials.basekey,
        )
        s3_response = await loop.run_in_executor(None, list_objects_partial)
    except exceptions.ClientError as e:
        rendergate_logger.info(f"Client Error listing objects: {e}")
        return []

    if not isinstance(s3_response, dict):
        rendergate_logger.info(f"s3 response not a dict: {s3_response}")
        return []

    # list of downloadable images is in Contents
    return s3_response.get("Contents", [])


async def download_images(context: Context, job: Job):
    """Download missing images."""

    from ..properties.properties import RendergatePreferences

    prefs: RendergatePreferences = RendergatePreferences.preferences(context)

    # set download folder already here, so if user changes it mid-download,
    # we still download to the same initial folder
    download_folder: PurePath = PurePath(bpy.path.abspath(prefs.download_folder))

    # get list of downloadable images
    contents: list[dict[str, Any]] | None = await get_download_content(context)
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
        file_dir: PurePath = PurePath(download_folder / job.name)
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
            await s3_download_file(key, file_dir, file_name)
        except FileNotFoundError as e:
            image.state = ImageState.DIRNOTFOUND
            rendergate_logger.info(f"Image {file_name} could not be downlaoded: {e}")
        else:
            image.state = ImageState.DOWNLOADED
            rendergate_logger.info(f"Downloaded image {file_name}.")


async def s3_download_file(key: str, file_dir: PurePath, file_name: str):
    """Downloads a file to the specified file_path."""

    # make sure file path exists
    Path(file_dir).mkdir(parents=True, exist_ok=True)

    file_path: PurePath = PurePath(file_dir / file_name)

    loop: AbstractEventLoop = asyncio.get_event_loop()

    download_file_partial = partial(
        _s3_client.download_file,
        _credentials.bucket,
        key,
        file_path,
    )
    try:
        await loop.run_in_executor(None, download_file_partial)
    except FileNotFoundError as e:
        rendergate_logger.error(e)
        raise FileNotFoundError(e)
