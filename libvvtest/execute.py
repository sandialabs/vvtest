#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.
from __future__ import division

import os, sys
import time

from . import tty
from . import utesthooks
from . import pathutil
from .printinfo import TestInformationPrinter
from .outpututils import XstatusString, pretty_time


class TestListRunner:

    def __init__(self, test_dir, tlist, xlist, perms,
                       rtinfo, results_writer, plat,
                       total_timeout, show_progress_bar=False):
        ""
        self.test_dir = test_dir
        self.tlist = tlist
        self.xlist = xlist
        self.perms = perms
        self.rtinfo = rtinfo
        self.results_writer = results_writer
        self.plat = plat
        self.total_timeout = total_timeout
        self.show_progress_bar = show_progress_bar
        self.current_log_level = tty.get_level()

    def setup(self):
        ""
        self.starttime = time.time()
        tty.info("Start time: {0}".format(time.ctime()))

        rfile = self.tlist.initializeResultsFile( **(self.rtinfo.asDict()) )
        self.perms.apply( os.path.abspath( rfile ) )

        self.cwd = os.getcwd()

    def total_time_expired(self):
        ""
        if self.total_timeout and self.total_timeout > 0:
            if time.time() - self.starttime > self.total_timeout:
                tty.warn('\ntotal timeout expired: {0}'.format(self.total_timeout))
                return True
        return False


class BatchRunner( TestListRunner ):

    def __init__(self, test_dir, tlist, xlist, perms,
                       rtinfo, results_writer, plat,
                       total_timeout, show_progress_bar=False):
        ""
        TestListRunner.__init__( self, test_dir, tlist, xlist, perms,
                                 rtinfo, results_writer, plat, total_timeout,
                                 show_progress_bar=show_progress_bar)
        self.batch = None

    def setBatcher(self, batch):
        ""
        self.batch = batch

    def startup(self):
        ""
        self.setup()

        self.plat.display()

        self.tlist.setResultsDate()

        self.batch.clearBatchDirectories()
        self.batch.constructBatchJobs()

        self.qsleep = int( os.environ.get( 'VVTEST_BATCH_SLEEP_LENGTH', 15 ) )
        self.info = TestInformationPrinter( sys.stdout, self.tlist, self.batch )

        tty.info('Maximum concurrent batch jobs: {0}'.format(self.batch.getMaxJobs()))

    def run(self):
        ""
        self.startup()

        uthook = utesthooks.construct_unit_testing_hook( 'batch' )

        try:
            save_log_level = tty.get_level()
            if self.show_progress_bar:
                # skip any information messages so that only the progress bar is shown
                tty.set_level(tty.WARN)

            while True:

                qid = self.batch.checkstart()
                if qid is not None:
                    # nothing to print here because the qsubmit prints
                    pass
                elif self.batch.numInProgress() == 0:
                    break
                else:
                    self.sleep_with_info_check()

                qidL,doneL = self.batch.checkdone()

                self.print_finished( qidL, doneL )

                uthook.check( self.batch.numInProgress(), self.batch.numPastQueue() )

                self.results_writer.midrun( self.tlist, self.rtinfo )

                self.print_progress( doneL )

                if self.total_time_expired():
                    break

            # any remaining tests cannot be run, so flush them
            NS, NF, nrL = self.batch.flush()

        finally:
            tty.set_level(save_log_level)
            self.batch.shutdown()

        self.finishup( NS, NF, nrL )

        return encode_integer_warning( self.tlist )

    def print_finished(self, qidL, doneL):
        ""
        if len(qidL) > 0:
            ids = ' '.join( [ str(qid) for qid in qidL ] )
            tty.info('Finished batch IDS: {0}'.format(ids))
        for tcase in doneL:
            ts = XstatusString( tcase, self.test_dir, self.cwd )
            tty.info("Finished: {0}".format(ts))

    def print_progress(self, doneL):
        ""
        if len(doneL) <= 0:
            return
        ndone_batch = self.batch.getNumDone()
        nprog_batch = self.batch.numInProgress()
        ndone_test = self.xlist.numDone()
        ntot_test = self.tlist.numActive()
        pct = 100 * float(ndone_test) / float(ntot_test)
        dt = time.time() - self.starttime
        fmt = "jobs running={0} completed={1}, tests {2}/{3} = {4:.1f}%, time = {5}"
        args = [nprog_batch, ndone_batch, ndone_test, ntot_test, pct, pretty_time(dt)]
        tty.info("Progress: " + fmt.format(*args))
        if self.show_progress_bar:
            line = progress_bar(ntot_test, ndone_test, dt, width=30)
            tty.emit(line)

    def sleep_with_info_check(self):
        ""
        for i in range( int( self.qsleep + 0.5 ) ):
            self.info.checkPrint()
            time.sleep( 1 )

    def finishup(self, NS, NF, nrL):
        ""
        if len(NS)+len(NF)+len(nrL) > 0:
            tty.emit("\n")
        if len(NS) > 0:
            tty.warn(
                "these batch numbers did not seem to start: {0}".format(' '.join(NS))
            )
        if len(NF) > 0:
            tty.warn(
                "these batch numbers did not seem to finish: {0}".format(' '.join(NF))
            )

        print_notrun_reasons( nrL )


class DirectRunner( TestListRunner ):

    def __init__(self, test_dir, tlist, xlist, perms,
                       rtinfo, results_writer, plat,
                       total_timeout, show_progress_bar=False):
        ""
        TestListRunner.__init__( self, test_dir, tlist, xlist, perms,
                                 rtinfo, results_writer, plat, total_timeout,
                                 show_progress_bar=show_progress_bar )
        self.batch_id = None
        self.handler = xlist.getExecutionHandler()

    def setBatchID(self, batch_id):
        ""
        self.batch_id = batch_id

    def startup(self):
        ""
        self.setup()

        self.plat.display()

        self.info = TestInformationPrinter( sys.stdout, self.xlist )

    def run(self):
        ""
        self.startup()

        uthook = utesthooks.construct_unit_testing_hook( 'run', self.batch_id )

        try:
            save_log_level = tty.get_level()
            if self.show_progress_bar:
                # skip any information messages so that only the progress bar is shown
                tty.set_level(tty.WARN)
            while True:

                tnext = self.xlist.popNext( self.plat.sizeAvailable() )

                if tnext is not None:
                    self.start_next( tnext )
                elif self.xlist.numRunning() == 0:
                    break
                else:
                    self.info.checkPrint()
                    time.sleep(1)

                showprogress = self.print_finished()

                uthook.check( self.xlist.numRunning(), self.xlist.numDone() )

                self.results_writer.midrun( self.tlist, self.rtinfo )

                if showprogress:
                    self.print_progress()

                if self.total_time_expired():
                    break

            nrL = self.xlist.popRemaining()  # these tests cannot be run

        finally:
            tty.set_level(save_log_level)
            self.tlist.writeFinished()

        self.finishup( nrL )

        return encode_integer_warning( self.tlist )

    def start_next(self, texec):
        ""
        tcase = texec.getTestCase()
        tty.info('Starting: {0}'.format(exec_path( tcase, self.test_dir)))
        start_test( self.handler, texec, self.plat )
        self.tlist.appendTestResult( tcase )

    def print_finished(self):
        ""
        showprogress = False

        for texec in list( self.xlist.getRunning() ):
            tcase = texec.getTestCase()
            if texec.poll():
                self.handler.finishExecution( texec )
            if texec.isDone():
                xs = XstatusString( tcase, self.test_dir, self.cwd )
                tty.info("Finished: {0}".format(xs))
                self.xlist.testDone( texec )
                showprogress = True

        return showprogress

    def print_progress(self):
        ""
        ndone = self.xlist.numDone()
        ntot = self.tlist.numActive()
        pct = 100 * float(ndone) / float(ntot)
        div = str(ndone)+'/'+str(ntot)
        dt = pretty_time( time.time() - self.starttime )
        tty.info("Progress: {0} {1:.1f}, time = {2}".format(div, pct, dt))
        if self.show_progress_bar:
            line = progress_bar(ntot, ndone, time.time() - self.starttime, width=30)
            tty.emit(line)

    def finishup(self, nrL):
        ""
        if len(nrL) > 0:
            tty.emit("\n")
        print_notrun_reasons( [ (tc,tc.getBlockedReason()) for tc in nrL ] )


def progress_bar(num_test, num_done, duration, width=30):
    bar = tty.progress_bar(num_test, num_done, width)
    pct = 100 * num_done / float(num_test)
    ave = duration / num_done
    togo = ave * (num_test - num_done)
    w = len(str(num_test))
    line = "\r{0} {1:{7}d}/{2} {3:5.1f}% [elapsed: {4} left: {5} ave: {6}]   ".format(
        bar, num_done, num_test, pct, hhmmss(duration), hhmmss(togo), hhmmss(ave), w
    )
    return line


def hhmmss(arg):
    seconds = int(arg)
    minutes = seconds // 60
    hours = minutes // 60
    return "%02d:%02d:%02d" % (hours, minutes % 60, seconds % 60)


def print_notrun_reasons( notrunlist ):
    ""
    for tcase,reason in notrunlist:
        xdir = tcase.getSpec().getDisplayString()
        # magic: reason = tcase.getBlockedReason()
        tty.warn("test {0!r} notrun due to dependency: {1}".format(xdir, reason))


def exec_path( tcase, test_dir ):
    ""
    xdir = tcase.getSpec().getDisplayString()
    return pathutil.relative_execute_directory( xdir, test_dir, os.getcwd() )


def run_baseline( xlist, plat ):
    ""
    failures = False

    handler = xlist.getExecutionHandler()

    for texec in xlist.consumeBacklog():

        tcase = texec.getTestCase()
        tspec = tcase.getSpec()
        tstat = tcase.getStat()

        xdir = tspec.getDisplayString()

        sys.stdout.write( "baselining "+xdir+"..." )

        start_test( handler, texec, plat, is_baseline=True )

        tm = int( os.environ.get( 'VVTEST_BASELINE_TIMEOUT', 30 ) )
        for i in range(tm):

            time.sleep(1)

            if texec.poll():
                handler.finishExecution( texec )

            if texec.isDone():
                if tstat.passed():
                    tty.info("done")
                else:
                    failures = True
                    tty.info("FAILED")
                break

        if not tstat.isDone():
            if texec.killJob():
                handler.finishExecution( texec )
            failures = True
            tty.info("TIMED OUT")

    if failures:
        tty.emit("\n\n !!!!!!!!!!!  THERE WERE FAILURES  !!!!!!!!!! \n\n")


def start_test( handler, texec, platform, is_baseline=False ):
    ""
    tcase = texec.getTestCase()

    obj = platform.getResources( tcase.getSize() )

    texec.setResourceObject( obj )

    logfile = None
    if handler.rtconfig.getAttr('logfile'):
        logfile = tcase.getSpec().getLogFilename( is_baseline )

    texec.start( handler.prepare_for_launch,
                 logfile, is_baseline, handler.perms,
                 fork_supported=handler.forkok )

    tcase.getStat().markStarted( texec.getStartTime() )


def encode_integer_warning( tlist ):
    ""
    ival = 0

    for tcase in tlist.getTests():
        if not tcase.getStat().skipTest():
            result = tcase.getStat().getResultStatus()
            if   result == 'diff'   : ival |= ( 2**1 )
            elif result == 'fail'   : ival |= ( 2**2 )
            elif result == 'timeout': ival |= ( 2**3 )
            elif result == 'notdone': ival |= ( 2**4 )
            elif result == 'notrun' : ival |= ( 2**5 )

    return ival
