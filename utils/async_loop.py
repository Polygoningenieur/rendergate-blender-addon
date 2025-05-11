# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

"""
Manages the asyncio loop.
(Copied from https://github.com/lampysprites/blender-asyncio,
who copied it from Blender Cloud plugin with minor changes)
And I made some changes.
"""


import gc
import bpy
import typing
import asyncio
import logging
import traceback
import concurrent.futures
from typing import Any
from concurrent.futures import ThreadPoolExecutor
from asyncio import AbstractEventLoop, Task
from bpy.types import WindowManager, Context
from .global_vars import rendergate_logger
from .utils import class_to_register


# Keeps track of whether a loop-kicking operator is already running.
_loop_kicking_operator_running: bool = False


def setup_asyncio_executor() -> None:
    """Sets up AsyncIO to run properly on each platform."""

    if kick_async_loop():
        erase_async_loop()
        global _loop_kicking_operator_running
        _loop_kicking_operator_running = False

    # On windows, ProactorEventLoop is now also the default event loop
    # Source: https://docs.python.org/3.11/library/asyncio-platforms.html#asyncio-windows-subprocess
    loop: AbstractEventLoop = asyncio.get_event_loop()

    executor: ThreadPoolExecutor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
    loop.set_default_executor(executor)
    loop.set_debug(
        True if rendergate_logger.getEffectiveLevel() == logging.DEBUG else False
    )


def kick_async_loop(*args) -> bool:
    """
    Performs a single iteration of the asyncio event loop.

    :return: whether the asyncio loop should stop after this kick.
    """

    loop: AbstractEventLoop = asyncio.get_event_loop()

    # Even when we want to stop, we always need to do one more
    # 'kick' to handle task-done callbacks.
    stop_after_this_kick: bool = False

    if loop.is_closed():
        rendergate_logger.warning("Loop closed, stopping immediately.")
        return True

    all_tasks: set[Task[Any]] = asyncio.all_tasks(loop)
    if not len(all_tasks):
        rendergate_logger.debug("No more scheduled tasks, stopping after this kick.")
        stop_after_this_kick = True

    elif all(task.done() for task in all_tasks):
        rendergate_logger.debug(
            f"All {len(all_tasks)} tasks are done, fetching results and stopping after this kick."
        )
        stop_after_this_kick = True

        # Clean up circular references between tasks.
        gc.collect()

        for task_idx, task in enumerate(all_tasks):
            if not task.done():
                continue

            try:
                res: Any = task.result()
                rendergate_logger.debug(f"Task #{task_idx}: result = {res}")
            except asyncio.CancelledError:
                # No problem, we want to stop anyway.
                rendergate_logger.debug(f"Task #{task_idx}: cancelled")
            except Exception:
                rendergate_logger.error(f"{repr(task)}: resulted in exception")
                traceback.print_exc()

    loop.stop()
    loop.run_forever()

    return stop_after_this_kick


def ensure_async_loop() -> None:
    rendergate_logger.debug("Starting asyncio loop")
    # is {'RUNNING_MODAL'} or {'PASS_THROUGH'} or ...
    result: set = bpy.ops.rendergate.loop()
    rendergate_logger.debug("Result of starting modal operator is %r", result)


def erase_async_loop() -> None:
    global _loop_kicking_operator_running

    rendergate_logger.debug("Erasing async loop")

    loop: AbstractEventLoop = asyncio.get_event_loop()
    loop.stop()


@class_to_register
class AsyncLoopModalOperator(bpy.types.Operator):
    """
    Kicks the asyncio loop every 0.00001 seconds.
    This is required to make sure the loop runs in the background.
    """

    bl_idname = "rendergate.loop"
    bl_label = "Runs the asyncio main loop"

    timer = None

    def __del__(self):
        global _loop_kicking_operator_running 
        rendergate_logger.debug("Deleting Async Operator")
        # This can be required when the operator is running while Blender
        # (re)loads a file. The operator then doesn't get the chance to
        # finish the async tasks, hence stop_after_this_kick is never True.
        _loop_kicking_operator_running = False

    def execute(self, context: Context):
        return self.invoke(context, None)

    def invoke(self, context: Context, event):
        global _loop_kicking_operator_running

        if _loop_kicking_operator_running:
            rendergate_logger.debug("Another loop-kicking operator is already running.")
            return {"PASS_THROUGH"}

        context.window_manager.modal_handler_add(self)
        _loop_kicking_operator_running = True

        wm: WindowManager = context.window_manager
        self.timer = wm.event_timer_add(0.00001, window=context.window)

        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event):
        global _loop_kicking_operator_running

        # If _loop_kicking_operator_running is set to False, someone called
        # erase_async_loop(). This is a signal that we really should stop
        # running.
        if not _loop_kicking_operator_running:
            return {"FINISHED"}

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        rendergate_logger.debug("KICKING LOOP")
        # stop after this kick?
        if kick_async_loop():
            context.window_manager.event_timer_remove(self.timer)
            _loop_kicking_operator_running = False

            rendergate_logger.debug("Stopped asyncio loop kicking")
            return {"FINISHED"}

        return {"RUNNING_MODAL"}


class AsyncModalOperatorMixin:
    async_task = None  # asyncio task for fetching thumbnails
    # asyncio future for signalling that we want to cancel everything.
    signalling_future = None

    _state = "INITIALIZING"
    stop_upon_exception = True

    def invoke(self, context: Context, event):
        context.window_manager.modal_handler_add(self)
        self.timer = context.window_manager.event_timer_add(
            1 / 15, window=context.window
        )

        rendergate_logger.info("Starting")

        # custom context pointer properties that can be set with:
        # layout.context_pointer_set(data, name)
        # where name needs to contain "context_pointer"
        # multiple can be set
        # we pass it through here so the async operator has access
        context_pointers: dict[Any] = {}
        for attribute_name in dir(context):
            if "context_pointer" in attribute_name:
                context_pointers.update(
                    {attribute_name: getattr(context, attribute_name, None)}
                )

        self._new_async_task(self.async_execute(context, context_pointers))

        return {"RUNNING_MODAL"}

    async def async_execute(self, context: Context, context_pointers: dict[Any]):
        """Entry point of the asynchronous operator.

        Implement in a subclass.
        """
        return

    def quit(self):
        """Signals the state machine to stop this operator from running."""
        self._state = "QUIT"

    def execute(self, context: Context):
        return self.invoke(context, None)

    def modal(self, context: Context, event):
        task = self.async_task

        if task and task.done() and not task.cancelled():
            ex = task.exception()
            if ex is not None:
                self._state = "EXCEPTION"
                rendergate_logger.error("Exception while running task: %s", ex)
                if self.stop_upon_exception:
                    self.quit()
                    self._finish(context)
                    return {"FINISHED"}

                return {"RUNNING_MODAL"}

        if self._state == "QUIT":
            self._finish(context)
            return {"FINISHED"}

        return {"PASS_THROUGH"}

    def _finish(self, context: Context):
        self._stop_async_task()
        context.window_manager.event_timer_remove(self.timer)

    def _new_async_task(
        self, async_task: typing.Coroutine, future: asyncio.Future = None
    ):
        """Stops the currently running async task, and starts another one."""

        rendergate_logger.debug(
            "Setting up a new task %r, so any existing task must be stopped", async_task
        )
        self._stop_async_task()

        # Download the previews asynchronously.
        self.signalling_future = future or asyncio.Future()
        self.async_task = asyncio.ensure_future(async_task)
        rendergate_logger.debug("Created new task %r", self.async_task)

        # Start the async manager so everything happens.
        ensure_async_loop()

    def _stop_async_task(self):
        rendergate_logger.debug("Stopping async task")
        if self.async_task is None:
            rendergate_logger.debug("No async task, trivially stopped")
            return

        # Signal that we want to stop.
        self.async_task.cancel()
        if not self.signalling_future.done():
            rendergate_logger.info(
                "Signalling that we want to cancel anything that's running."
            )
            self.signalling_future.cancel()

        # Wait until the asynchronous task is done.
        if not self.async_task.done():
            rendergate_logger.info("blocking until async task is done.")
            loop = asyncio.get_event_loop()
            try:
                loop.run_until_complete(self.async_task)
            except asyncio.CancelledError:
                rendergate_logger.info("Asynchronous task was cancelled")
                return

        # noinspection PyBroadException
        try:
            # This re-raises any exception of the task.
            self.async_task.result()
        except asyncio.CancelledError:
            rendergate_logger.info("Asynchronous task was cancelled")
        except Exception:
            rendergate_logger.exception("Exception from asynchronous task")
