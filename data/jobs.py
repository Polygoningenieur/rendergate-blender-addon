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


import decimal
from decimal import Decimal, InvalidOperation
import humanize
from dateutil import tz
from datetime import datetime, tzinfo
from bpy.types import Context
from ..utils.models import Job
from ..utils.enums import Stage
from ..utils.global_vars import rendergate_logger

_jobs: list[Job] = []


def get_jobs() -> list[Job]:
    """Return all rendergate render jobs."""

    return _jobs


def add_job(job: Job) -> Job:
    """Add a rendergate render job."""

    _jobs.append(job)

    return job


def get_selected_render_job(context: Context) -> Job | None:
    """Get the job that is selected in the enum property."""

    from ..properties.properties import RendergateProperties

    props: RendergateProperties = context.scene.rendergate_properties

    try:
        selected_job: Job = next(
            (j for j in get_jobs() if j.identifier == props.jobs), None
        )
    except IndexError as e:
        rendergate_logger.error(repr(e))
        return None
    else:
        return selected_job


def set_selected_render_job(context: Context, identifier: str) -> None:
    """Set the selected enum job by job identifier."""

    from ..properties.properties import RendergateProperties

    props: RendergateProperties = context.scene.rendergate_properties

    props.jobs = identifier


def construct_render_job(job_data: dict, index: int) -> Job:
    """Create the Job dataclass from the response job dict."""

    job_id: str = job_data.get("id")
    job_name: str = job_data.get("name", "")
    project_name: str = job_data.get("project")
    # parse incoming stage string onto strEnum Stage
    try:
        stage: Stage = Stage[job_data.get("stage", Stage.UNKNOWN)]
    except KeyError:
        stage: Stage = Stage.UNKNOWN
    progress: str = job_data.get("progress", "")

    # create decimals for the prices to not have floating point precision errors
    # and make sure we have enough precision to quantize
    decimal.getcontext().prec = 28
    cost_estimation_number: float = job_data.get("costEst", 0.00)
    try:
        cost_estimation: Decimal = Decimal(f"{cost_estimation_number}")
        cost_estimation = cost_estimation.quantize(Decimal(".01"))
    except InvalidOperation:
        cost_estimation: Decimal = Decimal("0.00")

    cost_number: float = job_data.get("cost", 0.0)
    try:
        cost: Decimal = Decimal(f"{cost_number}")
        cost = cost.quantize(Decimal(".01"))
    except InvalidOperation as e:
        cost: Decimal = Decimal("0.00")

    time_estimation: float = job_data.get("timeEst", 0.0)
    time: float = job_data.get("time", 0.0)
    preview: str = job_data.get("preview", "")

    # created time
    created: str = job_data.get("creationDate")
    from_zone: tzinfo = tz.tzutc()
    to_zone: tzinfo = tz.tzlocal()
    date_time_utc: datetime = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ")
    # tell the datetime object that it's in UTC time zone since
    # datetime objects are naive by default
    date_time_utc = date_time_utc.replace(tzinfo=from_zone)
    # convert to local time zone
    date_time_local = date_time_utc.astimezone(to_zone)
    created_ago: str = humanize.naturaltime(date_time_local)

    description: str = (
        f"Job {index}\nCreated: {created_ago}\nProject: {project_name}\nStage: {stage}\nProgress: {progress}\nCost Estimation: ${cost_estimation}\nCost: {cost}\nTime Estimation: {time_estimation}\nTime: {time}"
    )

    return Job(
        identifier=job_id,
        number=index,
        name=job_name,
        display_name=f'"{job_name}" {created_ago}',
        description=description,
        created=created_ago,
        project_name=project_name,
        stage=stage,
        progress=progress,
        cost_estimation=cost_estimation,
        cost=cost,
        time_estimation=time_estimation,
        time=time,
        preview_link=preview,
    )
