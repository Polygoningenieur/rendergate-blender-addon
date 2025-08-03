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

__all__ = ["get_download_content", "download_image"]


import boto3
import asyncio
from pathlib import PurePath
from functools import partial
from requests import Response  # requests is included in Blender 4.5
from asyncio import AbstractEventLoop
from bpy.types import Context
from json.decoder import JSONDecodeError
from botocore import exceptions
from dataclasses import asdict
from . import jobs
from ..utils import rest_client
from ..utils.models import Job, S3Credentials
from ..utils.global_vars import rendergate_logger


_s3_client = None
_credentials: S3Credentials | None = None


class CredentialsError(Exception):
    pass


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
                    rendergate_logger.info(f"New credentials: {_credentials}")

            # create s3 client
            _s3_client = boto3.client(
                "s3",
                aws_access_key_id=_credentials.access_key,
                aws_secret_access_key=_credentials.secret_access_key,
                aws_session_token=_credentials.session_token,
            )
    except Exception as err:
        rendergate_logger.error(f"{err}")


async def _get_download_credentials(context: Context) -> S3Credentials:
    """Get the download credentials from AWS."""

    global _credentials

    from ..properties.properties import RendergateProperties, RendergatePreferences

    props: RendergateProperties = context.scene.rendergate_properties
    prefs: RendergatePreferences = RendergatePreferences.preferences(context)

    selected_job: Job = jobs.get_selected_job(context)

    # download render job
    response: Response | str = await rest_client.request(
        url=f"{props.rendergate_api_url}/project/{selected_job.identifier}/downloadPerm",
        headers={"auth": prefs.aws_token},
        request="GET",
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


async def download_image(key: str, file_path: PurePath):
    """Downloads a file to the specified file_path."""

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
