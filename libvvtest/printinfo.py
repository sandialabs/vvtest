#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time
import datetime
import select
import platform

not_windows = not platform.uname()[0].lower().startswith('win')


class TestInformationPrinter:

    def __init__(self, outfile, xlist, batcher=None):
        ""
        self.outfile = outfile
        self.xlist = xlist
        self.batcher = batcher

        self.starttime = time.time()

        self._check_input = standard_in_has_data

    def checkPrint(self):
        ""
        if self._check_input():
            self.writeInfo()

    def writeInfo(self):
        ""
        now = time.time()
        total_runtime = datetime.timedelta( seconds=int(now - self.starttime) )

        self.println( "\nInformation:" )
        self.println( "  * Total runtime:", total_runtime )

        if self.batcher == None:
            self.writeTestListInfo( now )
        else:
            self.writeBatchListInfo( now )

    def writeTestListInfo(self, now):
        ""
        txL = self.xlist.getRunning()
        self.println( "  *", len(txL), "running test(s):" )

        for texec in txL:
            tcase = texec.getTestCase()
            tspec = tcase.getSpec()
            sdt = tcase.getStat().getStartDate()
            duration = datetime.timedelta( seconds=int(now-sdt) )
            xdir = tspec.getDisplayString()
            self.println( "    *", xdir,
                          '({0} elapsed)'.format(duration) )

    def writeBatchListInfo(self, now):
        ""
        self.println( '  *', self.batcher.numInProgress(),
                      'batch job(s) in flight:' )
        for batch_job in self.batcher.getSubmittedJobs():
            qid = batch_job.getBatchID()
            duration = now - batch_job.getStartTime()
            duration = datetime.timedelta( seconds=int(duration) )
            self.println( '    * qbat.{0}'.format(qid),
                          '({0} since submitting)'.format(duration) )
            for tcase in batch_job.getJobObject().getTests():
                xdir = tcase.getSpec().getDisplayString()
                self.println( '      *', xdir )

    def println(self, *args):
        ""
        s = ' '.join( [ str(arg) for arg in args ] )
        self.outfile.write( s + '\n' )

    def setInputChecker(self, func):
        ""
        self._check_input = func


def standard_in_has_data():
    ""
    if not_windows and sys.stdin and sys.stdin.isatty():
        if select.select( [sys.stdin,], [], [], 0.0 )[0]:
            sys.stdin.readline()
            return True

    return False
