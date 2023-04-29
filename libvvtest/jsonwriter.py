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
        for var in (
            "platform",
            "hostname",
            "python",
        ):
            top.pop(var, None)
        top["command"] = " ".join(quote(_) for _ in top.pop("cmdline", []))
        top["starttime"] = top.pop("startepoch", -1)
        top["endtime"] = top.pop("finishepoch", -1)
        top["enddate"] = top.pop("finishdate", None)
        if top["starttime"] > 0 and top["endtime"] > 0:
            top["duration"] = top["endtime"] - top["starttime"]
        else:
            top["duration"] = -1
        top["returncode"] = top.pop("returncode",-1)
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
        resources["processors"] = len( stat.getAttr( 'processor ids' ) )
        resources["processor ids"] = stat.getAttr( 'processor ids' )
        resources["total processors"] = stat.getAttr( 'total processors' )
        resources["devices"] = None
        resources["device ids"] = None
        resources["total devices"] = None
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
