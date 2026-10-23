import os
from urllib.parse import unquote

from dotenv import load_dotenv

load_dotenv()

BUS_ROUTE_INFO_INQIRE_SERVICE_KEY = unquote(os.environ["BUS_ROUTE_INFO_INQIRE_SERVICE_KEY"])
BUS_LC_INFO_INQIRE_SERVICE_KEY = unquote(os.environ["BUS_LC_INFO_INQIRE_SERVICE_KEY"])
KMA_ASOS_HOURLY_SERVICE_KEY = unquote(os.environ["KMA_ASOS_HOURLY_SERVICE_KEY"])
