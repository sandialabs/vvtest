#!/usr/bin/env python
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import time
import pytest

import script_util as su

fs_tolerance = 0.05
short_duration = 0.567
long_duration = 12.345
test_name = "spam"

# fmt: off
_db = [
    # Short
    {"target": "freestyle", "test_name": "",        "expected_duration": short_duration},
    {"target": "freestyle", "test_name": test_name, "expected_duration": short_duration},
    {"target": "context",   "test_name": "",        "expected_duration": short_duration},
    {"target": "context",   "test_name": test_name, "expected_duration": short_duration},
    {"target": "decorator", "test_name": "",        "expected_duration": short_duration},
    # Long
    {"target": "freestyle", "test_name": "",        "expected_duration": long_duration},
]
# fmt: on


@pytest.mark.parametrize("db", _db)
def test_timer_context(capsys, db):
    """
    This test uses the 'Timer' class in a with statement.
    """
    import time

    target = db["target"]
    test_name = db["test_name"]
    expected_duration = db["expected_duration"]

    t0 = time.time()
    self_duration = 0.0

    if target == "freestyle":
        if test_name == "":
            obj = su.timer()
            time.sleep(expected_duration)
            obj.finish()
            self_duration = obj.duration
        else:
            obj = su.timer(test_name)
            time.sleep(expected_duration)
            obj.finish()
            self_duration = obj.duration
    elif target == "context":
        if test_name == "":
            with su.timer() as obj:
                time.sleep(expected_duration)
        else:
            with su.timer(test_name) as obj:
                time.sleep(expected_duration)
        self_duration = obj.duration
    elif target == "decorator":

        @su.timer
        def super_func():
            time.sleep(expected_duration)

        super_func()

    t1 = time.time()
    out, err = capsys.readouterr()
    print("\nstdout:\n" + out)
    print("\nstderr:\n" + err)

    # Check the duration as measured in this function.
    duration_diff = (t1 - t0) - expected_duration
    print("duration_diff", duration_diff)
    assert 0.0 < duration_diff
    assert duration_diff < fs_tolerance

    # Check the self-reported duration.
    if self_duration != 0.0:
        assert expected_duration < self_duration
        assert self_duration < expected_duration + fs_tolerance

    # Do a "warm fuzzy" check that the names we're expecting exist
    # in the instances where randomized names aren't used.
    if target == "decorator":
        assert out.count("super_func()") == 2
    else:
        if test_name != "":
            assert out.count(test_name) == 2

    # Do much stronger checks on output.
    re_check = {
        r" Start timer \'.*\' ": 1,
        r" End timer \'.*\' ": 1,
        r" Timestamp: \d\d\d\d-\d\d-\d\dT\d\d\d\d\d\d.\d\d\d ": 2,
        r" Duration: \d+\.\d\d\ds ": 1,
    }
    for pattern, count in re_check.items():
        matches = re.findall(pattern, out)
        print(pattern, matches)
        assert len(matches) == count


def test_nested_decorators_inner_timer(capsys):

    print("before def")

    @su.flush_streams
    @su.timer
    def inner_timer():
        print("spam")

    print("after def")
    print("before")
    inner_timer()
    print("after")

    out, err = capsys.readouterr()
    print("\nstdout:\n" + out)
    print("\nstderr:\n" + err)

    assert "Start timer 'inner_timer()'" in out
    assert "End timer 'inner_timer()'" in out
    assert out.startswith("before def\nafter def\nbefore\n")
    assert out.endswith("after\n")


def test_nested_decorators_outer_timer(capsys):

    print("before def")

    @su.timer
    @su.flush_streams
    def outer_timer():
        print("spam")

    print("after def")
    print("before")
    outer_timer()
    print("after")

    out, err = capsys.readouterr()
    print("\nstdout:\n" + out)
    print("\nstderr:\n" + err)

    assert "Start timer 'outer_timer()'" in out
    assert "End timer 'outer_timer()'" in out
    assert out.startswith("before def\nafter def\nbefore\n")
    assert out.endswith("after\n")
