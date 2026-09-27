"""[VEGA] notifier: important events only, Ukrainian text. Reads VEGA_TG_TOKEN / VEGA_TG_CHAT from the
environment (never stored in the repo). Always appends to logs/notifications.log as well."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

from . import kernel as K


def send(text: str) -> bool:
    msg = f"[VEGA] {text}"
    log = K.VEGA_ROOT / "logs" / "notifications.log"
    log.parent.mkdir(exist_ok=True)
    with open(log, "a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ ", time.gmtime()) + msg + "\n")
    tok, chat = os.environ.get("VEGA_TG_TOKEN"), os.environ.get("VEGA_TG_CHAT")
    if not (tok and chat):
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": msg}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=20)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    print(send(" ".join(sys.argv[1:])))
