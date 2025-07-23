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

import asyncio
from pathlib import PurePath
from functools import partial
from requests import Response  # requests is included in Blender 4.4
from asyncio import AbstractEventLoop
from bpy.types import Context
from json.decoder import JSONDecodeError
from . import jobs
from ..utils import rest_client
from ..utils.models import Job
from ..utils.global_vars import rendergate_logger


async def get_download_credentials(context: Context) -> tuple[str, str, str, str, str]:
    """Get the download credentials from AWS."""

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
        rendergate_logger.error(
            f"Getting download credentials returned an error: {response}"
        )
        return None, None, None, None, None

    try:
        response_json: dict = response.json()
    except JSONDecodeError as e:
        rendergate_logger.error(f"Couldn't decode boto3 s3 response: {e}")
        return None, None, None, None, None

    credentials: dict = response_json.get("credentials", {})
    BUCKET: str = response_json.get("bucket")
    BASEKEY: str = response_json.get("baseKey")
    ACCESS_KEY: str = credentials.get("AccessKeyId")
    SECRET_KEY: str = credentials.get("SecretAccessKey")
    SESSION_TOKEN: str = credentials.get("SessionToken")

    return BUCKET, BASEKEY, ACCESS_KEY, SECRET_KEY, SESSION_TOKEN


async def get_download_content(client, bucket: str, base_key: str):
    """
    Get the Contents list of the download, containing the files that can be downloaded.
    """

    loop: AbstractEventLoop = asyncio.get_event_loop()

    list_objects_partial = partial(
        client.list_objects_v2, Bucket=bucket, Prefix=base_key
    )
    s3_response: dict = await loop.run_in_executor(None, list_objects_partial)
    if not isinstance(s3_response, dict):
        return None

    # list of downloadable images is in Contents
    return s3_response.get("Contents", [])


async def download_image(client, bucket: str, key: str, file_path: PurePath):
    """Downloads a file to the specified file_path."""

    loop: AbstractEventLoop = asyncio.get_event_loop()

    download_file_partial = partial(client.download_file, bucket, key, file_path)
    try:
        await loop.run_in_executor(None, download_file_partial)
    except FileNotFoundError as e:
        rendergate_logger.error(e)
        raise FileNotFoundError(e)
