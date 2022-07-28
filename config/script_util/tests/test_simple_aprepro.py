#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import math
import pytest

from script_util.simple_aprepro import SimpleAprepro

def test_0():
    """
    Test how integers are represented.
    """
    processor = SimpleAprepro("", "")
    processor.src_txt = ["# abc = {abc = 123}", "# abc = { abc }"]
    out = processor.process()
    assert processor.dst_txt == ["# abc = 123", "# abc = 123"]
    assert out == {"abc": 123}

def test_1():
    """
    Test how floats are represented with only several digits.
    """
    processor = SimpleAprepro("", "")
    processor.src_txt = ["# abc = {abc = 123.456}", "# abc = { abc }"]
    out = processor.process()
    assert processor.dst_txt == ["# abc = 123.456", "# abc = 123.456"]
    assert out == {"abc": 123.456}

def test_2():
    """
    Test how floats are represented with machine precision.
    """
    processor = SimpleAprepro("", "")
    processor.src_txt = ["# abc = {abc = PI}", "# abc = { abc }"]
    out = processor.process()
    assert processor.dst_txt == ["# abc = 3.141592653589793",
                                 "# abc = 3.141592653589793"]
    assert out == {"abc": math.pi}

def test_3():
    """
    Test for integer division
    """
    processor = SimpleAprepro("", "")
    processor.src_txt = ["# abc = {abc = 1 / 3}"]
    out = processor.process()
    assert out == {"abc": float(1.0) / float(3.0)}  # all floats, in case you were unsure
    #                                    12345678901234567
    assert processor.dst_txt[0][:17] == "# abc = 0.3333333"

def test_4():
    """
    Test for wrong exponentiation.
    """
    processor = SimpleAprepro("", "")
    processor.src_txt = ["# abc = {abc = 2 ^ 2}"]
    try:
        out = processor.process()
    except Exception as exc:
        assert "simple_aprepro() only supports exponentiation via ** and not ^" in str(exc)





_db = {
    r"\{": "{",
    r"\}": "}",
    r"\{\{": "{{",
    r"\}\}": "}}",
    r"foo \} bar": "foo } bar",
    r"foo \{ bar": "foo { bar",
    r"foo \} bar": "foo } bar",
    r"# abc = \{abc = 1 / 3\}": "# abc = {abc = 1 / 3}",
    r"# abc = \{abc = {1 / 2}\}": "# abc = {abc = 0.5}",
    r'\{2 * 3\} * {1 / 2} * \{np\}': "{2 * 3} * 0.5 * {np}",
    "{1 == 1}": "True",
    "{var = 1 == 1}": "True",
    "{'ON' if True else 'OFF'}": "ON",
    "{'' if True else 'foo'}": "",
    '# PRODUCT_SETS = {PRODUCT_SETS = "+0, +0, =1"}': "# PRODUCT_SETS = +0, +0, =1",
}
@pytest.mark.parametrize("db", _db.items())
def test_5(db):
    """
    Test for escaped curly braces
    """
    src, dst = db

    print("\nchecking {0}".format(src))
    processor = SimpleAprepro("", "")
    processor.src_txt = [src]
    out = processor.process()
    print("out", out)
    print("dst_txt", processor.dst_txt)
    #assert out == {}
    assert processor.dst_txt[0] == dst
    print("  PASS")
