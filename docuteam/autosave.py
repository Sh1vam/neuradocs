# autosave.py -- timed git checkpoints (Chapter 07, Part H)
import threading
import time

from build_loop import checkpoint


def start_autosave(interval=300):
    stop = threading.Event()

    def loop():
        while not stop.wait(interval):
            checkpoint('autosave ' + time.strftime('%H:%M'))

    threading.Thread(target=loop, daemon=True).start()
    return stop                      # call stop.set() to end it
