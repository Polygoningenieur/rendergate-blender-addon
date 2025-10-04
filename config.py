# TODO change to production

# aws authentication
import logging


REGION: str = "us-east-2"
USER_POOL_ID: str = "us-east-2_0iJztlRUB"
USER_POOL_WEB_CLIENT_ID: str = "6m7eldka3q9f20nmev7smovnf6"
URL: str ="https://rendergate.ch"
RENDERGATE_API:str ="https://vhvr3fdsg5.execute-api.us-east-2.amazonaws.com/default"
LOGGING_LEVEL = logging.ERROR

JOB_REFRESH_RATE=30.0 # seconds
DOWNLOAD_REFRESH_RATE=30.0 # seconds
