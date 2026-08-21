import logging
import os


def configure_logging(log_dir: str = "logs") -> None:
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.ERROR,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(log_dir, "bus_api.log")),
        ],
    )
