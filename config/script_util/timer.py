import time
import random
import string
import datetime
import functools
from .flush_streams import flush_streams


def timer(*args):
    """
    Easy way to time things.

    Examples:

    # Time the execution of `foo()`. Automatically finds name of function.
    @timeit
    def foo():
        return "bar"

    # Time a block of code. Automatically generate a name.
    obj = timeit()
    time.sleep(1.234)
    obj.finish()

    # Time a block of code. Call it "kiwi". Access duration.
    obj = timeit("kiwi")
    time.sleep(1.234)
    obj.finish()
    print(obj.duration)

    # Time the execution of a `with` code block (random name).
    with timeit():
        time.sleep(2.345)

    # Get the duration after the `with` block
    with timeit() as myclock:
        time.sleep(2.345)
    print(myclock.duration)

    # Time the execution of a `with` code block (user-supplied name)..
    with timeit("coconut"):
        time.sleep(3.456)
    """

    class Timer:
        def __init__(self, name):

            self.datefmt = lambda x: x.strftime("%Y-%m-%dT%H%M%S.%f")[:-3]

            self.name = name
            self.t0 = datetime.datetime.now()
            self.t1 = self.t0
            self.duration = 0.0
            self.has_finished = False

            self.print_text_box(
                [
                    "Start timer '{0}'".format(self.name),
                    "Timestamp: {0}".format(self.datefmt(self.t0)),
                ]
            )

        @flush_streams
        def print_text_box(self, lines):

            box_char = "*"
            text_width = max([len(_) for _ in lines])
            box_width = text_width + 4

            top = box_char * box_width
            fmt = lambda x: " {0:<{1}s} ".format(x, text_width)
            print("")
            print(top)
            for line in lines:
                print(box_char + fmt(line) + box_char)
            print(top)
            print("")

        def finish(self):
            if self.has_finished:
                raise Exception("Timer already finished. Cannot finish again.")
            self.has_finished = True
            self.t1 = datetime.datetime.now()
            self.duration = (self.t1 - self.t0).total_seconds()

            self.print_text_box(
                [
                    "End timer '{0:s}'".format(self.name),
                    "Timestamp: {0:s}".format(self.datefmt(self.t1)),
                    "Duration: {0:.3f}s".format(self.duration),
                ]
            )

        def __enter__(self):
            return self

        def __exit__(self, _type, _value, _traceback):
            self.finish()

    if len(args) == 0:

        def _random_name(n_chars):
            """ Generate a random ASCII name """
            valid_chars = string.ascii_lowercase + string.digits
            chars = [random.choice(valid_chars) for _ in range(n_chars)]
            return "".join(chars)

        return Timer(_random_name(n_chars=4))

    elif len(args) == 1 and isinstance(args[0], str):
        return Timer(args[0])
    elif len(args) == 1 and callable(args[0]):
        func = args[0]

        @functools.wraps(func)
        def secure_func(*args, **kwargs):
            obj = Timer(func.__name__ + "()")
            outputs = func(*args, **kwargs)
            obj.finish()
            return outputs

        return secure_func
    else:
        raise Exception("Incorrectly called. Check function signature for correct use.")
