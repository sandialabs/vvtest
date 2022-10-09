#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import basename
import re

from .helpers import runcmd, format_shell_flags


jobpat = re.compile( r'Job\s+<\d+>\s+is submitted to' )

class BatchLSF:

    def __init__(self, **attrs):
        ""
        self.attrs = attrs
        self.xflags = format_shell_flags( attrs.get("submit_flags",None) )

    def header(self, size, qtime, outfile):
        ""
        nnodes = size[0]

        hdr = [ '#BSUB -W ' + minutes_of_time(qtime),
                '#BSUB -nnodes ' + str(nnodes),
                '#BSUB -o ' + outfile,
                '#BSUB -e ' + outfile ]

        if 'queue' in self.attrs:
            hdr.append( '#BSUB -q '+self.attrs['queue'] )

        if 'account' in self.attrs:
            # not sure what to do with "account" in bsub
            pass

        return hdr

    def submit(self, fname, outfile):
        """
        Submit 'fname' to the batch system. Should return
            ( jobid, submit command, raw output from submit command )
        where jobid is None if an error occurred.
        """
        jobname = basename(fname)
        cmdL = ['bsub', '-J', jobname] + self.xflags + [fname]

        x,cmd,out = runcmd( cmdL )

        # output should contain something like
        #    Job <68628> is submitted to default queue <normal>.
        jobid = None
        mat = jobpat.search( out )
        if mat is not None:
            try:
                jobstr = mat.group().split()[1]
                assert jobstr[0] == '<' and jobstr[-1] == '>'
                jobstr = jobstr.strip('<').strip('>')
                assert jobstr
                jobid = jobstr
            except Exception:
                pass

        return jobid,cmd,out

    def query(self, jobids):
        """
        Determine the state of the given job ids.  Should return
            ( status dictionary, query command, raw output )
        where the status dictionary maps
            job id -> "running" or "pending" (waiting to run)
        Exclude job ids that are not running or pending.
        """
        cmdL = ['bjobs', '-noheader', '-o', 'jobid stat']
        x,cmd,out = runcmd(cmdL)

        jobs = {}
        err = ''
        for line in out.splitlines():
            line = line.strip()
            # a line should be something like "68628   PEND"
            if line:
                sL = line.split()
                if len(sL) == 2:
                    jid,st = sL
                    if jid in jobids:
                        if st in ['PROV','RUN','USUSP']:
                            jobs[jid] = 'running'
                        elif st in ['PEND','PSUSP','WAIT']:
                            jobs[jid] = 'pending'
                else:
                    err = '\n*** unexpected bjobs output line: '+repr(line)

        return jobs,cmd,out+err

    def cancel(self, jobid):
        ""
        x,cmd,out = runcmd( [ 'bkill', str(jobid) ], echo=True )


def minutes_of_time( seconds ):
    ""
    return str( max( 1, int( float(seconds)/60. + 0.5 ) ) )
