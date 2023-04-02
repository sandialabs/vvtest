#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time
import datetime
import select
import platform

from . import logger
from .outpututils import pretty_time

not_windows = not platform.uname()[0].lower().startswith('win')


class TestInformationPrinter:

    def __init__(self, outfile, xlist, show_progress_bar=False, batcher=None):
        ""
        self.outfile = outfile
        self.xlist = xlist
        self.batcher = batcher
        self.show_progress_bar = show_progress_bar

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

        if self.batcher is None:
            self.writeTestListInfo( now )
        else:
            self.writeBatchListInfo( now )

    def printProgress(self, ntotal):
        ""
        ndone = self.xlist.numDone()
        pct = 100 * float(ndone) / float(ntotal)
        div = str(ndone)+'/'+str(ntotal)
        dt = pretty_time( time.time() - self.starttime )
        logger.info("Progress: {0} {1:.1f}%, time = {2}".format(div, pct, dt))
        if self.show_progress_bar:
            line = progress_bar(ntotal, ndone, time.time() - self.starttime, width=30)
            logger.emit(line)

    def printBatchProgress(self, ndone_test):
        ""
        ndone_batch = self.batcher.getNumDone()
        nprog_batch = self.batcher.numInProgress()
        ntot_test = self.xlist.numActive()
        pct = 100 * float(ndone_test) / float(ntot_test)
        dt = time.time() - self.starttime
        fmt = "jobs running={0} completed={1}, tests {2}/{3} = {4:.1f}%, time = {5}"
        args = [nprog_batch, ndone_batch, ndone_test, ntot_test, pct, pretty_time(dt)]
        logger.info("Progress: " + fmt.format(*args))
        if self.show_progress_bar:
            line = progress_bar(ntot_test, ndone_test, dt, width=30)
            logger.emit(line)


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


def progress_bar(num_test, num_done, duration, width=30):
    bar = logger.progress_bar(num_test, num_done, width)
    pct = 100 * num_done / float(num_test)
    ave = None if not num_done else duration / num_done
    togo = None if ave is None else ave * (num_test - num_done)
    w = len(str(num_test))
    line = "\r{0} {1:{7}d}/{2} {3:5.1f}% [elapsed: {4} left: {5} ave: {6}]   ".format(
        bar, num_done, num_test, pct, hhmmss(duration), hhmmss(togo), hhmmss(ave), w
    )
    return line


def hhmmss(arg):
    if arg is None:
        return "--:--:--"
    seconds = int(arg)
    minutes = seconds // 60
    hours = minutes // 60
    return "%02d:%02d:%02d" % (hours, minutes % 60, seconds % 60)
