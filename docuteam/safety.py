# safety.py -- the kill switch
from config import STOP_FILE


def should_stop():
    # Create a FILE named STOP in the project folder to halt every loop; delete it to resume.
    # is_file() (not exists()) so an accidental STOP *folder* cannot trip the switch.
    return STOP_FILE.is_file()
