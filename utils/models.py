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

from dataclasses import dataclass
from decimal import Decimal
from pathlib import PurePath
from .enums import Stage, ImageState


@dataclass
class Image:
    file_path: PurePath
    file_name: str
    file_dir: PurePath
    state: ImageState

    def __eq__(self, other: str):
        return self.file_path == other


@dataclass
class Job:
    identifier: str
    number: int
    name: str
    display_name: str
    description: str
    created: str
    project_name: str
    stage: Stage
    progress: str
    cost_estimation: Decimal
    cost: Decimal
    time_estimation: float
    time_estimation_human: str
    time: float
    time_human: str
    preview_link: str
    images: list[Image]
    frames: int

    def __eq__(self, other: str):
        return self.identifier == other


@dataclass
class S3Credentials:
    bucket: str | None
    basekey: str | None
    access_key: str | None
    secret_access_key: str | None
    session_token: str | None
