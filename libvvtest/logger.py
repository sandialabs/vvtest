
# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys

TRACE    = 50
DEBUG    = 40
INFO     = 30
QUIET    = 25
WARN     = 20
ERROR    = 10
CRITICAL =  0

_level = INFO


def set_level(arg):
    global _level
    assert arg in (TRACE, DEBUG, INFO, QUIET, WARN, ERROR)
    _level = arg


def get_level():
    return _level


def flush(file=None):
    file = file or sys.stdout
    file.flush()


def emit(*args, **kwargs):
    pre = kwargs.get("pre", "")
    end = kwargs.get("end", "")
    file = kwargs.get("file", sys.stdout)
    message = " ".join(str(_) for _ in args)
    file.write("{0}{1}{2}".format(pre, message, end))
    file.flush()


def trace(*args, **kwargs):
    if _level >= TRACE:
        kwargs["end"] = kwargs.pop("end", "\n")
        emit(*args, **kwargs)


def debug(*args, **kwargs):
    if _level >= DEBUG:
        kwargs["end"] = kwargs.pop("end", "\n")
        emit(*args, **kwargs)


def info(*args, **kwargs):
    if _level >= QUIET:
        kwargs["end"] = kwargs.pop("end", "\n")
        emit(*args, **kwargs)


def xinfo(*args, **kwargs):
    """
    execution loop information; issued from within a test execution loop
    (as opposed to before the loop starts or after it finishes)
    """
    if _level >= INFO:
        kwargs["end"] = kwargs.pop("end", "\n")
        emit(*args, **kwargs)


def warn(*args, **kwargs):
    if _level >= WARN:
        kwargs["file"] = sys.stderr
        kwargs["pre"] = "*** Warning: "
        kwargs["end"] = kwargs.pop("end", "\n")
        emit(*args, **kwargs)


def error(*args, **kwargs):
    if _level >= ERROR:
        kwargs["file"] = sys.stderr
        kwargs["pre"] = "*** Error: "
        kwargs["end"] = kwargs.pop("end", "\n")
        emit(*args, **kwargs)


def critical(*args, **kwargs):
    if _level >= CRITICAL:
        kwargs["file"] = sys.stderr
        kwargs["pre"] = "*** Error: "
        kwargs["end"] = kwargs.pop("end", "\n")
        emit(*args, **kwargs)


def die(*args, **kwargs):
    critical(*args, **kwargs)
    sys.exit(1)
