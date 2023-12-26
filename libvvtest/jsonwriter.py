#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import base64
import json
import os
import sys
import zlib
import io
import time

try:
    from shlex import quote
except Exception:
    from pipes import quote

from . import outpututils


class JsonWriter:
    """Write test results to a json database.

    See tested schema in tests/results_json for the promised output schema.

    """

    def __init__(self, permsetter):
        """"""
        self.permsetter = permsetter

    def initialize(self, rtinfo, output_filename, datestamp):
        """"""
        self.rtinfo = rtinfo
        self.filename = os.path.normpath(os.path.abspath(output_filename))

    def postrun(self, atestlist):
        """"""
        self.writeFile(atestlist)

    def info(self, atestlist):
        """"""
        self.writeFile(atestlist)

    def writeFile(self, atestlist):
        """
        This collects information from the given test list (a python list of
        TestExec objects), then writes a file in json format
        """
        data = {}
        top = dict( self.rtinfo )
        top["vvplatform"] = top.pop( "platform", None )
        top.pop( "hostname", None )
        top.pop( "python", None )
        top["command"] = " ".join(quote(_) for _ in top.pop("cmdline", []))
        tm = atestlist.getResultsDate()
        top["starttime"] = -1 if tm is None else tm
        tm = atestlist.getFinishDate()
        top["endtime"] = -1 if tm is None else tm
        top["enddate"] = None if tm is None else time.ctime(tm)
        if top["starttime"] > 0 and top["endtime"] > 0:
            top["duration"] = top["endtime"] - top["starttime"]
        else:
            top["duration"] = -1.0
        x = atestlist.getFinishCode()
        top["returncode"] = -1 if x is None else x
        data.update(top)

        data["onopts"] = ' '.join( self.rtinfo["onopts"] )
        data["offopts"] = ' '.join( self.rtinfo["offopts"] )
        data["testargs"] = ' '.join( self.rtinfo["testargs"] )

        uname = os.uname()
        data["machine"] = {
            "platform": sys.platform,
            "system": uname[0],
            "nodename": uname[1],
            "release": uname[2],
            "version": uname[3],
            "arch": uname[4],
        }

        data["python"] = {
            "executable": sys.executable,
            "version": sys.version,
            "version info": list(sys.version_info),
        }

        data["environment"] = os.environ.copy()

        testcases = atestlist.getActiveTests()
        print("Writing {0}, tests to {1}".format(len(testcases), self.filename))
        counts = self.count_results(testcases)
        data["tests"] = {
            "tests": len(testcases),
            "pass": counts.get("pass", 0),
            "notdone": counts.get("notdone", 0),
            "notrun": counts.get("notrun", 0),
            "diff": counts.get("diff", 0),
            "fail": counts.get("fail", 0),
            "timeout": counts.get("timeout", 0),
        }
        cases = data["tests"].setdefault("cases", [])
        for testcase in testcases:
            case = self.testcase2dict(testcase)
            cases.append(case)

        with open(self.filename, "w") as fh:
            json.dump({"vvtest": data}, fh, indent=2)

        self.permsetter.apply(self.filename)

    def count_results(self, testcases):
        counts = {}
        for testcase in testcases:
            if testcase.getStat().skipTest():
                counts["skip"] = counts.get("skip", 0) + 1
            else:
                result = testcase.getStat().getResultStatus()
                counts[result] = counts.get(result, 0) + 1
        return counts

    def testcase2dict(self, testcase):
        """Convert the testcase to a dictionary"""
        spec = testcase.getSpec()
        stat = testcase.getStat()
        logfile = outpututils.get_log_file_path(self.rtinfo['rundir'], spec)
        result = stat.getResultStatus()
        skip = bool(stat.skipTest())
        starttime = stat.getStartDate(None) or -1
        duration = stat.getRuntime(None) or -1
        endtime = -1 if (starttime < 0 or duration < 0) else starttime + duration
        test = {
            "name": spec.getName(),
            "case": os.path.basename(spec.getDisplayString()),
            "id": spec.getTestID().computeMatchString(),
            "root": spec.getRootpath(),
            "path": spec.getFilepath(),
            "keywords": spec.getKeywords(include_implicit=False),
            "parameters": spec.getParameters(typed=True),
            "starttime": starttime,
            "endtime": endtime,
            "returncode": stat.getAttr("xvalue", None),
            "result": result,
            "timeout": stat.getAttr("timeout", None),
        }
        if spec.isAnalyze():
            p = spec.getParameterSet().getParameters(typed=True, serializable=True)
            test["parameter set"] = p

        resources = test.setdefault("resources", {})
        resources["processors"] = None
        resources["processor ids"] = None
        resources["total processors"] = None
        resources["devices"] = None
        resources["device ids"] = None
        resources["total devices"] = None
        if stat.getAttr( 'processor ids', None ):
            resources["processors"] = len( stat.getAttr( 'processor ids' ) )
            resources["processor ids"] = stat.getAttr( 'processor ids' )
            resources["total processors"] = stat.getAttr( 'total processors' )
        if stat.getAttr( 'device ids', None ):
            resources["device"] = len( stat.getAttr( 'device ids' ) )
            resources["device ids"] = stat.getAttr( 'device ids' )
            resources["total devices"] = stat.getAttr( 'total devices' )

        if skip:
            test["skip"] = True
            test["skip_reason"] = stat.getReasonForSkipTest()
        notrun = result in ("notrun", "skip", "notdone")
        if notrun:
            command = compressed_log = None
        else:
            command = outpututils.get_test_command_line(logfile)
            kb_to_keep = 2 if result == "passed" else 300
            compressed_log = self.compress_logfile(spec.getName(), logfile, kb_to_keep)
        test["command"] = command
        test["log"] = compressed_log
        user_file = os.path.join(os.path.dirname(logfile), "test-out.json")
        if os.path.exists(user_file):
            test["additional data"] = json.load(open(user_file))
        return test

    @staticmethod
    def compress_logfile(name, logfile, kb_to_keep):
        if logfile is None:
            log = "No log file found!"
        elif not os.path.exists(logfile):
            log = "Log file {0} not found!".format(logfile)
        else:
            log = io.open(logfile, errors="ignore").read()
        kb = 1024
        bytes_to_keep = kb_to_keep * kb
        if len(log) > bytes_to_keep:
            rule = "=" * 100 + "\n"
            msg = "\n\n{0}{0}Output truncated to {1} kb\n{0}{0}\n".format(
                rule, kb_to_keep
            )
            log = log[:kb] + msg + log[-(bytes_to_keep - kb) :]
        return compress64(log)


def compress64(string):
    compressed = zlib.compress(string.encode("utf-8"))
    return base64.b64encode(compressed).decode("utf-8")


json_output_schema = \
{
    "vvtest": {
        "curdir": str,
        "startdate": str,
        "command": str,
        "vvtestdir": str,
        "vvplatform": str,  # the vvtest platform name
        "compiler": (None, str),  # None or a string
        "rundir": str,
        "starttime": (int,float),  # a number
        "endtime": (int,float),
        "enddate": (None, str),
        "duration": float,
        "returncode": int,
        "onopts": str,
        "offopts": str,
        "testargs": str,
        "machine": {
            "platform": str,
            "system": str,
            "nodename": str,
            "release": str,
            "version": str,
            "arch": str,
        },
        "python": {
            "executable": str,
            "version": str,
            "version info": list,
        },
        "environment": dict,
        "tests": {
            "tests": int,  # number of test cases
            "pass": int,
            "notdone": int,
            "notrun": int,
            "diff": int,
            "fail": int,
            "timeout": int,
            "cases": [
                {
                    "name": str,
                    "case": str,
                    "id": str,
                    "root": str,
                    "path": str,
                    "keywords": [str,],  # a list of strings
                    "parameters": dict,  # must be { "name":value, ...}
                    "starttime": (int,float),
                    "endtime": (int,float),
                    "returncode": (None,int),
                    "result": str,
                    "timeout": int,
                    "resources": {
                        "processors": (None, int),  # num processors
                        "processor ids": (None, [int,]),  # a list of int
                        "total processors": (None, int),
                        "devices": (None, int),  # num devices
                        "device ids": (None, [int,]),  # None or a list of int
                        "total devices": (None, int),
                    },
                    "command": (None, str),
                    "log": (None, str),  # None or a b64 encoded zlib compressed string
                },
            ],
        },
    }
}


def assert_schema_conformance( obj ):
    """
    Used in unit tests to check that the json output complies with the expected
    schema. The schema is defined in a dict just above and uses a special (home
    grown) format.
    """
    _assert_schema( json_output_schema, obj )


def _assert_schema( schema, obj, info='' ):
    ""
    if isinstance(schema,dict):
        assert type(obj) == dict, 'expected a dict, not '+str(obj)+info
        for n,v in schema.items():
            assert n in obj, 'missing name, '+repr(n)+', in object: '+str(obj)+info
            _assert_schema( v, obj[n], ', parent dict entry '+repr(n) )
    elif isinstance(schema,list):
        assert type(obj) == list, 'expected a list, not: '+str(obj)+info
        assert len(schema) == 1, "a schema list must have a single entry: "+str(schema)
        for v in obj:
            _assert_schema( schema[0], v, ', from parent list' )
    elif isinstance(schema,tuple):
        # schema indicates a set of possible types
        if obj is None:
            assert None in schema, "None value not allowed here; should be one of "+str(schema)+info
        elif type(obj) not in schema:
            subtype = _get_schema_subtype( obj, schema )
            assert subtype is not None, "unexpected object type ("+str(type(obj)) + \
                                        ") types="+str(schema)+info
            _assert_schema( subtype, obj )
    else:
        assert type(obj) == schema, 'expected type '+str(schema)+' for object: '+str(obj)+info


def _get_schema_subtype( obj, schema_types ):
    ""
    for st in schema_types:
        if type(obj) == type(st):
            return st
    return None
