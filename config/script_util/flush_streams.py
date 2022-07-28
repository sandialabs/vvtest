import os
import sys
import functools


def flush_streams(*args):
    """
    Easy way to flush stdout and stderr streams

    Examples:

    # Flush the streams before and after running foo().
    @flush_streams
    def foo():
        return "bar"

    # Flush streams as a single line of code.
    flush_streams()

    # flush streams before and after running a block of code.
    with flush_streams():
        time.sleep(2.345)
    """
    chatty = os.environ.get("FLUSH_STREAMS_CHATTY", "") != ""

    class FlushStreams:
        def __init__(self):
            if chatty:
                print("FlushStreams.__init__()")
            self.flush()

        def flush(self):
            if chatty:
                print("FlushStreams.flush()")
            sys.stdout.flush()
            sys.stderr.flush()

        def __enter__(self):
            if chatty:
                print("FlushStreams.__enter__()")
            return self

        def __exit__(self, _type, _value, _traceback):
            if chatty:
                print("FlushStreams.__exit__()")
            self.flush()

    if len(args) == 0:
        return FlushStreams()

    elif len(args) == 1 and callable(args[0]):
        func = args[0]

        @functools.wraps(func)
        def secure_func(*args, **kwargs):
            obj = FlushStreams()
            outputs = func(*args, **kwargs)
            obj.flush()
            return outputs

        return secure_func
    else:
        raise Exception("Incorrectly called. Check function signature for correct use.")
