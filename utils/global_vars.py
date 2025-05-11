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

import logging
from logging import Logger, Formatter, StreamHandler


def _get_rendergate_handler() -> StreamHandler:
    """Set up the format of the streamhandler and return the handler."""

    formatter = Formatter(
        "%(asctime)s %(levelname)-8s %(lineno)-5d %(funcName)-30s %(message)s"
    )
    log_handler: StreamHandler = StreamHandler()
    log_handler.setFormatter(formatter)

    return log_handler


# set up logging
rendergate_logger: Logger = logging.getLogger(__name__)
if not len(rendergate_logger.handlers):
    rendergate_logger.addHandler(_get_rendergate_handler())
rendergate_logger.setLevel(logging.DEBUG)
