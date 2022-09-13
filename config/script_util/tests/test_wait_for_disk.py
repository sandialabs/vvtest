#!/usr/bin/env python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import time
import threading
import pytest

import script_util as su

BIG = 1.0e99
fs_tolerance = 0.05  # seconds


def threaded_create_file(filename, wait_duration):
    """ Create a file after `wait_duration` seconds """
    assert not os.path.exists(filename)
    print("\nWill create file '{0}' in {1:.6f} seconds".format(filename, wait_duration))
    t0 = time.time()
    time.sleep(wait_duration)
    with open(filename, "w") as stream:
        stream.write("spam")
    t1 = time.time()
    print("  Done in {0:.6f} seconds\n".format(t1 - t0))
    assert os.path.exists(filename)


_db = [
    {"dt": 1.0, "timeout": 3.14, "file_wait": 2.0},
    {"dt": 1.0, "timeout": 3.14, "file_wait": 2.5},
    {"dt": 1.0, "timeout": 3.14, "file_wait": 1.9},
    {"dt": 1.0 / 3.0, "timeout": 3.14, "file_wait": 0.2},
    {"dt": 1.0 / 3.0, "timeout": 3.14, "file_wait": 0.5},
    {"dt": 1.0 / 3.0, "timeout": 3.14, "file_wait": 1.9},
    {"dt": 1.0 / 3.0, "timeout": 3.14, "file_wait": 2.1},
    {"dt": 1.0 / 3.0, "timeout": 1.90, "file_wait": 1.8},
    {"dt": 1.0 / 3.0, "timeout": 1.90, "file_wait": BIG},
    {"dt": 0.1, "timeout": 0.10, "file_wait": BIG},
]


@pytest.mark.parametrize("db", _db)
def test_wait_for_disk_special(capsys, db):
    """
    Do some tests that are hand-picked by a human
    """

    if "WAIT_FOR_DISK_SLOW" in os.environ:
        del os.environ["WAIT_FOR_DISK_SLOW"]
    assert "WAIT_FOR_DISK_SLOW" not in os.environ

    filename = "does_not_exist"
    if os.path.exists(filename):
        os.remove(filename)

    if db["file_wait"] == BIG:
        # File won't be written.
        t0 = time.time()
        with pytest.raises(FileNotFoundError) as excinfo:
            su.wait_for_disk(filename, timeout=db["timeout"], dt=db["dt"])
        t1 = time.time()
        exception_msg = excinfo.value.args[0]

        out, err = capsys.readouterr()
        print("\nstdout:\n" + out)
        print("\nstderr:\n" + err)

        measured_duration = t1 - t0
        assert measured_duration < db["timeout"] + fs_tolerance
        assert "Object not found after" in exception_msg
        assert filename in exception_msg

    else:
        # Usual usage

        x = threading.Thread(
            target=threaded_create_file, args=(filename, db["file_wait"])
        )

        t0 = time.time()
        x.start()
        su.wait_for_disk(filename, timeout=db["timeout"], dt=db["dt"])
        t1 = time.time()
        x.join()

        out, err = capsys.readouterr()
        print("\nstdout:\n" + out)
        print("\nstderr:\n" + err)

        measured_duration = t1 - t0
        print("measured_duration", measured_duration)

        assert db["file_wait"] < measured_duration
        assert measured_duration < db["file_wait"] + db["dt"] + fs_tolerance

        assert os.path.exists(filename)
        os.remove(filename)
        assert not os.path.exists(filename)


@pytest.mark.parametrize("dt", [0.1, 0.5, 1.0])
@pytest.mark.parametrize("timeout", [0.1, 0.4, 1.5])
@pytest.mark.parametrize("file_wait", [0.0, 1.0 / 3.0, 0.5, 0.9])
def test_wait_for_disk_parameterized(capsys, dt, timeout, file_wait):
    """
    Run over a bunch of parameterizations.
    """

    if "WAIT_FOR_DISK_SLOW" in os.environ:
        del os.environ["WAIT_FOR_DISK_SLOW"]
    assert "WAIT_FOR_DISK_SLOW" not in os.environ

    filename = "does_not_exist"
    if os.path.exists(filename):
        os.remove(filename)

    x = threading.Thread(target=threaded_create_file, args=(filename, file_wait))

    if file_wait >= timeout:
        t0 = time.time()
        x.start()
        with pytest.raises(FileNotFoundError) as excinfo:
            su.wait_for_disk(filename, timeout=timeout, dt=dt)
        t1 = time.time()
        x.join()
        exception_msg = excinfo.value.args[0]

        out, err = capsys.readouterr()
        print("\nstdout:\n" + out)
        print("\nstderr:\n" + err)

        measured_duration = t1 - t0
        assert measured_duration < file_wait + fs_tolerance
        assert "Object not found after" in exception_msg
        assert filename in exception_msg

    else:
        t0 = time.time()
        x.start()
        su.wait_for_disk(filename, timeout=timeout, dt=dt)
        t1 = time.time()
        x.join()

        out, err = capsys.readouterr()
        print("\nstdout:\n" + out)
        print("\nstderr:\n" + err)

        # Check the duration as measured in this function.
        measured_duration = t1 - t0
        n_dt = measured_duration / dt
        print("Outer timer: {0:.6f}s".format(measured_duration))
        print("file_wait to create file: {0:.6f}s".format(file_wait))

        # Can't find the file faster than it's made.
        assert measured_duration > file_wait

        # We expect to find it in less time than the timeout (plus some).
        assert measured_duration < timeout + fs_tolerance

        # It should be found within `dt` of creation.
        assert file_wait < measured_duration
        assert measured_duration < file_wait + dt + fs_tolerance

    assert os.path.exists(filename)
    os.remove(filename)
    assert not os.path.exists(filename)


if __name__ == "__main__":
    pytest.main(["-vv", __file__])
