#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os
import sys
import time


class BatchJob:

    batchid_counter = 0

    def __init__(self):
        ""
        self.batchid = BatchJob.batchid_counter
        BatchJob.batchid_counter += 1

        self.jobscript = None
        self.outfile = None
        self.size = None
        self.jobid = None
        self.wrkdir = None

        self.tstart = None
        self.tseen = None
        self.tstop = None
        self.tcheck = None
        self.result = None

        self.jobobj = None

    def getBatchID(self): return self.batchid
    def getJobSize(self): return self.size

    def getJobScriptName(self): return self.jobscript

    def getOutputFilename(self): return self.outfile
    def outfileSeen(self): return self.tseen != None

    def getJobID(self): return self.jobid

    def getWorkDir(self): return self.wrkdir

    def getStartTime(self): return self.tstart
    def getCheckTime(self): return self.tcheck
    def getStopTime(self): return self.tstop

    def getResult(self): return self.result

    def setJobObject(self, obj):
        """
        an arbitrary object set and used by the client
        """
        self.jobobj = obj

    def getJobObject(self):
        ""
        return self.jobobj

    def setJobScriptName(self, scriptname):
        ""
        self.jobscript = scriptname

    def setOutputFilename(self, filename):
        ""
        self.outfile = filename

    def setWorkDir(self, dirpath):
        ""
        self.wrkdir = dirpath

    def setJobSize(self, jobsize):
        ""
        self.size = jobsize

    def setJobID(self, jobid):
        ""
        self.jobid = jobid

    def setStartTime(self, tstart):
        ""
        self.tstart = tstart

    def setOutfileSeen(self, tseen):
        ""
        self.tseen = tseen

    def setCheckTime(self, tcheck):
        ""
        self.tcheck = tcheck

    def setStopTime(self, tstop):
        ""
        self.tstop = tstop

    def setResult(self, result):
        ""
        self.result = result


class BatchJobHandler:

    def __init__(self, check_interval, check_timeout, batchitf, namer):
        ""
        self.check_interval = check_interval
        self.check_timeout = check_timeout
        self.batchitf = batchitf
        self.namer = namer

        self.todo  = {}
        self.submitted = {}
        self.stopped  = {}  # not in queue or shown as completed by the queue
        self.done  = {}  # job results have been processed

    def getNodeSize(self):
        ""
        return self.batchitf.getNodeSize()

    def createJob(self):
        ""
        bjob = BatchJob()

        fn = self.namer.getScriptPath( bjob.getBatchID() )
        bjob.setJobScriptName( fn )

        pout = self.namer.getOutputPath( bjob.getBatchID() )
        bjob.setOutputFilename( pout )

        bjob.setWorkDir( self.namer.getRootDir() )

        bid = bjob.getBatchID()
        self.todo[ bid ] = bjob

        return bjob

    def writeJobScript(self, batchjob, qtime, cmd):
        ""
        wrkdir = batchjob.getWorkDir()
        pout = batchjob.getOutputFilename()

        fn = batchjob.getJobScriptName()

        maxsize = batchjob.getJobSize()
        self.batchitf.writeJobScript( maxsize, qtime, wrkdir, pout, fn, cmd )

        return fn

    def startJob(self, batchjob):
        """
        returns batch system jobid and info string if successful, or None
        and an error message if unsuccessful
        """
        workdir = self.namer.getRootDir()
        scriptname = self.namer.getScriptPath( batchjob.getBatchID() )

        outfile = batchjob.getOutputFilename()
        jobid,out = self.batchitf.submitJob( workdir, outfile, scriptname )
        self.markJobStarted( batchjob, jobid )

        return jobid,out

    def numSubmitted(self):
        return len( self.submitted )

    def numStopped(self):
        return len( self.stopped )

    def numDone(self):
        return len( self.done )

    def getNotStarted(self):
        ""
        return self.todo.values()

    def getSubmitted(self):
        ""
        return self.submitted.values()

    def getStopped(self):
        ""
        return self.stopped.values()

    def getDone(self):
        ""
        return self.done.values()

    def markJobStarted(self, bjob, jobid):
        ""
        tm = time.time()
        bid = bjob.getBatchID()

        self._pop_job( bid )
        self.submitted[ bid ] = bjob

        bjob.setJobID( jobid )
        bjob.setStartTime( tm )

        # delay the first job check a little
        chktime = tm + max( 1, int( self.check_interval * 0.1 + 0.5 ) )
        bjob.setCheckTime( chktime )

    def markJobStopped(self, bjob):
        ""
        tm = time.time()
        bid = bjob.getBatchID()

        self._pop_job( bid )
        self.stopped[ bid ] = bjob

        bjob.setStopTime( tm )
        bjob.setCheckTime( tm )

    def markJobDone(self, bjob, result):
        ""
        bid = bjob.getBatchID()
        self._pop_job( bid )
        self.done[ bid ] = bjob
        bjob.setResult( result )

    def transitionStartedToStopped(self):
        ""
        doneL = []

        startlist = list( self.getSubmitted() )

        if len(startlist) > 0:
            jobidL = [ bjob.getJobID() for bjob in startlist ]
            statusD = self.batchitf.queryJobs( jobidL )
            tnow = time.time()
            for bjob in startlist:
                status = statusD[ bjob.getJobID() ]
                if self._check_stopped_job( bjob, status, tnow ):
                    doneL.append( bjob )

        return doneL

    def _check_stopped_job(self, bjob, queue_status, current_time):
        """
        If job 'queue_status' is empty (meaning the job is not in the queue),
        then return True if enough time has elapsed since the job started or
        the job output file has been seen.
        """
        started = False

        if not queue_status:
            elapsed = current_time - bjob.getStartTime()
            if elapsed > 30 or bjob.outfileSeen():
                started = True
                self.markJobStopped( bjob )

        return started

    def isTimeToCheck(self, bjob, current_time):
        ""
        return current_time > bjob.getCheckTime() + self.check_interval

    def resetCheckTime(self, bjob, current_time):
        """
        Resets the finish check time to the current time.  Returns
        False if the number of extensions has been exceeded.
        """
        tstop = bjob.getStopTime()
        if not tstop or current_time < tstop+self.check_timeout:
            bjob.setCheckTime( current_time )
            return True
        else:
            return False

    def checkBatchOutputForExit(self, outfile):
        """
        Returns True if the log file shows the batch job ran and finished.
        """
        return self.batchitf.checkForJobScriptExit( outfile )

    def markNotStartedJobsAsDone(self):
        ""
        jobs = []

        for bjob in list( self.getNotStarted() ):
            self.markJobDone( bjob, 'notrun' )
            jobs.append( bjob )

        return jobs

    def getUnfinishedJobIDs(self):
        ""
        stats = {}
        for bjob in self.getDone():
            bid = str( bjob.getBatchID() )
            if bjob.getResult() in ['notrun','notdone','fail']:
                stats.setdefault(bjob.getResult(),[]).append( bid )

        return stats

    def cancelStartedJobs(self):
        ""
        jL = [ bjob.getJobID() for bjob in self.getSubmitted() ]
        if len(jL) > 0:
            self.batchitf.cancelJobs( jL )

    def _pop_job(self, batchid):
        ""
        for qD in [ self.todo, self.submitted, self.stopped, self.done ]:
            if batchid in qD:
                return qD.pop( batchid )
        raise Exception( 'job id not found: '+str(batchid) )
