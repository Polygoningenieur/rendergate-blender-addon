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


from enum import StrEnum


class Stage(StrEnum):
    """Rendergate stage values."""

    INIT = "Initializing"
    # CALCULATING doesn't exist on rendergate (yet),
    # it is just UPLOADED without timeEst & costEst
    CALCULATING = "Calculating"
    UPLOADED = "Uploaded"
    PAYING = "Paying"
    RENDERING = "Rendering"
    FINISHED = "Finished"
    CRASHED = "Crashed"
    UNKNOWN = "Unknown Job Stage"


class ImageState(StrEnum):
    """The state an image can be in."""

    DIRNOTFOUND = "DIRNOTFOUND"
    MISSING = "MISSING"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"


class DownloadTrigger(StrEnum):
    """The properties that will trigger or influence the automatic image download."""

    JOB = "RENDER_JOB"
    FOLDER = "DOWNLOAD_FOLDER"
    AUTO = "AUTO_DOWNLOAD"
