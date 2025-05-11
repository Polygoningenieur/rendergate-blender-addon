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
from asyncio import AbstractEventLoop, Future
from requests import Response, Session  # requests gets delivered with Blender 4.4
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
        The response object if the request is successful, otherwise None.
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
            return f"{response.status_code}: Informational Response: {response.text}"
        elif response.status_code >= 200 and response.status_code < 300:
            return response
        elif response.status_code >= 300 and response.status_code < 400:
            return f"{response.status_code}: Redirection: {response.text}"
        elif response.status_code == 401:
            return f"Token expired. Please log in again."
        elif response.status_code >= 400 and response.status_code < 500:
            return f"{response.status_code}: Client Error: {response.text}"
        elif response.status_code >= 500 and response.status_code < 600:
            return f"{response.status_code}: Server Error: {response.text}"
        else:
            response.raise_for_status()
    except (HTTPError, ConnectionError, Timeout, RequestException) as e:
        return f"Error requesting from API {repr(e)}.\n{url=}\n{payload=}\n{headers=}\n{files=}\n{request=}\n"
    except Exception as e:
        return f"Unknown error requesting. {repr(e)}"
