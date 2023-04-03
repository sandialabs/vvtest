#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.
from __future__ import division

import os, sys
import time

from . import logger
from . import utesthooks
from . import pathutil
from .printinfo import DirectInfoPrinter, BatchInfoPrinter
from .outpututils import XstatusString


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
        self.current_log_level = logger.get_level()

    def setup(self):
        ""
        self.starttime = time.time()
        logger.info("Start time: {0}".format(time.ctime()))

        rfile = self.tlist.initializeResultsFile( **(self.rtinfo.asDict()) )
        self.perms.apply( os.path.abspath( rfile ) )

        self.cwd = os.getcwd()

    def total_time_expired(self):
        ""
        if self.total_timeout and self.total_timeout > 0:
            if time.time() - self.starttime > self.total_timeout:
                logger.warn('total timeout expired: {0}s'.format(self.total_timeout))
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
        self.info = BatchInfoPrinter( self.tlist, self.batch, self.show_progress_bar )

        logger.info('Maximum concurrent batch jobs: {0}'.format(self.batch.getMaxJobs()))

    def run(self):
        ""
        self.startup()

        uthook = utesthooks.construct_unit_testing_hook( 'batch' )

        try:
            save_log_level = logger.get_level()
            if self.show_progress_bar:
                # skip any information messages so that only the progress bar is shown
                logger.set_level(logger.WARN)

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

                self.info.printProgress( len(doneL) )

                if self.total_time_expired():
                    break

            # any remaining tests cannot be run, so flush them
            NS, NF, nrL = self.batch.flush()

        finally:
            logger.set_level(save_log_level)
            self.batch.shutdown()

        self.finishup( NS, NF, nrL )

        return encode_integer_warning( self.tlist )

    def print_finished(self, qidL, doneL):
        ""
        if len(qidL) > 0:
            ids = ' '.join( [ str(qid) for qid in qidL ] )
            logger.info('Finished batch IDS: {0}'.format(ids))
        for tcase in doneL:
            ts = XstatusString( tcase, self.test_dir, self.cwd )
            logger.info("Finished: {0}".format(ts))

    def sleep_with_info_check(self):
        ""
        for i in range( int( self.qsleep + 0.5 ) ):
            self.info.checkPrint()
            time.sleep( 1 )

    def finishup(self, NS, NF, nrL):
        ""
        if len(NS)+len(NF)+len(nrL) > 0:
            logger.emit("\n")
        if len(NS) > 0:
            logger.warn(
                "these batch numbers did not seem to start: {0}".format(' '.join(NS))
            )
        if len(NF) > 0:
            logger.warn(
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

        self.info = DirectInfoPrinter( self.xlist, self.tlist.numActive(), self.show_progress_bar )

    def run(self):
        ""
        self.startup()

        uthook = utesthooks.construct_unit_testing_hook( 'run', self.batch_id )

        try:
            save_log_level = logger.get_level()
            if self.show_progress_bar:
                # skip any information messages so that only the progress bar is shown
                logger.set_level(logger.WARN)
            while True:

                tnext = self.xlist.popNext( self.plat.sizeAvailable() )

                if tnext is not None:
                    self.start_next( tnext )
                elif self.xlist.numRunning() == 0:
                    break
                else:
                    self.info.checkPrint()
                    time.sleep(1)

                done_count = self.process_finished()

                uthook.check( self.xlist.numRunning(), self.xlist.numDone() )

                self.results_writer.midrun( self.tlist, self.rtinfo )

                self.info.printProgress( done_count )

                if self.total_time_expired():
                    break

            nrL = self.xlist.popRemaining()  # these tests cannot be run

        finally:
            logger.set_level(save_log_level)
            self.tlist.writeFinished()

        self.finishup( nrL )

        return encode_integer_warning( self.tlist )

    def start_next(self, texec):
        ""
        tcase = texec.getTestCase()
        logger.info('Starting: {0}'.format(exec_path( tcase, self.test_dir)))
        start_test( self.handler, texec, self.plat )
        self.tlist.appendTestResult( tcase )

    def process_finished(self):
        ""
        ndone = 0

        for texec in list( self.xlist.getRunning() ):
            tcase = texec.getTestCase()
            if texec.poll():
                self.handler.finishExecution( texec )
            if texec.isDone():
                xs = XstatusString( tcase, self.test_dir, self.cwd )
                logger.info("Finished: {0}".format(xs))
                self.xlist.testDone( texec )
                ndone += 1

        return ndone

    def finishup(self, nrL):
        ""
        if len(nrL) > 0:
            logger.emit("\n")
        print_notrun_reasons( [ (tc,tc.getBlockedReason()) for tc in nrL ] )


def print_notrun_reasons( notrunlist ):
    ""
    for tcase,reason in notrunlist:
        xdir = tcase.getSpec().getDisplayString()
        # magic: reason = tcase.getBlockedReason()
        logger.warn("test {0!r} notrun due to dependency: {1}".format(xdir, reason))


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
                    logger.info("done")
                else:
                    failures = True
                    logger.info("FAILED")
                break

        if not tstat.isDone():
            if texec.killJob():
                handler.finishExecution( texec )
            failures = True
            logger.info("TIMED OUT")

    if failures:
        logger.emit("\n\n !!!!!!!!!!!  THERE WERE FAILURES  !!!!!!!!!! \n\n")


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
