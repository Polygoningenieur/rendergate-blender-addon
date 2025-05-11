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
import traceback
from warrant import Cognito
from bpy.types import Operator, Context
from ..utils.utils import class_to_register
from ..utils.global_vars import rendergate_logger
from ..properties.properties import RendergateProperties


@class_to_register
class RENDERGATE_OT_login(Operator):
    bl_idname = "rendergate.login"
    bl_label = "Login"
    bl_description = "Login into you Rendergate.ch account."
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context: Context):
        """
        Logs into AWS cognito with warrant (using boto3).
        """

        props: RendergateProperties = context.scene.rendergate_properties

        # aws authentication
        REGION: str = "us-east-2"
        USER_POOL_ID: str = "us-east-2_0iJztlRUB"
        USER_POOL_WEB_CLIENT_ID: str = "6m7eldka3q9f20nmev7smovnf6"

        try:
            user: Cognito = Cognito(
                user_pool_id=USER_POOL_ID,
                client_id=USER_POOL_WEB_CLIENT_ID,
                user_pool_region=REGION,
                username=props.username,
            )
            user.authenticate(password=props.password)

        except Exception as e:
            rendergate_logger.error(traceback.format_exc())
            props.aws_token = ""
            self.report({"ERROR"}, f"Login failed: {str(e)}")
            return {"CANCELLED"}

        else:
            props.aws_token = user.id_token

            # get jobs
            try:
                bpy.ops.rendergate.get_jobs("EXEC_DEFAULT")
            except Exception as e:
                rendergate_logger.error(f"{repr(e)}")

        self.report({"INFO"}, "Login successfull.")
        return {"FINISHED"}
