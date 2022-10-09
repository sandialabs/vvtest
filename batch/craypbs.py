#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys

"""
This batch handler was used on the Cray XE machines.  Most commands are MOAB
but it has aspects of PBS.
"""

from .helpers import runcmd, format_shell_flags, get_node_size


class BatchCrayPBS:

    def __init__(self, **attrs):
        ""
        self.attrs = attrs
        self.xflags = format_shell_flags( attrs.get("submit_flags",None) )

    def header(self, size, qtime, outfile):
        ""
        nnodes = size[0]
        ppn,dpn = get_node_size( self.attrs )

        hdr = [ '#MSUB -l nodes='+str(nnodes)+':ppn='+str(ppn)+ \
                      ',walltime='+str(qtime),
                '#MSUB -j oe',
                '#MSUB -o '+outfile ]

        if 'queue' in self.attrs:
            hdr.append( '#MSUB -q '+self.attrs['queue'] )

        if 'account' in self.attrs:
            hdr.append( '#MSUB -A '+self.attrs['account'] )

        return hdr

    def submit(self, fname, outfile):
        """
        Submit 'fname' to the batch system. Should return
            ( jobid, submit command, raw output from submit command )
        where jobid is None if an error occurred.
        """
        jobname = os.path.basename(fname)
        cmdL = ['msub', '-N', jobname] + self.xflags + [fname]

        x,cmd,out = runcmd( cmdL )

        # output should contain something like the following
        #    12345.ladmin1 or 12345.sdb
        jobid = None
        jobstr = out.strip()
        if jobstr and len( jobstr.splitlines() ) == 1:
            sL = jobstr.split()
            if len(sL) == 1 and sL[0]:
                jobid = sL[0]

        return jobid,cmd,out

    def query(self, jobids):
        """
        Determine the state of the given job ids.  Should return
            ( status dictionary, query command, raw output )
        where the status dictionary maps
            job id -> "running" or "pending" (waiting to run)
        Exclude job ids that are not running or pending.
        """
        x,cmd,out = runcmd( ['showq'] )

        jobs = {}
        err = ''
        for line in out.strip().splitlines():
            line = line.strip()
            # a line should be something like "123457.sdb n/a Idle foobar"
            if line:
                sL = line.split()
                if len(sL) >= 4:
                    jid,st = sL[0],sL[2]
                    if jid in jobids:
                        if st in ['Running']:
                            jobs[jid] = 'running'
                        elif st in ['Deferred','Idle']:
                            jobs[jid] = 'pending'
                else:
                    err = '\n*** unexpected showq output line: '+repr(line)

        return jobs,cmd,out+err
