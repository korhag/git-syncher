from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

_LOG_PATH = r"C:\Users\Derya\PARA\02_Areas\Workshop\git-syncher\debug-ca3fb9.log"


# ------------------------------------------------------------
# Function: agentLog
# Purpose: Append one NDJSON debug line for session ca3fb9.
# ------------------------------------------------------------
def agentLog(
    hypothesis_id: str,
    location: str,
    message: str,
    data: Optional[dict[str, Any]] = None,
) -> None:
    rec = {
        "sessionId": "ca3fb9",
        "timestamp": int(time.time() * 1000),
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "pid": os.getpid(),
    }
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(rec) + "\n")
    except OSError:
        pass
