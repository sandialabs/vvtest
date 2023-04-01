#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import base64
import json
import os
import sys
import zlib

from . import outpututils

print3 = outpututils.print3


class JsonWriter:
    """Write test results to a json database.  The schema for the database is

    "vvtest": {
      "meta": {
        "hostname" str,
        "curdir": str,
        "python": str,
        "PYTHONPATH": str,
        "PATH": str,
        "LOADEDMODULES": str,
        "cmdline": list[str],
        "vvtestdir": str,
        "platforma": str,
        "system": str,
        "compiler": str,
        "rundir": str,
        "starttime": float,
        "startdate": str,
        "endtime": float,
        "enddate": str,
        "duration": float
      },
      "tests": {
        "tests": int,
        "pass": int,
        "notdone": int,
        "notrun": int,
        "diff": int,
        "fail": int,
        "timeout": int
        "cases": [
          {
            "name": str,
            "case": str,
            "root": str,
            "path": str,
            "command": str,
            "keywords": list[str],
            "processors": int,
            "starttime": float,
            "endtime": float,
            timeout: int,
            "returncode": int,
            "result": str,
            "log": str
          }
        ]
      }
    """

    def __init__(self, permsetter, output_filename, results_test_dir):
        """"""
        self.permsetter = permsetter
        self.filename = os.path.normpath(os.path.abspath(output_filename))
        self.testdir = results_test_dir
        self.datestamp = None

    def setOutputDate(self, datestamp):
        """"""
        self.datestamp = datestamp

    def prerun(self, atestlist, rtinfo, verbosity):
        """"""
        pass

    def midrun(self, atestlist, rtinfo):
        """"""
        pass

    def postrun(self, atestlist, rtinfo):
        """"""
        self.writeFile(atestlist, rtinfo)

    def info(self, atestlist, rtinfo):
        """"""
        self.writeFile(atestlist, rtinfo)

    def writeFile(self, atestlist, rtinfo):
        """
        This collects information from the given test list (a python list of
        TestExec objects), then writes a file in json format

        """
        meta = rtinfo.asDict()
        meta["starttime"] = meta.pop("startepoch", -1)
        meta["endtime"] = meta.pop("finishepoch", -1)
        meta["enddate"] = meta.pop("finishdate", None)
        if meta["starttime"] > 0 and meta["endtime"] > 0:
            meta["duration"] = meta["endtime"] - meta["starttime"]
        else:
            meta["duration"] = -1
        meta["system"] = os.getenv("SNLSYSTEM", sys.platform)
        data = {"meta": meta}
        testcases = atestlist.getActiveTests()
        print3(
            "Writing {0}, tests to Json file {1}".format(len(testcases), self.filename)
        )
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
        logfile = outpututils.get_log_file_path(self.testdir, spec)
        result = stat.getResultStatus()
        notrun = result in ("notrun", "skip", "notdone")
        if notrun:
            command = compressed_log = None
        else:
            command = outpututils.get_test_command_line(logfile)
            kb_to_keep = 2 if result == "passed" else 300
            compressed_log = self.compress_logfile(logfile, kb_to_keep)
        skip = bool(stat.skipTest())
        parameters = spec.getParameters()
        processors = int(parameters.get("np", 1))
        starttime = stat.getStartDate(None) or -1
        duration = stat.getRuntime(None) or -1
        endtime = -1 if (starttime < 0 or duration < 0) else starttime + duration
        test = {
            "name": spec.getName(),
            "case": os.path.basename(spec.getDisplayString()),
            "root": spec.getRootpath(),
            "path": spec.getFilepath(),
            "command": command,
            "keywords": spec.getKeywords(include_implicit=False),
            "processors": processors,
            "starttime": starttime,
            "endtime": endtime,
            "returncode": stat.getAttr("xvalue", None),
            "result": result,
            "log": compressed_log,
            "timeout": stat.getAttr("timeout", None),
        }
        if skip:
            test["skip"] = True
            test["skip_reason"] = stat.getReasonForSkipTest()
        return test

    @staticmethod
    def compress_logfile(logfile, kb_to_keep):
        if logfile is None or not os.path.exists(logfile):
            log = "Log file {0} not found!".format(logfile)
        else:
            log = open(logfile, errors="ignore").read()
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
