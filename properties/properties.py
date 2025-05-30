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


# pyright: reportInvalidTypeForm=false

from bpy.types import PropertyGroup, AddonPreferences, Context
from bpy.props import (
    StringProperty,
    IntProperty,
    BoolProperty,
    EnumProperty,
    FloatProperty,
)
from .. import __package__ as base_package
from ..utils.utils import class_to_register
from .property_updates import RendergatePropertyUpdates


@class_to_register
class RendergateProperties(PropertyGroup):

    async_op_running: BoolProperty(
        name="Async Operator Running",
        description="If an asynchronous bpy operator is currently running",
        default=False,
        options={"HIDDEN"},
    )

    rendergate_api_url: StringProperty(
        name="Rendergate API URL",
        description="The URL of the rendergate API",
        default="https://vhvr3fdsg5.execute-api.us-east-2.amazonaws.com/default",
        options={"HIDDEN"},
    )

    blend_file_path: StringProperty(
        name="Blend File Path",
        description="The absolute path of the blend-file.",
        default="",
        options={"HIDDEN"},
    )

    blend_file_size: IntProperty(
        name="Blend File Size",
        description="File Size of the blend-file in bytes",
        default=0,
        options={"HIDDEN"},
    )

    getting_jobs: BoolProperty(
        name="Getting Jobs",
        description="If we are currently getting the render jobs from rendergate.ch",
        default=False,
        options={"HIDDEN"},
    )

    create_job_progress: FloatProperty(
        soft_min=0.0,
        soft_max=1.0,
        min=0.0,
        max=1.0,
        default=1.0,
    )

    create_job_progress_text: StringProperty()

    download_job_progress: FloatProperty(
        soft_min=0.0,
        soft_max=1.0,
        min=0.0,
        max=1.0,
        default=1.0,
    )

    download_job_progress_text: StringProperty()

    render_job_progress: FloatProperty(
        soft_min=0.0,
        soft_max=1.0,
        min=0.0,
        max=1.0,
        default=1.0,
    )

    render_job_progress_text: StringProperty()

    render_credits: StringProperty(
        name="Render Credits",
        description="Your rendergate.ch render credit balance. You can add more on rendergate.ch",
    )


@class_to_register
class RendergatePreferences(AddonPreferences):
    """
    These are like properties, but are not saved within the blend-file,
    since they don't get attached to Scene for example.
    """

    @staticmethod
    def preferences(context: Context):
        """Get the rendergate preferences."""

        try:
            preferences = context.preferences
        except AttributeError:
            preferences = context.user_preferences

        addon_prefs = preferences.addons[base_package].preferences
        return addon_prefs

    # this must match the addon name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = base_package

    username: StringProperty(
        name="Username",
        description="Your Rendergate username (e-mail address)",
        options={"HIDDEN", "SKIP_SAVE"},
    )

    password: StringProperty(
        name="Password",
        description="Your Rendergate login password",
        options={"HIDDEN", "SKIP_SAVE"},
    )

    aws_token: StringProperty(
        name="AWS Token",
        description="The token we get when logging into AWS Cognito.",
        default="",
        options={"HIDDEN", "SKIP_SAVE"},
    )

    job_name: StringProperty(
        name="Job Name*",
        description="Name of the job that will be created",
        default="",
        options={"HIDDEN", "SKIP_SAVE"},
    )

    project_name: StringProperty(
        name="Project Name",
        description="Name of the project the job will be added to",
        default="",
    )

    jobs: EnumProperty(
        name="Render Jobs",
        description="All your rendergate.ch render jobs",
        items=RendergatePropertyUpdates.create_job_list,
        default=0,
    )

    download_folder: StringProperty(
        name="Download Folder",
        description="The folder where rendered results from Rendergate.ch will be stored in",
        subtype="DIR_PATH",
        default="",
    )
