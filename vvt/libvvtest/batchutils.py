#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
import os
import time
import glob

from . import TestList
from . import testlistio
from . import pathutil


class Batcher:

    def __init__(self, vvtestcmd, testlist_name,
                       plat, tlist, xlist, perms,
                       test_dir, qsublimit,
                       batch_length, max_timeout):
        ""
        self.perms = perms

        clean_exit_marker = "queue job finished cleanly"

        # allow these values to be set by environment variable, mainly for
        # unit testing; if setting these is needed more regularly then a
        # command line option should be added
        read_interval = int( os.environ.get( 'VVTEST_BATCH_READ_INTERVAL', 30 ) )
        read_timeout = int( os.environ.get( 'VVTEST_BATCH_READ_TIMEOUT', 5*60 ) )

        self.tracker = JobTracker()

        self.namer = BatchFileNamer( test_dir, testlist_name )

        jobmon = BatchJobMonitor( read_interval, read_timeout,
                                  clean_exit_marker )

        self.scheduler = BatchScheduler(
                            tlist, xlist,
                            self.tracker, self.namer, jobmon,
                            perms, plat, qsublimit )

        suffix = tlist.getResultsSuffix()
        self.handler = JobHandler( suffix, self.namer, plat,
                                   vvtestcmd,
                                   clean_exit_marker )

        self.grouper = BatchTestGrouper( xlist, batch_length, max_timeout )
        self.grouper.construct()

        self.qsub_testfilenames = []

    def getScheduler(self):
        return self.scheduler

    def getNumNotRun(self):
        ""
        return self.tracker.numToDo()

    def getNumStarted(self):
        ""
        return self.tracker.numStarted()

    def getStarted(self):
        ""
        return self.tracker.getStarted()

    def writeQsubScripts(self):
        ""
        self._remove_batch_directories()

        for qnumber,qL in enumerate( self.grouper.getGroups() ):
            self._create_job_and_write_script( qnumber, qL )

    def getIncludeFiles(self):
        ""
        return self.qsub_testfilenames

    def _remove_batch_directories(self):
        ""
        for d in self.namer.globBatchDirectories():
            print3( 'rm -rf '+d )
            pathutil.fault_tolerant_remove( d )

    def _create_job_and_write_script(self, qnumber, testL):
        ""
        jb = self.handler.createJob( qnumber, testL )

        self.tracker.addJob( qnumber, jb )

        qtime = self.grouper.computeQueueTime( jb.getTestList() )
        self.handler.writeJob( jb, qtime )

        incl = self.namer.getTestListName( qnumber, relative=True )
        self.qsub_testfilenames.append( incl )

        d = self.namer.getSubdir( qnumber )
        self.perms.recurse( d )


class BatchTestGrouper:

    def __init__(self, xlist, batch_length, max_timeout):
        ""
        self.xlist = xlist

        if batch_length == None:
            self.qlen = 30*60
        else:
            self.qlen = batch_length

        self.max_timeout = max_timeout

        # TODO: make Tzero a platform plugin thing
        self.Tzero = 21*60*60  # no timeout in batch mode is 21 hours

        self.groups = []

    def construct(self):
        ""
        qL = []

        for np in self.xlist.getTestExecProcList():
            qL.extend( self._process_groups( np ) )

        qL.sort()
        qL.reverse()

        self.groups = [ L[3] for L in qL ]

    def getGroups(self):
        ""
        return self.groups

    def computeQueueTime(self, tlist):
        ""
        qtime = 0

        for tcase in tlist.getTests():
            tspec = tcase.getSpec()
            qtime += int( tspec.getAttr('timeout') )

        if qtime == 0:
            qtime = self.Tzero  # give it the "no timeout" length of time
        else:
            qtime = apply_queue_timeout_bump_factor( qtime )

        if self.max_timeout:
            qtime = min( qtime, float(self.max_timeout) )

        return qtime

    def _process_groups(self, np):
        ""
        qL = []

        xL = []
        for tcase in self.xlist.getTestExecList(np):
            xdir = tcase.getSpec().getDisplayString()
            xL.append( (tcase.getSpec().getAttr('timeout'),xdir,tcase) )
        xL.sort()

        grpL = []
        tsum = 0
        for rt,xdir,tcase in xL:
            tspec = tcase.getSpec()
            if tcase.numDependencies() > 0 or tspec.getAttr('timeout') < 1:
                # analyze tests and those with no timeout get their own group
                qL.append( [ self.Tzero, np, len(qL), [tcase] ] )
            else:
                if len(grpL) > 0 and tsum + rt > self.qlen:
                    qL.append( [ tsum, np, len(qL), grpL ] )
                    grpL = []
                    tsum = 0
                grpL.append( tcase )
                tsum += rt

        if len(grpL) > 0:
            qL.append( [ tsum, np, len(qL), grpL ] )

        return qL


def make_batch_TestList( filename, suffix, qlist ):
    ""
    tl = TestList.TestList( filename )
    tl.setResultsSuffix( suffix )
    for tcase in qlist:
        tl.addTest( tcase )

    return tl


def compute_max_np( tlist ):
    ""
    maxnp = 0
    for tcase in tlist.getTests():
        tspec = tcase.getSpec()
        np = int( tspec.getParameters().get('np', 0) )
        if np <= 0: np = 1
        maxnp = max( maxnp, np )

    return maxnp


def apply_queue_timeout_bump_factor( qtime ):
    ""
    # allow more time in the queue than calculated. This overhead time
    # monotonically increases with increasing qtime and plateaus at
    # about 16 minutes of overhead, but force it to never be more than
    # exactly 15 minutes.

    if qtime < 60:
        qtime += 60
    elif qtime < 10*60:
        qtime += qtime
    elif qtime < 30*60:
        qtime += min( 15*60, 10*60 + int( float(qtime-10*60) * 0.3 ) )
    else:
        qtime += min( 15*60, 10*60 + int( float(30*60-10*60) * 0.3 ) )

    return qtime


class JobHandler:

    def __init__(self, suffix, filenamer, platform,
                       basevvtestcmd, clean_exit_marker):
        ""
        self.suffix = suffix
        self.namer = filenamer
        self.plat = platform
        self.vvtestcmd = basevvtestcmd
        self.clean_exit_marker = clean_exit_marker

    def createJob(self, qnumber, testL):
        ""
        testlistfname = self.namer.getTestListName( qnumber )
        tlist = make_batch_TestList( testlistfname, self.suffix, testL )

        maxnp = compute_max_np( tlist )

        pout = self.namer.getBatchOutputName( qnumber )
        tout = self.namer.getTestListName( qnumber ) + '.' + self.suffix

        bjob = BatchJob( qnumber, maxnp, pout, tout, tlist )

        return bjob

    def writeJob(self, bjob, qtime):
        ""
        tl = bjob.getTestList()

        tl.stringFileWrite( extended=True )

        qidstr = str( bjob.getQNumber() )
        maxnp = bjob.getMaxNP()

        fn = self.namer.getBatchScriptName( qidstr )
        fp = open( fn, "w" )

        tdir = self.namer.getTestResultsRoot()
        pout = self.namer.getBatchOutputName( bjob.getQNumber() )

        hdr = self.plat.getQsubScriptHeader( maxnp, qtime, tdir, pout )
        fp.writelines( [ hdr + '\n\n',
                         'cd ' + tdir + ' || exit 1\n',
                         'echo "job start time = `date`"\n' + \
                         'echo "job time limit = ' + str(qtime) + '"\n' ] )

        # set the environment variables from the platform into the script
        for k,v in self.plat.getEnvironment().items():
            fp.write( 'setenv ' + k + ' "' + v  + '"\n' )

        cmd = self.vvtestcmd + ' --qsub-id=' + qidstr

        if len( tl.getTestMap() ) == 1:
            # force a timeout for batches with only one test
            if qtime < 600: cmd += ' -T ' + str(qtime*0.90)
            else:           cmd += ' -T ' + str(qtime-120)

        cmd += ' || exit 1'
        fp.writelines( [ cmd+'\n\n' ] )

        # echo a marker to determine when a clean batch job exit has occurred
        fp.writelines( [ 'echo "'+self.clean_exit_marker+'"\n' ] )

        fp.close()


class BatchScheduler:

    def __init__(self, tlist, xlist,
                       tracker, namer, jobmon,
                       perms, plat, maxjobs):
        ""
        self.tlist = tlist
        self.xlist = xlist
        self.tracker = tracker
        self.namer = namer
        self.perms = perms
        self.plat = plat
        self.maxjobs = maxjobs
        self.jobmon = jobmon

    def numInFlight(self):
        """
        Returns the number of batch jobs are still running or stopped but
        whose results have not been read yet.
        """
        return self.tracker.numInFlight()

    def numPastQueue(self):
        ""
        return self.tracker.numPastQueue()

    def numStarted(self):
        """
        Number of batch jobs currently running (those that have been started
        and still appear to be in the batch queue).
        """
        return self.tracker.numStarted()

    def numDone(self):
        """
        Number of batch jobs that ran and completed.
        """
        return self.tracker.numDone()

    def checkstart(self):
        """
        Launches a new batch job if possible.  If it does, the batch id is
        returned.
        """
        if self.tracker.numStarted() < self.maxjobs:
            for qid,bjob in self.tracker.getNotStarted():
                if self.getBlockingDependency( bjob ) == None:
                    pin = self.namer.getBatchScriptName( qid )
                    tdir = self.namer.getTestResultsRoot()
                    jobid = self.plat.Qsubmit( tdir, bjob.getOutputFile(), pin )
                    self.tracker.markJobStarted( qid )
                    self.jobmon.start( bjob, jobid )
                    return qid
        return None

    def checkdone(self):
        """
        Uses the platform to find batch jobs that ran but are now no longer
        in the batch queue.  These jobs are moved from the started list to
        the stopped list.

        Then the jobs in the "stopped" list are visited and their test
        results are read.  When a job is successfully read, the job is moved
        from the "stopped" list to the "read" list.

        Returns a list of job ids that were removed from the batch queue,
        and a list of tests that were successfully read in.
        """
        qdoneL = []
        startlist = self.tracker.getStarted()
        if len(startlist) > 0:
            jobidL = [ jb.jobid for qid,jb in startlist ]
            statusD = self.plat.Qquery( jobidL )
            tnow = time.time()
            for qid,bjob in list( startlist ):
                check_set_outfile_permissions( bjob, self.perms )
                if self.jobmon.checkJobStarted( bjob, statusD[ bjob.getJobID() ], tnow ):
                    self.tracker.markJobStopped( qid )
                    self.jobmon.stop( bjob )
                    qdoneL.append( qid )

        tnow = time.time()
        tdoneL = []
        for qid,bjob in list( self.tracker.getStopped() ):
            if self.jobmon.timeToCheckIfFinished( bjob, tnow ):
                if self.checkJobFinished( bjob.getOutputFile(),
                                          bjob.getResultsFile() ):
                    # load the results into the TestList
                    tdoneL.extend( self.finalizeJob( qid, bjob, 'clean' ) )
                else:
                    if not self.jobmon.extendFinishCheck( bjob, tnow ):
                        # too many attempts to read; assume the queue job
                        # failed somehow, but force a read anyway
                        tdoneL.extend( self.finalizeJob( qid, bjob ) )

        return qdoneL, tdoneL

    def checkJobFinished(self, outfilename, resultsname):
        ""
        finished = False
        if self.jobmon.scanBatchOutput( outfilename ):
            finished = testlistio.file_is_marked_finished( resultsname )
        return finished

    def flush(self):
        """
        Remove any remaining jobs from the "todo" list, add them to the "read"
        list, but mark them as not run.

        Returns a triple
            - a list of batch ids that were not run
            - a list of batch ids that did not finish
            - a list of the tests that did not run, each of which is a
              pair (a test, failed dependency test)
        """
        # should not be here if there are jobs currently running
        assert self.tracker.numInFlight() == 0

        # force remove the rest of the jobs that were not run and gather
        # the list of tests that were not run
        notrunL = []
        for qid,bjob in list( self.tracker.getNotStarted() ):
            tcase1 = self.getBlockingDependency( bjob )
            assert tcase1 != None  # otherwise checkstart() should have ran it
            for tcase0 in bjob.getTests():
                notrunL.append( (tcase0,tcase1) )
            self.tracker.markJobDone( qid, 'notrun' )
            bjob.setResult( 'notrun' )

        # TODO: rather than only reporting the jobs left on qtodo as not run,
        #       loop on all jobs in qread and look for 'notrun' mark

        notrun = []
        notdone = []
        for qid,bjob in self.tracker.getDone():
            if bjob.getResult() == 'notrun': notrun.append( str(qid) )
            elif bjob.getResult() == 'notdone': notdone.append( str(qid) )

        return notrun, notdone, notrunL

    def finalizeJob(self, qid, bjob, mark=None):
        ""
        tL = []

        if not os.path.exists( bjob.getOutputFile() ):
            mark = 'notrun'

        elif os.path.exists( bjob.getResultsFile() ):
            if mark == None:
                mark = 'notdone'

            self.tlist.readTestResults( bjob.getResultsFile() )

            tlr = testlistio.TestListReader( bjob.getResultsFile() )
            tlr.read()
            jobtests = tlr.getTests()

            # only add tests to the stopped list that are done
            for tcase in bjob.getTests():

                tid = tcase.getSpec().getID()

                job_tcase = jobtests.get( tid, None )
                if job_tcase and job_tcase.getStat().isDone():
                    tL.append( tcase )
                    self.xlist.testDone( tcase )

        else:
            mark = 'fail'

        self.tracker.markJobDone( qid, mark )
        bjob.setResult( mark )

        return tL

    def getBlockingDependency(self, bjob):
        """
        If a dependency of any of the tests in the current list have not run or
        ran but did not pass or diff, then that dependency test is returned.
        Otherwise None is returned.
        """
        for tcase in bjob.getTests():
            deptx = tcase.getBlockingDependency()
            if deptx != None:
                return deptx
        return None


def check_set_outfile_permissions( bjob, perms ):
    ""
    ofile = bjob.getOutputFile()
    if not bjob.outfileSeen() and os.path.exists( ofile ):
        perms.set( ofile )
        bjob.setOutfileSeen()


class BatchJob:

    def __init__(self, qnumber, maxnp, fout, resultsfile, tlist):
        ""
        self.qnumber = qnumber
        self.maxnp = maxnp
        self.outfile = fout
        self.resultsfile = resultsfile
        self.tlist = tlist  # a TestList object

        self.jobid = None
        self.tstart = None
        self.outfile_seen = False
        self.tstop = None
        self.tcheck = None
        self.result = None

    def getQNumber(self): return self.qnumber
    def getMaxNP(self): return self.maxnp

    def getTestList(self): return self.tlist
    def getTests(self): return self.tlist.getTests()

    def getJobID(self): return self.jobid

    def getStartTime(self): return self.tstart
    def getCheckTime(self): return self.tcheck
    def getStopTime(self): return self.tstop

    def getResult(self): return self.result

    def getOutputFile(self): return self.outfile
    def outfileSeen(self): return self.outfile_seen
    def getResultsFile(self): return self.resultsfile

    def setJobID(self, jobid):
        ""
        self.jobid = jobid

    def setStartTime(self, tstart):
        ""
        self.tstart = tstart

    def setOutfileSeen(self):
        ""
        self.outfile_seen = True

    def setCheckTime(self, tcheck):
        ""
        self.tcheck = tcheck

    def setStopTime(self, tstop):
        ""
        self.tstop = tstop

    def setResult(self, result):
        ""
        self.result = result


class BatchJobMonitor:

    def __init__(self, read_interval, read_timeout, clean_exit_marker):
        ""
        self.read_interval = read_interval
        self.read_timeout = read_timeout
        self.clean_exit_marker = clean_exit_marker

    def start(self, bjob, jobid):
        ""
        bjob.setJobID( jobid )
        bjob.setStartTime( time.time() )

    def checkJobStarted(self, bjob, queue_status, current_time):
        """
        If either the output file exists or enough time has elapsed since the
        job was submitted, then mark the BatchJob as having started.

        Returns true if the job was started.
        """
        started = False
        elapsed = current_time - bjob.getStartTime()

        if not queue_status:
            if elapsed > 30 or bjob.outfileSeen():
                started = True

        return started

    def timeToCheckIfFinished(self, bjob, current_time):
        ""
        return bjob.getCheckTime() < current_time

    def extendFinishCheck(self, bjob, current_time):
        """
        Resets the finish check time to a time into the future.  Returns
        False if the number of extensions has been exceeded.
        """
        if current_time < bjob.getStopTime()+self.read_timeout:
            # set the time for the next read attempt
            bjob.setCheckTime( current_time + self.read_interval )
            return False

        return True

    def stop(self, bjob):
        ""
        tm = time.time()
        bjob.setStopTime( tm )
        bjob.setCheckTime( tm + self.read_interval )

    def scanBatchOutput(self, outfile):
        """
        Tries to read the batch output file, then looks for the marker
        indicating a clean job script finish.  Returns true for a clean finish.
        """
        clean = False

        try:
            # compute file seek offset, and open the file
            sz = os.path.getsize( outfile )
            off = max(sz-512, 0)
            fp = open( outfile, 'r' )
        except Exception:
            pass
        else:
            try:
                # only read the end of the file
                fp.seek(off)
                buf = fp.read(512)
            except Exception:
                pass
            else:
                if self.clean_exit_marker in buf:
                    clean = True
            try:
                fp.close()
            except Exception:
                pass

        return clean


class BatchFileNamer:

    def __init__(self, rootdir, listbasename):
        """
        """
        self.rootdir = rootdir
        self.listbasename = listbasename

    def getTestResultsRoot(self):
        ""
        return self.rootdir

    def getTestListName(self, qid, relative=False):
        """
        """
        return self.getPath( self.listbasename, qid, relative )

    def getBatchScriptName(self, qid):
        """
        """
        return self.getPath( 'qbat', qid )

    def getBatchOutputName(self, qid):
        """
        """
        return self.getPath( 'qbat-out', qid )

    def getPath(self, basename, qid, relative=False):
        """
        Given a base file name and a batch id, this function returns the
        file name in the batchset subdirectory and with the id appended.
        If 'relative' is true, then the path is relative to the TestResults
        directory.
        """
        subd = self.getSubdir( qid, relative )
        fn = os.path.join( subd, basename+'.'+str(qid) )
        return fn

    def getSubdir(self, qid, relative=False):
        """
        Given a queue/batch id, this function returns the corresponding
        subdirectory name.  The 'qid' argument can be a string or integer.
        """
        d = 'batchset' + str( int( float(qid)/50 + 0.5 ) )
        if relative:
            return d
        return os.path.join( self.rootdir, d )

    def globBatchDirectories(self):
        """
        Returns a list of existing batch working directories.
        """
        dL = []
        for f in os.listdir( self.rootdir ):
            if f.startswith( 'batchset' ):
                dL.append( os.path.join( self.rootdir, f ) )
        return dL


class JobTracker:

    def __init__(self):
        ""
        self.qtodo  = {}  # to be submitted
        self.qstart = {}  # submitted
        self.qstop  = {}  # no longer in the queue
        self.qdone  = {}  # final results have been read

    def addJob(self, qid, batchjob ):
        ""
        self.qtodo[ qid ] = batchjob

    def numToDo(self):
        ""
        return len( self.qtodo )

    def numStarted(self):
        return len( self.qstart )

    def numDone(self):
        return len( self.qdone )

    def numInFlight(self):
        return len( self.qstart ) + len( self.qstop )

    def numPastQueue(self):
        return len( self.qstop ) + len( self.qdone )

    def getNotStarted(self):
        ""
        return self.qtodo.items()

    def getStarted(self):
        ""
        return self.qstart.items()

    def getStopped(self):
        ""
        return self.qstop.items()

    def getDone(self):
        ""
        return self.qdone.items()

    def markJobStarted(self, qid):
        ""
        jb = self.popJob( qid )
        self.qstart[ qid ] = jb

    def markJobStopped(self, qid):
        ""
        jb = self.popJob( qid )
        self.qstop[ qid ] = jb

    def markJobDone(self, qid, done_mark):
        ""
        jb = self.popJob( qid )
        self.qdone[ qid ] = jb

    def popJob(self, qid):
        ""
        for qD in [ self.qtodo, self.qstart, self.qstop, self.qdone ]:
            if qid in qD:
                return qD.pop( qid )
        raise Exception( 'job id not found: '+str(qid) )


def print3( *args ):
    sys.stdout.write( ' '.join( [ str(arg) for arg in args ] ) + '\n' )
    sys.stdout.flush()
