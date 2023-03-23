#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
import os
import time
import glob
import itertools
from os.path import dirname

from . import tty
from . import TestList
from .testlistio import TestListReader, file_is_marked_finished
from . import pathutil
from .teststatus import copy_test_results


class Batcher:

    def __init__(self, vvtestcmd,
                       tlist, perms,
                       batchlimit, max_qtime,
                       grouper, namer, jobhandler ):
        ""
        self.perms = perms
        self.maxjobs = batchlimit
        self.maxqtime = max_qtime

        self.namer = namer
        self.jobhandler = jobhandler

        self.results = ResultsHandler( tlist )

        self.rundate = tlist.getResultsDate()
        self.vvtestcmd = vvtestcmd

        self.grouper = grouper

    def getMaxJobs(self):
        ""
        return self.maxjobs

    def clearBatchDirectories(self):
        ""
        self._remove_batch_directories()

    def constructBatchJobs(self):
        ""
        self.grouper.createGroups()
        for grp in self.grouper.getGroups():
            bjob = self.jobhandler.createJob()
            self._construct_job( bjob, grp )

    def getNumStarted(self):
        """
        Number of batch jobs currently in progress (those that have been
        submitted and still appear to be in the queue).
        """
        return self.jobhandler.numSubmitted()

    def numInProgress(self):
        """
        Returns the number of batch jobs are still in the queue or stopped but
        whose results have not yet been read.
        """
        return self.jobhandler.numSubmitted() + self.jobhandler.numStopped()

    def numPastQueue(self):
        ""
        return self.jobhandler.numStopped() + self.jobhandler.numDone()

    def getNumDone(self):
        """
        Number of batch jobs that ran and completed.
        """
        return self.jobhandler.numDone()

    def getSubmittedJobs(self):
        ""
        return self.jobhandler.getSubmitted()

    def checkstart(self):
        """
        Launches a new batch job if possible.  If it does, the batch id is
        returned.
        """
        if self.jobhandler.numSubmitted() < self.maxjobs:
            for bjob in self.jobhandler.getNotStarted():
                if not self.results.hasBlockingDependency( bjob ):
                    self._start_job( bjob )
                    return bjob.getBatchID()
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
        tdoneL = []
        qdoneL = []
        self._check_get_stopped_jobs( qdoneL, tdoneL )
        self._check_get_finished_tests( tdoneL )

        return qdoneL, tdoneL

    def flush(self):
        """
        Remove any remaining jobs from the "todo" list, add them to the "read"
        list, but mark them as not run.

        Returns a triple
            - a list of batch ids that were not run
            - a list of batch ids that did not finish
            - a list of the tests that did not run, each of which is a
              pair (TestCase, failed dependency test)
        """
        jobL = self.jobhandler.markNotStartedJobsAsDone()

        notrunL = []
        for bjob in jobL:
            notrunL.extend( self.results.getReasonForNotRun( bjob ) )

        notrun,notdone = self.jobhandler.getUnfinishedJobIDs()

        return notrun, notdone, notrunL

    def shutdown(self):
        ""
        self.jobhandler.cancelStartedJobs()
        self.results.finalize()

    #####################################################################

    def _construct_job(self, bjob, batchgrp):
        ""
        tlist = self._make_TestList( bjob.getBatchID(), batchgrp )

        jobsize = compute_job_size( tlist, self.jobhandler.getNodeSize() )

        bjob.setJobSize( jobsize )
        bjob.setJobObject( batchgrp )

    def _make_TestList(self, batchid, batchgrp ):
        ""
        tl = batchgrp.getTestList()

        fn = self.namer.getBatchPath( batchid )
        tl.setFilename( fn )

        tl.setResultsDate( self.rundate )

        return tl

    def _start_job(self, bjob):
        ""
        self._write_job( bjob )
        self.results.addResultsInclude( bjob )
        self.jobhandler.startJob( bjob )

    def _write_job(self, bjob):
        ""
        grp = bjob.getJobObject()
        tl = grp.getTestList()

        bdir = dirname( bjob.getJobScriptName() )
        check_make_directory( bdir, self.perms )

        tname = tl.stringFileWrite( extended=True )

        cmd = self.vvtestcmd + ' --batch-id='+str( bjob.getBatchID() )

        # this is arbitrary (for now?)
        no_timeout_value = 21*60*60

        qtime = compute_queue_time( grp, self.maxqtime, no_timeout_value )

        if len( tl.getTestMap() ) == 1:
            # force a timeout for batches with only one test
            if qtime < 600: cmd += ' -T ' + str(qtime*0.90)
            else:           cmd += ' -T ' + str(qtime-120)

        nn,np,nd = bjob.getJobSize()
        ppn,dpn = self.jobhandler.getNodeSize()
        assert nn and ppn
        cmd += ' -N '+str(nn*ppn)+' --platopt ppn='+str(ppn)
        if dpn:
            cmd += ' --max-devices '+str(nn*dpn)+' --platopt dpn='+str(dpn)

        cmd += ' || exit 1'

        bname = self.jobhandler.writeJobScript( bjob, qtime, cmd )

        self.perms.apply( bname )
        self.perms.apply( tname )

    def _check_get_stopped_jobs(self, qdoneL, tdoneL):
        ""
        tm = time.time()

        for bjob in self.jobhandler.getSubmitted():
            # magic: also use check time to look for outfile
            check_set_outfile_permissions( bjob, self.perms, tm )

        stop_jobs = self.jobhandler.transitionStartedToStopped()

        for bjob in stop_jobs:
            self.results.readJobResults( bjob, tdoneL )
            self.jobhandler.resetCheckTime( bjob, tm )

        for bjob in stop_jobs:
            qdoneL.append( bjob.getBatchID() )

    def _check_get_finished_tests(self, tdoneL):
        ""
        tnow = time.time()

        for bjob in self.jobhandler.getSubmitted():
            if self.jobhandler.isTimeToCheck( bjob, tnow ):
                self.results.readJobResults( bjob, tdoneL )
                self.jobhandler.resetCheckTime( bjob, tnow )

        for bjob in list( self.jobhandler.getStopped() ):
            if self.jobhandler.isTimeToCheck( bjob, tnow ):
                self._check_job_finish( bjob, tdoneL, tnow )

    def _check_job_finish(self, bjob, tdoneL, current_time):
        ""
        if self._check_for_clean_finish( bjob ):
            self.results.readJobResults( bjob, tdoneL )
            self.results.completeResultsInclude( bjob )
            self.jobhandler.markJobDone( bjob, 'clean' )

        elif not self.jobhandler.resetCheckTime( bjob, current_time ):
            # too many attempts to read; assume the queue job
            # failed somehow, but force a read anyway
            self._force_job_finish( bjob, tdoneL )

    def _check_for_clean_finish(self, bjob):
        ""
        ofile = bjob.getOutputFilename()
        rfile = bjob.getJobObject().getTestList().getResultsFilename()

        finished = False
        if self.jobhandler.checkBatchOutputForExit( ofile ):
            finished = file_is_marked_finished( rfile )

        return finished

    def _force_job_finish(self, bjob, tdoneL):
        ""
        if not os.path.exists( bjob.getOutputFilename() ):
            mark = 'notrun'

        elif os.path.exists( bjob.getJobObject().getTestList().getResultsFilename() ):
            mark = 'notdone'
            self.results.readJobResults( bjob, tdoneL )

        else:
            mark = 'fail'

        self.results.completeResultsInclude( bjob )

        self.jobhandler.markJobDone( bjob, mark )

    def _remove_batch_directories(self):
        ""
        for d in self.namer.globBatchDirectories():
            tty.emit('rm -rf {0}'.format(d), end="\n")
            pathutil.fault_tolerant_remove( d )


class BatchTestGrouper:

    def __init__(self, tlist, batch_length):
        ""
        self.tlist = tlist

        if batch_length is None:
            self.tsize = 30*60
        else:
            self.tsize = batch_length

    def createGroups(self):
        ""
        self._process_groups()
        self._sort_groups()

    def getGroups(self):
        ""
        return self.batches

    def _sort_groups(self):
        ""
        sortL = []
        for grp in self.batches:
            sortL.append( ( grp.makeSortableKey(), grp ) )
        sortL.sort( reverse=True )

        self.batches = [ grp for _,grp in sortL ]

    def _process_groups(self):
        ""
        self.batches = []
        self.group = None
        self.num_groups = 0

        back = self.tlist.getActiveTests()
        back.sort(
            key=lambda tc: [ tc.getSize()[0], tc.getStat().getAttr('timeout') ],
            reverse=True )

        for tcase in back:
            assert tcase.getSpec().constructionCompleted()
            self._add_test_case( tcase )

        if self.group != None and not self.group.empty():
            self.batches.append( self.group )

    def _add_test_case(self, tcase):
        ""
        timeval = tcase.getStat().getAttr('timeout')

        if tcase.numDependencies() > 0:
            # tests with dependencies (like analyze tests) get their own group
            self._add_single_group( tcase, timeval )

        elif timeval < 1:
            # a zero timeout means no limit
            self._add_single_group( tcase, 0 )

        else:
            self._check_start_new_group( tcase )

    def _check_start_new_group(self, tcase):
        ""
        size = tcase.getSize()
        timeval = tcase.getStat().getAttr('timeout')

        if self.group is None:
            self.group = self._make_new_group()

        elif self.group.needNewGroup( size, timeval, self.tsize ):
            self.batches.append( self.group )
            self.group = self._make_new_group()

        self.group.appendTest( tcase, timeval )

    def _add_single_group(self, tcase, timeval):
        ""
        grp = self._make_new_group()
        grp.appendTest( tcase, timeval )
        self.batches.append( grp )

    def _make_new_group(self):
        ""
        grplist = TestList.TestList( self.tlist.getTestCaseFactory() )
        grp = BatchGroup( grplist, self.num_groups )
        self.num_groups += 1
        return grp


def compute_queue_time( grp, maxqtime, no_timeout_value ):
    ""
    qtime = grp.getTime()

    if qtime == 0:
        qtime = no_timeout_value
    else:
        qtime = apply_queue_timeout_bump_factor( qtime )

    if maxqtime:
        qtime = min( qtime, float(maxqtime) )

    return qtime


class BatchGroup:

    def __init__(self, testlist, groupid):
        ""
        self.groupid = groupid
        self.tlist = testlist

        self.size = None
        self.tsum = 0

    def getTests(self):
        ""
        return self.tlist.getTests()

    def getTime(self):
        ""
        return self.tsum

    def appendTest(self, tcase, timeval):
        ""
        if self.size is None:
            self.size = tcase.getSize()
        self.tlist.addTest( tcase )
        self.tsum += timeval

    def getTestList(self):
        ""
        return self.tlist

    def empty(self):
        ""
        return len( self.tlist.getTests() ) == 0

    def needNewGroup(self, size, timeval, tlimit):
        ""
        if len( self.tlist.getTests() ) > 0:
            if self.size != size or self.tsum + timeval > tlimit:
                return True

        return False

    def makeSortableKey(self):
        ""
        return ( self.tsum, self.size, self.groupid )


def compute_job_size( tlist, nodesize ):
    ""
    ppn,dpn = nodesize

    mxnp = 1
    mxnd = 0
    for tcase in tlist.getTests():
        np,nd = tcase.getSize()
        mxnp = max( np, mxnp )
        mxnd = max( nd, mxnd )

    nn = 1

    if ppn:
        assert type(ppn) == type(2) and ppn > 0
        numnd = int( mxnp/ppn )
        if mxnp%ppn != 0:
            numnd += 1
        nn = max( nn, numnd )

    if dpn and mxnd > 0:
        assert type(dpn) == type(2) and dpn > 0
        numnd = int( mxnd/dpn )
        if mxnd%dpn != 0:
            numnd += 1
        nn = max( nn, numnd )

    return nn,mxnp,mxnd


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


class ResultsHandler:

    def __init__(self, tlist):
        ""
        self.tlist = tlist

    def addResultsInclude(self, bjob):
        ""
        fname = get_relative_results_filename( self.tlist, bjob )
        self.tlist.addIncludeFile( fname )

    def completeResultsInclude(self, bjob):
        ""
        fname = get_relative_results_filename( self.tlist, bjob )
        self.tlist.completeIncludeFile( fname )

    def readJobResults(self, bjob, donetests):
        ""
        rfile = bjob.getJobObject().getTestList().getResultsFilename()

        if os.path.isfile( rfile ):

            try:
                tlr = TestListReader( self.tlist.getTestCaseFactory(), rfile )
                tlr.read()
                jobtests = tlr.getTests()
            except Exception:
                # file system race condition can cause corruption, ignore
                pass
            else:
                tL = self.tlist.copyResultsIfStateChange( jobtests.values() )
                donetests.extend( tL )

    def getReasonForNotRun(self, bjob):
        ""
        notrunL = []
        fallback_reason = 'batch number '+str(bjob.getJobID())+' did not run'

        for tcase in bjob.getJobObject().getTestList().getTests():
            reason = tcase.getBlockedReason()
            if reason:
                notrunL.append( (tcase,reason) )
            else:
                notrunL.append( (tcase,fallback_reason) )

        return notrunL

    def hasBlockingDependency(self, bjob):
        ""
        for tcase in bjob.getJobObject().getTestList().getTests():
            if tcase.isBlocked():
                return True
        return False

    def finalize(self):
        ""
        self.tlist.writeFinished()


def get_relative_results_filename( tlist_from, to_bjob ):
    ""
    fromdir = os.path.dirname( tlist_from.getResultsFilename() )

    tofile = to_bjob.getJobObject().getTestList().getResultsFilename()

    return pathutil.compute_relative_path( fromdir, tofile )


def check_make_directory( dirname, perms ):
    ""
    if dirname and dirname != '.':
        if not os.path.exists( dirname ):
            os.mkdir( dirname )
            perms.apply( dirname )


def check_set_outfile_permissions( bjob, perms, curtime ):
    ""
    ofile = bjob.getOutputFilename()
    if not bjob.outfileSeen() and os.path.exists( ofile ):
        perms.apply( ofile )
        bjob.setOutfileSeen( curtime )
