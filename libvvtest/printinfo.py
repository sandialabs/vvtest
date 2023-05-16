#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

from __future__ import division

import os, sys
import time
import datetime
import select
import platform

from . import logger
from .outpututils import pretty_time, XstatusString
from . import pathutil

not_windows = not platform.uname()[0].lower().startswith('win')


class TestInformationPrinter:

    def __init__(self, test_dir, total_num_tests):
        ""
        self.test_dir = test_dir
        self.ntotal = total_num_tests
        self.ndone = 0

        self.starttime = time.time()

        self._check_input = standard_in_has_data

        self.cwd = os.getcwd()

    def printFinished(self, done_list):
        ""
        for tcase in done_list:
            ts = XstatusString( tcase, self.test_dir, self.cwd )
            logger.xinfo("Finished: {0}".format(ts))

    def printProgress(self, ndone_test):
        ""
        if ndone_test > 0:
            self.ndone += ndone_test

            self.writeProgressInfo()
            self.writeProgressBar()

    def checkPrint(self):
        ""
        if self._check_input():
            self.writeInfo()
            self.writeProgressBar()

    def writeProgressBar(self):
        ""
        if logger.get_level() <= logger.QUIET:
            print_progress_bar(self.ntotal, self.ndone, time.time()-self.starttime, width=30)

    def writeInfo(self):
        ""
        now = time.time()
        total_runtime = datetime.timedelta( seconds=int(now - self.starttime) )

        logger.emit( "\nInformation:", end='\n' )
        logger.emit( "  * Total runtime:", total_runtime, end='\n' )

        self.writeTestListInfo( now )

    def setInputChecker(self, func):
        ""
        self._check_input = func


class DirectInfoPrinter( TestInformationPrinter ):

    def __init__(self, test_dir, xlist, total_num_tests):
        ""
        TestInformationPrinter.__init__( self, test_dir, total_num_tests )
        self.xlist = xlist

    def printStarting(self, tcase):
        ""
        logger.xinfo('Starting: {0}'.format(exec_path( tcase, self.test_dir)))

    def writeProgressInfo(self):
        ""
        pct = 100 * float(self.ndone) / float(self.ntotal)
        div = str(self.ndone)+'/'+str(self.ntotal)
        dt = pretty_time( time.time()-self.starttime )
        logger.xinfo("Progress: {0} {1:.1f}%, time = {2}".format(div, pct, dt))

    def writeTestListInfo(self, now):
        ""
        txL = self.xlist.getRunning()
        logger.emit( "  *", len(txL), "running test(s):", end='\n' )

        for texec in txL:
            tcase = texec.getTestCase()
            tspec = tcase.getSpec()
            sdt = tcase.getStat().getStartDate()
            duration = datetime.timedelta( seconds=int(now-sdt) )
            xdir = tspec.getDisplayString()
            logger.emit( "    *", xdir, '({0} elapsed)'.format(duration), end='\n' )

    def printRemainders(self, not_run_list):
        ""
        if len(not_run_list) > 0:
            logger.emit("\n")
        print_notrun_reasons( [ (tc,tc.getBlockedReason()) for tc in not_run_list ] )


class BatchInfoPrinter( TestInformationPrinter ):

    def __init__(self, test_dir, tlist, batcher):
        ""
        TestInformationPrinter.__init__( self, test_dir, tlist.numActive() )
        self.batcher = batcher

    def writeProgressInfo(self):
        ""
        dt = time.time() - self.starttime
        ndone_batch = self.batcher.getNumDone()
        nprog_batch = self.batcher.numInProgress()
        pct = 100 * float(self.ndone) / float(self.ntotal)
        fmt = "jobs running={0} completed={1}, tests {2}/{3} = {4:.1f}%, time = {5}"
        args = [nprog_batch, ndone_batch, self.ndone, self.ntotal, pct, pretty_time(dt)]
        logger.xinfo("Progress: " + fmt.format(*args))

    def printFinishedBatches(self, qidL):
        ""
        if len(qidL) > 0:
            ids = ' '.join( [ str(qid) for qid in qidL ] )
            logger.xinfo('Finished batch IDS: {0}'.format(ids))

    def writeTestListInfo(self, now):
        ""
        logger.emit( '  *', self.batcher.numInProgress(),
                     'batch job(s) in flight:', end='\n' )
        for batch_job in self.batcher.getSubmittedJobs():
            qid = batch_job.getBatchID()
            duration = now - batch_job.getStartTime()
            duration = datetime.timedelta( seconds=int(duration) )
            logger.emit( '    * qbat.{0}'.format(qid),
                         '({0} since submitting)'.format(duration), end='\n' )
            for tcase in batch_job.getJobObject().getTests():
                xdir = tcase.getSpec().getDisplayString()
                logger.emit( '      *', xdir, end='\n' )

    def printBatchRemainders(self, jobstats, notrun_list):
        ""
        nostart = jobstats.get('notrun',[])
        nofinish = jobstats.get('notdone',[])
        failed = jobstats.get('fail',[])
        if len(nostart)+len(nofinish)+len(failed) > 0:
            logger.emit("\n")

        if len(nostart) > 0:
            logger.warn(
                "these batch numbers did not seem to start: {0}".format(' '.join(nostart))
            )

        if len(nofinish) > 0:
            logger.warn(
                "these batch numbers did not seem to finish: {0}".format(' '.join(nofinish))
            )

        if len(failed) > 0:
            logger.warn(
                "these batch numbers seemed to fail: {0}".format(' '.join(failed))
            )

        print_notrun_reasons( notrun_list )


def standard_in_has_data():
    ""
    if not_windows and sys.stdin and sys.stdin.isatty():
        if select.select( [sys.stdin,], [], [], 0.0 )[0]:
            sys.stdin.readline()
            return True

    return False


def exec_path( tcase, test_dir ):
    ""
    xdir = tcase.getSpec().getDisplayString()
    return pathutil.relative_execute_directory( xdir, test_dir, os.getcwd() )


def unicode_chars_supported(*uchars):
    ""
    try:
        if sys.stdout.encoding:
            [_.encode(sys.stdout.encoding) for _ in uchars]
        else:
            [_.encode() for _ in uchars]
        return True
    except UnicodeEncodeError:
        return False


if sys.version_info[0] < 3:
    _progress_bar_charset = [" ", unichr(0x2588), unichr(0x2591), ""]
else:
    _progress_bar_charset = [" ", chr(0x2588), chr(0x2591), ""]

if not unicode_chars_supported(*_progress_bar_charset):
    _progress_bar_charset = ["|", "#", "-", "|"]


def progress_bar(total, complete, width):
    ""
    lbar, bar, xbar, rbar = _progress_bar_charset
    frac = complete / total
    nbar = int(frac * width)
    bars = bar * nbar
    if nbar < width:
        bars += xbar * (width - nbar)
    return lbar+bars+rbar


def print_progress_bar(num_test, num_done, duration, width=30):
    ""
    bar = progress_bar( num_test, num_done, width )
    pct = 100 * num_done / float(num_test)
    ave = None if not num_done else duration / num_done
    togo = None if ave is None else ave * (num_test - num_done)
    w = len(str(num_test))
    line = " {0:{6}d}/{1} {2:5.1f}% [elapsed: {3} left: {4} ave: {5}]   ".format(
        num_done, num_test, pct, hhmmss(duration), hhmmss(togo), hhmmss(ave), w
    )
    sys.stdout.write( '\r'+bar+line )
    sys.stdout.flush()


def hhmmss(arg):
    if arg is None:
        return "--:--:--"
    seconds = int(arg)
    minutes = seconds // 60
    hours = minutes // 60
    return "%02d:%02d:%02d" % (hours, minutes % 60, seconds % 60)


def print_notrun_reasons( notrunlist ):
    ""
    for tcase,reason in notrunlist:
        xdir = tcase.getSpec().getDisplayString()
        logger.warn("test {0!r} notrun due to dependency: {1}".format(xdir, reason))
