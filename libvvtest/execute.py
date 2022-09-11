#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time

from . import utesthooks
from . import pathutil
from .printinfo import TestInformationPrinter
from .outpututils import XstatusString, pretty_time


class TestListRunner:

    def __init__(self, test_dir, tlist, xlist, perms,
                       rtinfo, results_writer, plat,
                       total_timeout):
        ""
        self.test_dir = test_dir
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
        print3( "Start time:", time.ctime() )

        rfile = self.tlist.initializeResultsFile( **(self.rtinfo.asDict()) )
        self.perms.apply( os.path.abspath( rfile ) )

        self.cwd = os.getcwd()

    def total_time_expired(self):
        ""
        if self.total_timeout and self.total_timeout > 0:
            if time.time() - self.starttime > self.total_timeout:
                print3( '\n*** vvtest: total timeout expired:',
                        self.total_timeout, '\n' )
                return True
        return False


class BatchRunner( TestListRunner ):

    def __init__(self, test_dir, tlist, xlist, perms,
                       rtinfo, results_writer, plat,
                       total_timeout):
        ""
        TestListRunner.__init__( self, test_dir, tlist, xlist, perms,
                                 rtinfo, results_writer, plat, total_timeout )
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

        print3( 'Maximum concurrent batch jobs:', self.batch.getMaxJobs() )

    def run(self):
        ""
        self.startup()

        uthook = utesthooks.construct_unit_testing_hook( 'batch' )

        try:
            while True:

                qid = self.batch.checkstart()
                if qid != None:
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
            self.batch.shutdown()

        self.finishup( NS, NF, nrL )

        return encode_integer_warning( self.tlist )

    def print_finished(self, qidL, doneL):
        ""
        if len(qidL) > 0:
            ids = ' '.join( [ str(qid) for qid in qidL ] )
            print3( 'Finished batch IDS:', ids )
        for tcase in doneL:
            ts = XstatusString( tcase, self.test_dir, self.cwd )
            print3( "Finished:", ts )

    def print_progress(self, doneL):
        ""
        if len(doneL) > 0:
            sL = [ get_batch_info( self.batch ),
                   get_test_info( self.tlist, self.xlist ),
                   'time = '+pretty_time( time.time() - self.starttime ) ]
            print3( "Progress:", ', '.join( sL )  )

    def sleep_with_info_check(self):
        ""
        for i in range( int( self.qsleep + 0.5 ) ):
            self.info.checkPrint()
            time.sleep( 1 )

    def finishup(self, NS, NF, nrL):
        ""
        if len(NS)+len(NF)+len(nrL) > 0:
            print3()
        if len(NS) > 0:
            print3( "*** Warning: these batch numbers did not seem to start:",
                    ' '.join(NS) )
        if len(NF) > 0:
            print3( "*** Warning: these batch numbers did not seem to finish:",
                    ' '.join(NF) )

        print_notrun_reasons( nrL )


class DirectRunner( TestListRunner ):

    def __init__(self, test_dir, tlist, xlist, perms,
                       rtinfo, results_writer, plat,
                       total_timeout):
        ""
        TestListRunner.__init__( self, test_dir, tlist, xlist, perms,
                                 rtinfo, results_writer, plat, total_timeout )
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
            while True:

                tnext = self.xlist.popNext( self.plat.sizeAvailable() )

                if tnext != None:
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
            self.tlist.writeFinished()

        self.finishup( nrL )

        return encode_integer_warning( self.tlist )

    def start_next(self, texec):
        ""
        tcase = texec.getTestCase()
        print3( 'Starting:', exec_path( tcase, self.test_dir ) )
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
                print3( "Finished:", xs )
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
        print3( "Progress: " + div+" = %%%.1f"%pct + ', time = '+dt )

    def finishup(self, nrL):
        ""
        if len(nrL) > 0:
            print3()
        tcase_with_reason = [ (T[0].getTestCase(),T[1]) for T in nrL ]
        print_notrun_reasons( tcase_with_reason )


def print_notrun_reasons( notrunlist ):
    ""
    for tcase,reason in notrunlist:
        xdir = tcase.getSpec().getDisplayString()
        # magic: reason = tcase.getBlockedReason()
        print3( '*** Warning: test "'+xdir+'"',
                'notrun due to dependency: ' + str(reason) )


def get_batch_info( batch ):
    ""
    ndone = batch.getNumDone()
    nrun = batch.numInProgress()

    return 'jobs running='+str(nrun)+' completed='+str(ndone)


def get_test_info( tlist, xlist ):
    ""
    ndone = xlist.numDone()
    ntot = tlist.numActive()
    tpct = 100 * float(ndone) / float(ntot)
    tdiv = 'tests '+str(ndone)+'/'+str(ntot)

    return tdiv+" = %%%.1f"%tpct


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
                    print3( "done" )
                else:
                    failures = True
                    print3("FAILED")
                break

        if not tstat.isDone():
            if texec.killJob():
                handler.finishExecution( texec )
            failures = True
            print3( "TIMED OUT" )

    if failures:
        print3( "\n\n !!!!!!!!!!!  THERE WERE FAILURES  !!!!!!!!!! \n\n" )


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


def print3( *args ):
    ""
    sys.stdout.write( ' '.join( [ str(arg) for arg in args ] ) + '\n' )
    sys.stdout.flush()
