#!/usr/bin/env python3
from __future__ import division  # Make python2 and python3 handle divisions the same.
import sys
import os
import math
import random
import re

class SimpleAprepro:
    """
    This class is a scaled-down version of Aprepro, a text preprocessor
    for mathematical expressions. It only supports the subset of
    capabilities from Aprepro that are most useful for V&V and automated
    testing. While the general behavior is the same as Aprepro, the
    replaced text is not guaranteed to be the same (e.g. the number of
    digits of printed accuracy might not be the same).

    The source of Aprepro lives in Seacas:

        https://github.com/gsjaardema/seacas

    and the documentation can be found here:

        https://gsjaardema.github.io/seacas/


    Quick Description
    -----------------

    A file can be written with mathematical expressions between curly
    braces (on a single line) and it will write a new file with those
    chunks replaced. For example:

      Input:  "I have {n_bananas = 6} bananas.
               Would you like {n_bananas / 2}?"

      Output: "I have 6 bananas.
               Would you like 3 bananas?"

    It is also able to handle simple mathematical functions like sin(),
    cos(), and sqrt().


    Inputs
    ------

    src_f        filename of the file to process
    dst_f        filename of where to write the processed file
    chatty       bool defining if messages should be written to screen
    override     dictionary of values to override or None
    immutable    bool defining if variables can be overwritten


    Outputs
    -------

    eval_locals  dictionary of variable names and values that were
                 evaluated while processing src_f.
    """

    def read_file(self, filename):

        # Make it so that files get read in relative the the file that
        # they are currently reading in.
        cwd = os.getcwd()
        if os.path.dirname(self.src_f) != "":
            os.chdir(os.path.dirname(self.src_f))

        processor = SimpleAprepro(filename, None,
                                  chatty=self.chatty,
                                  override=self.override,
                                  immutable=self.immutable)
        processor.load_file()
        processor.eval_locals.update(self.eval_locals)
        eval_locals = processor.process()
        self.eval_locals.update(eval_locals)
        os.chdir(cwd)

        return "".join(processor.dst_txt)#, eval_locals


    def __init__(self, src_f, dst_f,
                       chatty=True,
                       override=None,
                       immutable=False):
        self.src_f = src_f
        self.dst_f = dst_f
        self.chatty = chatty
        if override is None:
            self.override = {}
        else:
            self.override = override
        self.immutable = immutable
        self.src_txt = []
        self.dst_txt = []

        # These are defined here so that each time process() is called
        # it gets a new version of the locals and globals so that there
        # isn't cross-call contamination. Commented entries are present
        # in Aprepro but are not supported here.
        self.safe_globals = {
                             "abs": math.fabs,
                             "acos": math.acos,
                             #"acosd"
                             "acosh": math.acosh,
                             "asin": math.asin,
                             #"asind"
                             "asinh": math.asinh,
                             "atan": math.atan,
                             "atan2": math.atan2,
                             #"atan2d"
                             #"atand"
                             "atanh": math.atanh,
                             "ceil": math.ceil,
                             "cos": math.cos,
                             #"cosd"
                             "cosh": math.cosh,
                             "d2r": math.radians,
                             #"dim"
                             #"dist"
                             "exp": math.exp,
                             #"find_word"
                             "floor": math.floor,
                             "fmod": math.fmod,
                             "hypot": math.hypot,
                             #"int" (I think this is part of the python interpreter)
                             #"julday"
                             #"juldayhms"
                             #"lgamma"
                             "ln": math.log,
                             "log": math.log,
                             "log10": math.log10,
                             "log1p": math.log1p,
                             "max": max,
                             "min": min,
                             "nint" : round,
                             #"polarX"
                             #"polarY"
                             "r2d" : math.degrees,
                             "rand" : random.uniform,
                             "rand_lognormal" : random.lognormvariate,
                             "rand_normal" : random.normalvariate,
                             "rand_weibull" : random.weibullvariate,
                             "sign": math.copysign,
                             "sin": math.sin,
                             #"sind"
                             "sinh": math.sinh,
                             "sqrt": math.sqrt,
                             #"srand"
                             #"strtod"
                             "tan": math.tan,
                             #"tand"
                             "tanh": math.tanh,
                             #"Vangle"
                             #"Vangled"
                             #"word_count"

                             # Predefined Variables from Aprepro
                             "PI": math.pi,
                             "PI_2": 2 * math.pi,
                             "SQRT2": math.sqrt(2.0),
                             "DEG": 180.0 / math.pi,
                             "RAD": math.pi / 180.0,
                             "E": math.e,
                             "GAMMA": 0.57721566490153286060651209008240243,
                             "PHI": (math.sqrt(5.0) + 1.0) / 2.0,

                             # Predefined Variables from Aprepro
                             "include": self.read_file,
                            }
        self.eval_locals = {}


    def safe_eval(self, txt):
        """
        Evaluate the text given in 'txt'. If it has an assignment operator
        assign the value to the appropriately named key in 'eval_locals'.

        If 'immutable==True', allow values to be evaluated and stored, but
        do not allow them to be overwritten. Return the string representation
        of the computed value.
        """

        # For each call, make sure the override variables are in place.
        self.eval_locals.update(self.override)

        if "^" in txt:
            raise Exception("simple_aprepro() only supports exponentiation via **" +
                  " and not ^. As aprepro supports both, please use ** instead." + 
                  " Encountered while processing '{0}'".format(txt))

        # look for an equals sign that is not preceded or followed by
        # another equals sign.
        pattern = re.compile(r"(?<!=)=(?!=)")
        if re.search(pattern, txt):
            splitted = re.split(pattern, txt, maxsplit=1)
            if len(splitted) != 2:
                raise Exception("Unsupported syntax: {0}".format(txt))
            name, expression = [_.strip() for _ in splitted]

            if self.immutable and name in self.eval_locals.keys():
                raise Exception("Cannot change '{0}'".format(name)
                                + " because it is immutable. Context:"
                                + " '{0}'".format(txt))

            if name in self.override:
                print("* !!! override variable '{0}' cannot".format(name)
                      + " be updated. Context: '{0}'".format(txt))
            else:
                self.eval_locals[name] = eval(expression,
                                              self.safe_globals,
                                              self.eval_locals)

            val = self.eval_locals[name]
        else:
            val = eval(txt, self.safe_globals, self.eval_locals)

        if type(val) is str:
            # Python3 and non-unicode vars in python2.
            return val
        elif str(type(val)) == "<type 'unicode'>":
            # Unicode vars in python2.
            return val.encode('ascii')

        return repr(val)


    def load_file(self):
        """
        This file reads the file given by self.src_f and saves the list
        of lines to self.src_txt. It is modular so that testing can
        occur without actual files.
        """
        with open(self.src_f, 'r') as src:
            self.src_txt = src.readlines()

    def dump_file(self):
        """
        This function dumps the processed file to self.dst_f. It is
        modular so that testing can occur without actual files. If
        dst_f is 'None', do not write to disk.
        """
        if self.dst_f is None:
            return

        with open(self.dst_f, 'w') as dst:
            # line breaks should already be present
            dst.write("".join(self.dst_txt))

    def process(self):
        """
        Output
        -------

        eval_locals  dictionary of variable names and values that were
                     evaluated while processing src_txt.
        """

        if self.chatty:
            print("\n" + "*" * 72)
            print("* Calling SimpleAprepro.process()")
            print("* --- Current state")
            print("*   src_f = {0}".format(self.src_f))
            print("*   dst_f = {0}".format(self.dst_f))
            print("*   chatty = {0}".format(self.chatty))
            print("*   override = {0}".format(self.override))

        # Process the input file line-by-line
        for jdx, clean_line in enumerate(self.src_txt):

            # Process the aprepro directive blocks. Only split on curly
            # braces that are not escaped.
            split_line = re.split(r"(?<!\\)({[^{]*?})", clean_line)
            for idx, chunk in enumerate(split_line):
                if chunk.startswith("{") and chunk.endswith("}"):
                    # Found a chunk to evaluate.
                    split_line[idx] = self.safe_eval(chunk[1:-1])
            joined_line = "".join(split_line)

            # Process escaped curly braces.
            joined_line = joined_line.replace(r"\{", "{").replace(r"\}", "}")

            if self.chatty:
                print("* {0: 4d}: {1}".format(jdx, repr(joined_line)))
            self.dst_txt.append(joined_line)

        if self.chatty:
            print("* End call to SimpleAprepro.process()")
            print("*" * 72 + "\n")

        return self.eval_locals


def test0():
    """
    Test how integers are represented.
    """
    processor = SimpleAprepro("", "")
    processor.src_txt = ["# abc = {abc = 123}", "# abc = { abc }"]
    out = processor.process()
    assert processor.dst_txt == ["# abc = 123", "# abc = 123"]
    assert out == {"abc": 123}

def test1():
    """
    Test how floats are represented with only several digits.
    """
    processor = SimpleAprepro("", "")
    processor.src_txt = ["# abc = {abc = 123.456}", "# abc = { abc }"]
    out = processor.process()
    assert processor.dst_txt == ["# abc = 123.456", "# abc = 123.456"]
    assert out == {"abc": 123.456}

def test2():
    """
    Test how floats are represented with machine precision.
    """
    processor = SimpleAprepro("", "")
    processor.src_txt = ["# abc = {abc = PI}", "# abc = { abc }"]
    out = processor.process()
    assert processor.dst_txt == ["# abc = 3.141592653589793",
                                 "# abc = 3.141592653589793"]
    assert out == {"abc": math.pi}

def test3():
    """
    Test for integer division
    """
    processor = SimpleAprepro("", "")
    processor.src_txt = ["# abc = {abc = 1 / 3}"]
    out = processor.process()
    assert out == {"abc": float(1.0) / float(3.0)}  # all floats, in case you were unsure
    #                                    12345678901234567
    assert processor.dst_txt[0][:17] == "# abc = 0.3333333"

def test4():
    """
    Test for wrong exponentiation.
    """
    processor = SimpleAprepro("", "")
    processor.src_txt = ["# abc = {abc = 2 ^ 2}"]
    try:
        out = processor.process()
    except Exception as exc:
        assert "simple_aprepro() only supports exponentiation via ** and not ^" in str(exc)

def test5():
    """
    Test for escaped curly braces
    """

    cases = {
        "\{": "{",
        "\}": "}",
        "\{\{": "{{",
        "\}\}": "}}",
        "foo \} bar": "foo } bar",
        "foo \{ bar": "foo { bar",
        "foo \} bar": "foo } bar",
        "# abc = \{abc = 1 / 3\}": "# abc = {abc = 1 / 3}",
        "# abc = \{abc = {1 / 2}\}": "# abc = {abc = 0.5}",
        '\{2 * 3\} * {1 / 2} * \{np\}': "{2 * 3} * 0.5 * {np}",
        "{1 == 1}": "True",
        "{var = 1 == 1}": "True",
        "{'ON' if True else 'OFF'}": "ON",
        "{'' if True else 'foo'}": "",
        '# PRODUCT_SETS = {PRODUCT_SETS = "+0, +0, =1"}': "# PRODUCT_SETS = +0, +0, =1",
    }

    for src, dst in cases.items():
        print("\nchecking {0}".format(src))
        processor = SimpleAprepro("", "")
        processor.src_txt = [src]
        out = processor.process()
        print("out", out)
        print("dst_txt", processor.dst_txt)
        #assert out == {}
        assert processor.dst_txt[0] == dst
        print("  PASS")

def run_tests():
    test0()
    test1()
    test2()
    test3()
    test4()
    test5()

def simple_aprepro(src_f, dst_f,
                   chatty=True,
                   override=None,
                   immutable=False):
    """
    This function is a simplified interface to the SimpleAprepro class.
    It instantiates and object and calls the process() function and
    returns the dictionary of evaluted values.

    Inputs
    ------

    src_f        filename of the file to process
    dst_f        filename of where to write the processed file. If 'None'
                 return the dictionary of values and do not write to disk.
    chatty       bool defining if messages should be written to screen
    override     dictionary of values to override or None
    immutable    bool defining if variables can be overwritten


    Outputs
    -------

    eval_locals  dictionary of variable names and values that were
                 evaluated while processing src_f.
    """

    processor = SimpleAprepro(src_f, dst_f,
                              chatty=chatty,
                              override=override,
                              immutable=immutable)

    processor.load_file()
    eval_locals = processor.process()
    processor.dump_file()

    return eval_locals


def main(args):

    import argparse
    import json

    # Parse inputs
    parser = argparse.ArgumentParser("simple_aprepro.py")
    parser.add_argument('input_file', action='store',
                        help='File to be processed.')
    parser.add_argument('output_file', action='store', default=None,
                        help='File to be written.')
    parser.add_argument('--params', dest='parameters_jsonl',
           action='store', default=None,
           help='Create multiple files parameterizing from a jsonl file.')
    parser.add_argument('--chatty', dest='chatty', action='store_true', default=False,
           help='Increase verbosity [default: %(default)s]')
    args = parser.parse_args(args)

    # Check inputs
    if not os.path.isfile(args.input_file):
        sys.exit("Input file not found: {0}".format(args.input_file))

    if args.parameters_jsonl is not None:

        # Ensure that the jsonl file exists.
        if not os.path.isfile(args.parameters_jsonl):
            sys.exit("Parameter file not found: {0}".format(args.parameters_jsol))

        # Read in all the realizations.
        realizations = []
        with open(args.parameters_jsonl, 'rt') as F:
            for line in F.readlines():
                realizations.append(json.loads(line))

        # Create each file.
        base, suffix = os.path.splitext(args.output_file)
        for realization in realizations:
            sorted_items = sorted(realization.items(), key=lambda x: x[0])
            param_string = ".".join(["{0}={1}".format(key, value) for key, value in sorted_items])
            output_f = base + "." + param_string + suffix
            simple_aprepro(args.input_file, output_f, override=realization, chatty=args.chatty)
            print("Wrote {0}".format(output_f))

    else:
        # Process file
        simple_aprepro(args.input_file, args.output_file, chatty=args.chatty)


if __name__ == '__main__':
    #run_tests()
    main(sys.argv[1:])
