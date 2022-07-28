#!/usr/bin/env python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import textwrap

import script_util as su

var_name = "FLUSH_STREAMS_CHATTY"
var_val = "totally"


def test_singleton(capsys):
    assert var_name not in os.environ
    os.environ[var_name] = var_val
    assert var_name in os.environ

    print("before")
    su.flush_streams()
    print("after")

    del os.environ[var_name]
    assert var_name not in os.environ

    out, err = capsys.readouterr()

    print("\nout:\n" + out)
    print("\nerr:\n" + err)

    assert out == textwrap.dedent(
        """\
        before
        FlushStreams.__init__()
        FlushStreams.flush()
        after
        """
    )
    assert err == ""


def test_context(capsys):
    assert var_name not in os.environ
    os.environ[var_name] = var_val
    assert var_name in os.environ

    print("before")
    with su.flush_streams():
        print("middle")
    print("after")

    del os.environ[var_name]
    assert var_name not in os.environ

    out, err = capsys.readouterr()

    print("\nout:\n" + out)
    print("\nerr:\n" + err)

    assert out == textwrap.dedent(
        """\
        before
        FlushStreams.__init__()
        FlushStreams.flush()
        FlushStreams.__enter__()
        middle
        FlushStreams.__exit__()
        FlushStreams.flush()
        after
        """
    )
    assert err == ""


def test_decorator(capsys):
    assert var_name not in os.environ
    os.environ[var_name] = var_val
    assert var_name in os.environ

    print("before def")

    @su.flush_streams
    def f():
        print("function")

    print("after def")

    print("before")
    f()
    print("after")

    del os.environ[var_name]
    assert var_name not in os.environ

    out, err = capsys.readouterr()

    print("\nout:\n" + out)
    print("\nerr:\n" + err)

    assert out == textwrap.dedent(
        """\
        before def
        after def
        before
        FlushStreams.__init__()
        FlushStreams.flush()
        function
        FlushStreams.flush()
        after
        """
    )
    assert err == ""
