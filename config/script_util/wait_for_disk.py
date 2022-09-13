import os
import math
import time as myclock


def wait_for_disk(filename, timeout=30.0, dt=1.0):
    """ This should work for link, directory, or file """
    t0 = myclock.time()
    while True:
        if os.path.exists(filename):
            return

        t1 = myclock.time()
        elapsed = t1 - t0
        remaining = timeout - elapsed
        if elapsed > timeout:
            break
        elif remaining < dt:
            sleep_duration = remaining
        else:
            sleep_duration = dt
        myclock.sleep(sleep_duration)

    raise FileNotFoundError(
        "Object not found after {0:.2f}s: {1}".format(t1 - t0, filename)
    )
