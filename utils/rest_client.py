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


import json
import asyncio
from asyncio import AbstractEventLoop, Future
from requests import Response, Session  # requests gets delivered with Blender 4.5
from requests.exceptions import (
    HTTPError,
    Timeout,
    ConnectionError,
    RequestException,
)


async def request(
    url: str,
    headers: dict = None,
    payload: dict = None,
    files: dict = None,
    request: str = "POST",
) -> Response | str:
    """Make a generic REST request to a service.

    Args:
        url: The URL of the service.
        payload: Optional data to send with the request.
        header: Optional headers for the request.
        files: Optional files to send with the request.
        post: Use the default http POST request or GET

    Returns:
        The response object if the request is successful,
        otherwise a string with the error/failed message.
    """

    loop: AbstractEventLoop = asyncio.get_event_loop()
    session: Session = Session()

    try:
        if request == "POST":
            future: Future = loop.run_in_executor(
                None,
                lambda: session.post(
                    url,
                    headers=headers,
                    json=payload,
                    files=files,
                    timeout=10,
                ),
            )
        elif request == "POST-DATA":
            future: Future = loop.run_in_executor(
                None,
                lambda: session.post(
                    url,
                    data=payload,
                    timeout=10,
                ),
            )
        elif request == "PUT":
            future: Future = loop.run_in_executor(
                None,
                lambda: session.put(
                    url,
                    data=payload,
                ),
            )
        # get
        else:
            future: Future = loop.run_in_executor(
                None,
                lambda: session.get(
                    url,
                    headers=headers,
                    timeout=10,
                ),
            )

    except Exception as e:
        return f"Error running async loop while requesting from API {repr(e)}"

    try:
        response: Response = await future
        if response.status_code >= 100 and response.status_code < 200:
            return format_failed_response(
                response, response.status_code, "Informational Response"
            )
        elif response.status_code >= 200 and response.status_code < 300:
            return response
        elif response.status_code >= 300 and response.status_code < 400:
            return format_failed_response(response, response.status_code, "Redirection")
        elif response.status_code == 401:
            return f"Token expired. Please log in again."
        elif response.status_code >= 400 and response.status_code < 500:
            return format_failed_response(
                response, response.status_code, "Client Error"
            )
        elif response.status_code >= 500 and response.status_code < 600:
            return format_failed_response(
                response, response.status_code, "Server Error"
            )
        else:
            response.raise_for_status()
    except (HTTPError, ConnectionError, Timeout, RequestException) as e:
        return f"Error requesting from API {repr(e)}.\n{url=}\n{payload=}\n{headers=}\n{files=}\n{request=}\n"
    except Exception as e:
        return f"Unknown error requesting. {repr(e)}"


def format_failed_response(
    response: Response, status_code: int, status_type: str
) -> str:
    """Return string representation of failed response."""

    try:
        status_dict: dict = json.loads(response.text)
    except Exception as e:
        return f"Error parsing failed response message {repr(e)}"

    # add more info
    status_dict.update({"status_code": status_code})
    status_dict.update({"status_type": status_type})

    failure_text: str = ""
    for key, value in status_dict.items():
        if key == "message":
            failure_text += f"{str(value).capitalize()}.\n"
        else:
            failure_text += f"{str(key).replace('_', ' ').capitalize()}: {value}\n"

    return failure_text
