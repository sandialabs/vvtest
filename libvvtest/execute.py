#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time

from . import logger
from . import utesthooks
from .printinfo import DirectInfoPrinter, BatchInfoPrinter


class TestListRunner:

    def __init__(self, tlist, xlist, perms,
                       rtinfo, results_writer, plat,
                       total_timeout ):
        ""
        self.tlist = tlist
        self.xlist = xlist
        self.perms = perms
        self.rtinfo = rtinfo
        self.results_writer = results_writer
        self.plat = plat
        self.total_timeout = total_timeout

    def setup(self):
        ""
        self.starttime = time.time()
        logger.info("Start time: {0}".format(time.ctime()))

        rfile = self.tlist.initializeResultsFile( **(self.rtinfo) )
        self.perms.apply( os.path.abspath( rfile ) )

    def total_time_expired(self):
        ""
        if self.total_timeout and self.total_timeout > 0:
            if time.time() - self.starttime > self.total_timeout:
                logger.warn('total timeout expired: {0}s'.format(self.total_timeout))
                return True
        return False


class BatchRunner( TestListRunner ):

    def __init__(self, batch, test_dir, tlist, xlist, perms,
                       rtinfo, results_writer, plat,
                       total_timeout ):
        ""
        TestListRunner.__init__( self, tlist, xlist, perms,
                                 rtinfo, results_writer, plat, total_timeout )
        self.batch = batch
        self.info = BatchInfoPrinter( test_dir, tlist, batch )

    def startup(self):
        ""
        self.setup()

        self.plat.display()

        self.tlist.setResultsDate()

        self.batch.clearBatchDirectories()
        self.batch.constructBatchJobs()

        self.qsleep = int( os.environ.get( 'VVTEST_BATCH_SLEEP_LENGTH', 15 ) )

        logger.info('Maximum concurrent batch jobs: {0}'.format(self.batch.getMaxJobs()))

    def run(self):
        ""
        self.startup()

        uthook = utesthooks.construct_unit_testing_hook( 'batch' )

        try:

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

                self.info.printFinishedBatches( qidL )
                self.info.printFinished( doneL )

                uthook.check( self.batch.numInProgress(), self.batch.numPastQueue() )

                self.results_writer.midrun( self.tlist )

                self.info.printProgress( len(doneL) )

                if self.total_time_expired():
                    break

            # any remaining tests cannot be run, so flush them
            jobstats, nrL = self.batch.flush()

        finally:
            finish_time = time.time()
            self.batch.shutdown()
            rtn = encode_integer_warning( self.tlist )
            self.tlist.writeFinished( finish_time, rtn )

        self.info.printBatchRemainders( jobstats, nrL )

        self.rtinfo['returncode'] = rtn
        self.rtinfo['finishepoch'] = finish_time

        return rtn

    def sleep_with_info_check(self):
        ""
        for i in range( int( self.qsleep + 0.5 ) ):
            self.info.checkPrint()
            time.sleep( 1 )


class DirectRunner( TestListRunner ):

    def __init__(self, test_dir, tlist, xlist, perms,
                       rtinfo, results_writer, plat,
                       total_timeout ):
        ""
        TestListRunner.__init__( self, tlist, xlist, perms,
                                 rtinfo, results_writer, plat, total_timeout )
        self.batch_id = None
        self.handler = xlist.getExecutionHandler()
        self.info = DirectInfoPrinter( test_dir, xlist, tlist.numActive() )

    def setBatchID(self, batch_id):
        ""
        self.batch_id = batch_id

    def startup(self):
        ""
        self.setup()
        self.plat.display()

    def run(self):
        ""
        self.startup()

        uthook = utesthooks.construct_unit_testing_hook( 'run', self.batch_id )

        try:
            while True:

                tnext = self.xlist.popNext( self.plat.sizeAvailable() )

                if tnext is not None:
                    self.start_next( tnext )
                elif self.xlist.numRunning() == 0:
                    break
                else:
                    self.info.checkPrint()
                    time.sleep(1)

                doneL = self.process_finished()

                self.info.printFinished( doneL )

                uthook.check( self.xlist.numRunning(), self.xlist.numDone() )

                self.results_writer.midrun( self.tlist )

                self.info.printProgress( len(doneL) )

                if self.total_time_expired():
                    break

            nrL = self.xlist.popRemaining()  # these tests cannot be run

        finally:
            finish_time = time.time()
            rtn = encode_integer_warning( self.tlist )
            self.tlist.writeFinished( finish_time, rtn )

        self.info.printRemainders( nrL )

        self.rtinfo['returncode'] = rtn
        self.rtinfo['finishepoch'] = finish_time

        return rtn

    def start_next(self, texec):
        ""
        tcase = texec.getTestCase()
        self.info.printStarting( tcase )
        start_test( self.handler, texec, self.plat )
        self.tlist.appendTestResult( tcase )

    def process_finished(self):
        ""
        doneL = []  # TestCase objects

        for texec in list( self.xlist.getRunning() ):
            tcase = texec.getTestCase()
            if texec.poll():
                self.handler.finishExecution( texec )
            if texec.isDone():
                self.xlist.testDone( texec )
                doneL.append( tcase )

        return doneL


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
        logger.warn( "\n\n !!!!!!!!!!!  THERE WERE FAILURES  !!!!!!!!!! \n\n" )


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
