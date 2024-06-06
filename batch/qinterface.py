#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os
import sys

try:
    from shlex import quote
except Exception:
    from pipes import quote

from .batchfactory import construct_batch_system


class BatchQueueInterface:

    def __init__(self, node_size, attrs={}):
        """
        The 'attrs' must have a "batchsys" key with one of these values:

            slurm    : standard SLURM system
            lsf      : LSF, such as the Sierra platform
            craypbs  : for Cray machines running PBS (or PBS-like)
            moab     : for Cray machines running Moab (may work in general)
            pbs      : standard PBS system
            subprocs : simulate batch processing with subprocesses
        """
        self.batch = None
        self.attrs = dict( attrs )

        assert node_size[0] and node_size[0] > 0
        self.nodesize = node_size

        assert 'batchsys' in self.attrs
        self.batch = construct_batch_system( self.attrs )

        self.clean_exit_marker = "queue job finished cleanly"

    def getNodeSize(self):
        ""
        return self.nodesize

    def checkForJobScriptExit(self, outfile):
        """
        Returns True if 'outfile' exists and contains the clean exit marker.
        """
        clean = False

        try:
            # compute file seek offset, and open the file
            sz = os.path.getsize( outfile )
            off = max(sz-512, 0)
            fp = open( outfile, 'rt' )
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

    def writeJobScript(self, size, queue_time, workdir, qout_file,
                             filename, command):
        ""
        qt = self.attrs.get( 'walltime', queue_time )

        bufL = [ '#!/bin/bash' ]

        bhead = self.batch.header( size, qt, qout_file )
        if type(bhead) == type(''):
            bufL.append( bhead )
        else:
            bufL.extend( list(bhead) )

        bufL.extend( [ '# attributes: '+str(self.attrs),
                       '',
                       'cd '+quote(workdir)+' || exit 1' ] )
        if qout_file:
            bufL.append( 'touch '+quote(qout_file) + ' || exit 1' )

        bufL.extend( [ '',
                       'echo "job start time = `date`"',
                       'echo "job time limit = '+str(queue_time)+'"' ] )

        bufL.extend( [ '',
                       command,
                       '',
                       'echo "'+self.clean_exit_marker+'"' ] )

        with open( filename, 'wt' ) as fp:
            fp.write( '\n'.join( bufL ) + '\n' )

    def submitJob(self, workdir, outfile, scriptname):
        """
        returns batch system jobid and info string if successful, or None
        and an error message if unsuccessful
        """
        cwd = os.getcwd()
        os.chdir( workdir )
        try:
            jobid,cmd,out = self.batch.submit( scriptname, outfile )
        finally:
            os.chdir( cwd )

        if jobid is None:
            out = "{0}\n{1}\n{2}".format( cmd, out,
                "Batch submission failed or could not parse output to get job id" )
        else:
            out = "Job script {0} submitted with id {1}".format(scriptname, jobid)

        return jobid,out

    def queryJobs(self, jobidL):
        """
        returns a dict mapping jobid to a string, where
            <empty>   means the jobid is either not in the queue or is completed
            "running" means it is currently running
            "pending" means it is waiting to run
        """
        non_None = extract_non_None_job_ids( jobidL )

        jobD,cmd,out = self.batch.query( non_None )

        for jobid in jobidL:
            if jobid not in jobD:
                jobD[jobid] = ''

        return jobD

    def cancelJobs(self, jobidL):
        ""
        jids = list( filter( lambda jid: jid is not None, jobidL ) )
        if len(jids) > 0 and hasattr( self.batch, 'cancel' ):
            print ( "\nCancelling jobs: {0}".format(" ".join(str(_) for _ in jids)) )
            for jid in jids:
                self.batch.cancel( jid )


def extract_non_None_job_ids( jobidL ):
    ""
    non_None = []

    for jobid in jobidL:
        if jobid is not None:
            non_None.append( jobid )

    return non_None
