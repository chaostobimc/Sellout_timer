# Source Generated with Decompyle++
# File: config.pyc (Python 3.12)

from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
log = logging.getLogger(__name__)
Config = <NODE:12>()

def load_config(path = None):
    config_path = Path(path).expanduser().resolve()
    env_path = config_path.parent / '.env'
# WARNING: Decompyle incomplete

