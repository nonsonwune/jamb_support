# logger.py
import logging
import json
from datetime import datetime


class StructuredLogger:
    def __init__(self, name):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def _log(self, level, message, **kwargs):
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            **kwargs,
        }
        self.logger.log(getattr(logging, level), json.dumps(log_data))

    def info(self, message, **kwargs):
        self._log("INFO", message, **kwargs)

    def warning(self, message, **kwargs):
        self._log("WARNING", message, **kwargs)

    def error(self, message, **kwargs):
        self._log("ERROR", message, **kwargs)

    def debug(self, message, **kwargs):
        self._log("DEBUG", message, **kwargs)


# Create a global instance of StructuredLogger
logger = StructuredLogger(__name__)
