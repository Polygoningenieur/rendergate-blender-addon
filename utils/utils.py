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
import bpy
import asyncio
import traceback
from typing import Any, Callable
from functools import wraps
from bpy.types import Context
from .global_vars import rendergate_logger

classes_to_register: list = []


def class_to_register(cls):
    """Class annotation to add this class to a list to be registered."""

    classes_to_register.append(cls)
    return cls


def catch_exception(callback: Callable):
    """
    Decorator that wraps an async bpy operator function into a try-except block.
    Accepts a callback function, so you can reset parameters or do cleanup
    when an exception occurs.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                rendergate_logger.error(
                    f"Exception in async operator {func}:\n{repr(e)}"
                )
                # get the context from the bpy operator function
                context: Context = None
                context_pointers: dict[str, Any] = {}
                for arg in args:
                    rendergate_logger.info(f"{arg = } {type(arg) = }")
                    if isinstance(arg, Context):
                        context = arg
                    if isinstance(arg, dict):
                        context_pointers = arg
                # call callback function with self (func) and context
                if callable(callback) and context:
                    callback(func, context, context_pointers)

        return wrapper

    return decorator


def get_file_size(file_path: str) -> int:
    """Get the size of a file in bytes"""

    try:
        return os.path.getsize(file_path)
    except OSError:
        rendergate_logger.error(traceback.format_exc())
        return 0
    except FileNotFoundError as e:
        rendergate_logger.error(traceback.format_exc())
        return 0
    except Exception:
        rendergate_logger.error(traceback.format_exc())
        return 0


def format_file_size(file_bytes: int) -> str:
    """Display readable file size."""

    suffix: str = "B"
    for unit in ("", "k", "M", "G", "T", "P", "E", "Z"):
        if abs(file_bytes) < 1000.0:
            return f"{file_bytes:3.2f} {unit}{suffix}"
        file_bytes /= 1000.0
    return f"{file_bytes:.2f}Y{suffix}"


def path_leaf(path: str) -> str:
    """Get the head and tail of a path, platform independent."""

    # normalize path
    path = os.path.normpath(path)

    head: str = ""
    tail: str = ""
    head, tail = os.path.split(path)

    return tail or os.path.basename(head)


def is_string_blank(string: str) -> bool:
    """Returns true if the string is blank."""

    return not bool(string and not string.isspace())


async def progress(
    obj: Any,
    prop_name: str,
    value: float,
    context: Context = None,
    sleep: float = 0.0,
):
    """Set a progress property."""

    setattr(obj, prop_name, value)

    try:
        if context:
            context.area.tag_redraw()
        else:
            bpy.context.area.tag_redraw()
    except:
        pass

    await asyncio.sleep(sleep)
