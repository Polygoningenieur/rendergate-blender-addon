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

__all__ = ["load_handler", "get_download_content", "s3_download_file"]


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


class CredentialsError(Exception):
    pass


@persistent
def load_handler(_):
    """On file load, add a timer that periodically checks for downloads."""

    print(f"Load Handler: {bpy.data.filepath = }")

    try:
        bpy.app.timers.unregister(bpy.__rendergate_downloads)
    except Exception:
        pass

    try:
        # add timer that constantly checks for downloadable images
        bpy.app.timers.register(_check_for_downloads)
    except Exception as e:
        rendergate_logger.error(f"Could not register download timer: {e}")
    else:
        print("Download timer registered.")

    # keep reference so we can unregister anytime anywhere
    bpy.__rendergate_downloads = _check_for_downloads


def _check_for_downloads() -> None:
    """
    Timer that periodically checks all jobs with active downloads
    and downloads images if there are any.
    """

    from ..properties.properties import RendergateProperties, RendergatePreferences

    print("Periodic check for downloads...")

    frequency: float = 60.0

    loop: AbstractEventLoop = asyncio.get_event_loop()
    prefs: RendergatePreferences = RendergatePreferences.preferences()
    props: RendergateProperties = bpy.context.scene.rendergate_properties

    if not prefs.aws_token:
        return frequency

    for job in jobs.get_all():
        # download images if the job is done or currently rendering
        if job.stage in [Stage.FINISHED, Stage.RENDERING] and job.active_download:
            print(f"Download images for {job.name}...")
            task: Task = loop.create_task(_download_images(bpy.context, job))
            bpy.app.timers.register(lambda: utils.run_task_on_main_thread(task))

    # reset stop download flag
    props.stop_download = False

    return frequency


async def _download_images(context: Context, job: Job):
    """Download missing images."""

    from ..properties.properties import RendergateProperties, RendergatePreferences

    prefs: RendergatePreferences = RendergatePreferences.preferences(context)
    props: RendergateProperties = context.scene.rendergate_properties

    # set download folder already here, so if user changes it mid-download,
    # we still download to the same initial folder
    download_folder: PurePath = PurePath(bpy.path.abspath(prefs.download_folder))

    # get list of downloadable images
    contents: list[dict[str, Any]] | None = await get_download_content(context, job)
    if contents is None:
        return
    if not isinstance(contents, list):
        return
    if len(contents) == 0:
        return

    file_dir: PurePath = PurePath(download_folder / job.name)

    # download images
    for content in contents:
        if props.stop_download:
            return

        key: str = content.get("Key")
        if key is None:
            continue

        # check if the content is for the correct job
        if job.identifier not in key:
            rendergate_logger.error(
                f"Got content for wrong job! (Job: {job.identifier} Content: {key})"
            )
            continue

        # download to specified folder
        file_name: str = f"{PurePath(key).stem}{PurePath(key).suffix}"
        file_path: PurePath = PurePath(file_dir / file_name)

        # get the current image from the job
        image: Image = next((i for i in job.images if i.file_path == file_path), None)
        if image is None:
            image = Image(
                file_path=file_path,
                file_name=file_name,
                file_dir=file_dir,
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
            await s3_download_file(job, key, file_dir, file_name)
        except FileNotFoundError as e:
            image.state = ImageState.DIRNOTFOUND
            rendergate_logger.info(f"Image {file_name} could not be downlaoded: {e}")
        else:
            image.state = ImageState.DOWNLOADED
            rendergate_logger.info(f"Downloaded image {file_name}.")

    print(
        f"{job.name} IMAGES: {len(job.images)}\nMISSING: {len([i for i in job.images if i.state == ImageState.MISSING])}\nDOWNLOADED: {len([i for i in job.images if i.state == ImageState.DOWNLOADED])}\nDOWNLOADING: {len([i for i in job.images if i.state == ImageState.DOWNLOADING])}\nDIRNOTFOUND: {len([i for i in job.images if i.state == ImageState.DIRNOTFOUND])}"
    )


async def get_download_content(context: Context, job: Job) -> list:
    """
    Get the Contents list of the download, containing the files that can be downloaded.
    """

    loop: AbstractEventLoop = asyncio.get_event_loop()

    await _set_client_and_credentials(context, job)
    if job.download_client is None:
        rendergate_logger.error(f"Client is None.")
        return []

    max_keys: int = 100
    s3_response: dict | None = None
    contents: list[dict] = []

    list_objects_partial = partial(
        job.download_client.list_objects_v2,
        Bucket=job.download_credentials.bucket,
        Prefix=job.download_credentials.basekey,
        MaxKeys=max_keys,
    )
    try:
        s3_response = await loop.run_in_executor(None, list_objects_partial)
    except exceptions.ClientError as e:
        rendergate_logger.info(f"Client Error listing objects: {e}")
        return []

    if not isinstance(s3_response, dict):
        rendergate_logger.info(f"s3 response not a dict: {s3_response}")
        return []

    # initial content
    contents = s3_response.get("Contents", [])

    while s3_response.get("IsTruncated", False) or False:
        continuation_token: str = s3_response.get("NextContinuationToken")
        next_response_partial = partial(
            job.download_client.list_objects_v2,
            Bucket=job.download_credentials.bucket,
            Prefix=job.download_credentials.basekey,
            MaxKeys=max_keys,
            ContinuationToken=continuation_token,
        )
        try:
            s3_response = await loop.run_in_executor(None, next_response_partial)
        except exceptions.ClientError as e:
            rendergate_logger.info(f"Client Error listing continued objects: {e}")
            break
        if not isinstance(s3_response, dict):
            rendergate_logger.info(f"s3 continued response not a dict: {s3_response}")
            break

        contents.extend(s3_response.get("Contents", []))

    return contents


async def _set_client_and_credentials(context: Context, job: Job) -> None:
    """
    Sets the s3 client for the job,
    creates client and credentials if they don't exist yet.
    """

    try:
        # no client, create one
        if job.download_client is None:
            rendergate_logger.info("No client, creating...")

            # no credentials to create client, get them
            if (
                job.download_credentials is None
                or None in asdict(job.download_credentials).values()
            ):
                rendergate_logger.info("No creds, requesting...")
                try:
                    await _set_download_credentials(context, job)
                except CredentialsError as e:
                    rendergate_logger.error(f"Error getting credentials: {e}")
                    # TODO what to do, retry?
                    job.download_client = None
                    return
                else:
                    rendergate_logger.info(
                        f"New credentials: {str(job.download_credentials)[:100]}..."
                    )

            # create s3 client
            job.download_client = boto3.client(
                "s3",
                aws_access_key_id=job.download_credentials.access_key,
                aws_secret_access_key=job.download_credentials.secret_access_key,
                aws_session_token=job.download_credentials.session_token,
            )

    except Exception as err:
        rendergate_logger.error(f"{err}")
        job.download_client = None


async def _set_download_credentials(context: Context, job: Job) -> None:
    """Get the download credentials from AWS."""

    from ..properties.properties import RendergateProperties, RendergatePreferences

    props: RendergateProperties = context.scene.rendergate_properties
    prefs: RendergatePreferences = RendergatePreferences.preferences(context)

    # download render job
    response: Response | str = await rest_client.request(
        url=f"{props.rendergate_api_url}/project/{job.identifier}/downloadPerm",
        headers={"auth": prefs.aws_token},
        request_type="GET",
    )

    # error occured
    if isinstance(response, str):
        job.download_credentials = None
        raise CredentialsError(f"Error getting download credentials: {response}")

    try:
        response_json: dict = response.json()
    except JSONDecodeError as e:
        job.download_credentials = None
        raise CredentialsError(f"Couldn't decode boto3 s3 response: {e}")

    credentials_obj: dict = response_json.get("credentials", {})
    job.download_credentials = S3Credentials(
        bucket=response_json.get("bucket"),
        basekey=response_json.get("baseKey"),
        access_key=credentials_obj.get("AccessKeyId"),
        secret_access_key=credentials_obj.get("SecretAccessKey"),
        session_token=credentials_obj.get("SessionToken"),
    )
    if None in asdict(job.download_credentials).values():
        message: str = f"Got invalid credentials: {job.download_credentials}"
        job.download_credentials = None
        raise CredentialsError(message)


async def s3_download_file(job: Job, key: str, file_dir: PurePath, file_name: str):
    """Downloads a file to the specified file_path."""

    # make sure file dir exists
    Path(file_dir).mkdir(parents=True, exist_ok=True)

    file_path: PurePath = PurePath(file_dir / file_name)

    loop: AbstractEventLoop = asyncio.get_event_loop()

    download_file_partial = partial(
        job.download_client.download_file,
        job.download_credentials.bucket,
        key,
        file_path,
    )
    try:
        await loop.run_in_executor(None, download_file_partial)
    except FileNotFoundError as e:
        rendergate_logger.error(e)
        raise FileNotFoundError(e)
