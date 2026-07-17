"""Background payment watcher (run under pm2). Polls the Celo chain for cUSD
transfers matching open invoices and settles + notifies both parties."""

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import POLL_INTERVAL_SECONDS  # noqa: E402
from app.db import get_session, init_db  # noqa: E402
from app.payments import poll_open_invoices  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s poller %(levelname)s %(message)s")
log = logging.getLogger("poller")


def main() -> None:
    init_db()
    log.info("Payment poller started (every %ss)", POLL_INTERVAL_SECONDS)
    while True:
        try:
            with get_session() as db:
                settled = poll_open_invoices(db)
            if settled:
                log.info("Settled %d invoice(s) this cycle", settled)
        except Exception:
            log.exception("Poll cycle failed")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
