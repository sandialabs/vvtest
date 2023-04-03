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

    def __init__(self, total_num_tests, show_progress_bar):
        ""
        self.ntotal = total_num_tests
        self.ndone = 0

        self.show_progress_bar = show_progress_bar

        self.starttime = time.time()

        self._check_input = standard_in_has_data

    def printProgress(self, ndone_test):
        ""
        if ndone_test > 0:
            self.ndone += ndone_test
            self.writeProgressInfo()

    def writeInfo(self):
        ""
        now = time.time()
        total_runtime = datetime.timedelta( seconds=int(now - self.starttime) )

        logger.info( "\nInformation:" )
        logger.info( "  * Total runtime:", total_runtime )

        self.writeTestListInfo( now )

    def checkPrint(self):
        ""
        if self._check_input():
            self.writeInfo()

    def setInputChecker(self, func):
        ""
        self._check_input = func


class DirectInfoPrinter( TestInformationPrinter ):

    def __init__(self, xlist, total_num_tests, show_progress_bar=False):
        ""
        TestInformationPrinter.__init__( self, total_num_tests, show_progress_bar )
        self.xlist = xlist

    def writeProgressInfo(self):
        ""
        pct = 100 * float(self.ndone) / float(self.ntotal)
        div = str(self.ndone)+'/'+str(self.ntotal)
        dt = pretty_time( time.time() - self.starttime )
        logger.info("Progress: {0} {1:.1f}%, time = {2}".format(div, pct, dt))

        if self.show_progress_bar:
            line = progress_bar(self.ntotal, self.ndone, time.time() - self.starttime, width=30)
            logger.emit(line)

    def writeTestListInfo(self, now):
        ""
        txL = self.xlist.getRunning()
        logger.info( "  *", len(txL), "running test(s):" )

        for texec in txL:
            tcase = texec.getTestCase()
            tspec = tcase.getSpec()
            sdt = tcase.getStat().getStartDate()
            duration = datetime.timedelta( seconds=int(now-sdt) )
            xdir = tspec.getDisplayString()
            logger.info( "    *", xdir, '({0} elapsed)'.format(duration) )


class BatchInfoPrinter( TestInformationPrinter ):

    def __init__(self, tlist, batcher, show_progress_bar=False):
        ""
        TestInformationPrinter.__init__( self, tlist.numActive(), show_progress_bar )
        self.batcher = batcher

    def writeProgressInfo(self):
        ""
        ndone_batch = self.batcher.getNumDone()
        nprog_batch = self.batcher.numInProgress()
        pct = 100 * float(self.ndone) / float(self.ntotal)
        dt = time.time() - self.starttime
        fmt = "jobs running={0} completed={1}, tests {2}/{3} = {4:.1f}%, time = {5}"
        args = [nprog_batch, ndone_batch, self.ndone, self.ntotal, pct, pretty_time(dt)]
        logger.info("Progress: " + fmt.format(*args))

        if self.show_progress_bar:
            line = progress_bar(self.ntotal, self.ndone, dt, width=30)
            logger.emit(line)

    def writeTestListInfo(self, now):
        ""
        logger.info( '  *', self.batcher.numInProgress(),
                      'batch job(s) in flight:' )
        for batch_job in self.batcher.getSubmittedJobs():
            qid = batch_job.getBatchID()
            duration = now - batch_job.getStartTime()
            duration = datetime.timedelta( seconds=int(duration) )
            logger.info( '    * qbat.{0}'.format(qid),
                          '({0} since submitting)'.format(duration) )
            for tcase in batch_job.getJobObject().getTests():
                xdir = tcase.getSpec().getDisplayString()
                logger.info( '      *', xdir )


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
