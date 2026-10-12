import logging
import os

from secrets_mask import MaskServiceKeyFilter


def configure_logging(log_dir: str = "logs") -> None:
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(log_dir, "bus_api.log")),
        ],
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(MaskServiceKeyFilter())
