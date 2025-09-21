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

__all__ = ["login"]

import string
import random
import asyncio
from functools import partial
from warrant import Cognito
from bpy.types import Context
from asyncio import AbstractEventLoop
from ..utils.global_vars import rendergate_logger


# aws authentication
# TODO change to production
REGION: str = "us-east-2"
USER_POOL_ID: str = "us-east-2_0iJztlRUB"
USER_POOL_WEB_CLIENT_ID: str = "6m7eldka3q9f20nmev7smovnf6"


async def login(context: Context) -> None:
    """Logs the user in using Cognito."""

    from ..properties.properties import RendergatePreferences
    loop: AbstractEventLoop = asyncio.get_event_loop()
    prefs: RendergatePreferences = RendergatePreferences.preferences(context)

    try:
        user: Cognito = Cognito(
            user_pool_id=USER_POOL_ID,
            client_id=USER_POOL_WEB_CLIENT_ID,
            user_pool_region=REGION,
            username=prefs.username,
        )
        authenticate_partial = partial(user.authenticate, password=prefs.password)
        await loop.run_in_executor(None, authenticate_partial)

    except Exception as e:
        raise Exception(e)

    # login sucessfull
    prefs.aws_token = user.id_token
    prefs.aws_access_token = user.access_token
    prefs.aws_refresh_token = user.refresh_token

    # from Blender ID Authentication Addon:
    # Prevent saving the password in user preferences
    # Overwrite the password with a random string,
    # as just setting to '' might only replace the first byte with 0
    password_length: int = len(prefs.password)
    random_string: str = "".join(
        random.choice(string.ascii_uppercase + string.digits)
        for _ in range(password_length + 16)
    )
    prefs.password = random_string
    prefs.password = ""

async def get_aws_token(context: Context) -> str:
    from ..properties.properties import RendergatePreferences
    loop: AbstractEventLoop = asyncio.get_event_loop()
    prefs: RendergatePreferences = RendergatePreferences.preferences(context)
    user:Cognito=Cognito(
        user_pool_id=USER_POOL_ID,
        client_id=USER_POOL_WEB_CLIENT_ID,
        user_pool_region=REGION,
        username=prefs.username,
        id_token=prefs.aws_token,
        access_token=prefs.aws_access_token,
        refresh_token=prefs.aws_refresh_token
    )
    await loop.run_in_executor(None,user.check_token)
    prefs.aws_token = user.id_token
    prefs.aws_access_token = user.access_token
    prefs.aws_refresh_token = user.refresh_token
    return user.id_token




def refresh_id_token() -> None:
    """
    Token expired, getting new id token with refresh token.
    The exact cause of failure is not important to the user so we just log it.
    """
    from ..properties.properties import RendergatePreferences

    prefs: RendergatePreferences = RendergatePreferences.preferences()

    if not prefs.aws_refresh_token:
        rendergate_logger.error(f"No refresh token available. Please log in again.")
        raise AttributeError()

    user: Cognito = Cognito(
        user_pool_id=USER_POOL_ID,
        client_id=USER_POOL_WEB_CLIENT_ID,
        user_pool_region=REGION,
        username=prefs.username,
    )
    user.refresh_token = prefs.aws_refresh_token
    try:
        expired: bool = user.renew_access_token()
    except AttributeError as e:
        rendergate_logger.error(f"Error refreshing Cognito user token: {e}")
        raise AttributeError()

    prefs.aws_token = user.id_token
    prefs.aws_access_token = user.access_token
    prefs.aws_refresh_token = user.refresh_token
