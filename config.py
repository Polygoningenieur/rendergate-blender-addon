# TODO change to production

# aws authentication
import logging


REGION: str = "us-east-2"
USER_POOL_ID: str = "us-east-2_2BByuLtIX"
USER_POOL_WEB_CLIENT_ID: str = "5pafa8521fg1gl8opp8p908d9p"
URL: str ="https://rendergate.ch"
RENDERGATE_API:str ="https://5qa62yq9vi.execute-api.us-east-2.amazonaws.com/default"
LOGGING_LEVEL = logging.ERROR
JOB_REFRESH_RATE=30.0 # seconds
DOWNLOAD_REFRESH_RATE=30.0 # seconds
