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
from bpy.utils import register_class, unregister_class, previews
from bpy.types import Scene
from bpy.props import PointerProperty

# necessary to import modules so they can get registered
from . import properties, utils, panels, operators

from .utils.utils import classes_to_register
from .properties.properties import RendergateProperties
from .utils.async_loop import setup_asyncio_executor
from .utils.global_vars import rendergate_images

bl_info = {
    "name": "Rendergate",
    "author": "Polygoningenieur Gustav Hahn",
    "description": "Allows you to render in the cloud with Rendergate.ch",
    "blender": (4, 4, 0),
    "version": (0, 1, 33),
    "location": "Properties -> Render",
    "warning": "",
    "doc_url": "https://github.com/Polygoningenieur/rendergate-blender-addon",
    "tracker_url": "https://github.com/Polygoningenieur/rendergate-blender-addon/issues",
    "support": "COMMUNITY",
    "category": "Render",
}


def register() -> None:
    """Initialize addon by registering its classes."""

    setup_asyncio_executor()

    for c in classes_to_register:
        register_class(c)

    Scene.rendergate_properties = PointerProperty(type=RendergateProperties)

    # Note that preview collections returned by bpy.utils.previews
    # are regular py objects - you can use them to store custom data.
    pcoll: previews.ImagePreviewCollection = previews.new()
    # path to the folder where the icon is
    # the path is calculated relative to this py file inside the addon folder
    rendergate_icons_dir: str = os.path.join(os.path.dirname(__file__), "icons")
    # load a preview thumbnail of a file and store in the previews collection
    pcoll.load(
        "rendergate_logo",
        os.path.join(rendergate_icons_dir, "rendergate.png"),
        "IMAGE",
    )
    rendergate_images["main"] = pcoll


def unregister() -> None:
    """Unregister addon classes."""

    del Scene.rendergate_properties
    for c in reversed(classes_to_register):
        if c.is_registered:
            unregister_class(c)

    for pcoll in rendergate_images.values():
        previews.remove(pcoll)
    rendergate_images.clear()
