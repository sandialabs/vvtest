#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import basename

from .helpers import format_shell_flags, runcmd


class BatchFLUX:

    def __init__(self, **attrs):
        ""
        self.attrs = attrs
        self.xflags = format_shell_flags( self.attrs.get("submit_flags",None) )

    def header(self, size, qtime, outfile):
        ""
        nnodes = size[0]

        # flux wants minutes (although there are other formats)
        m = qtime//60
        if qtime%60 > 0:
            m += 1

        hdr = [ '#FLUX: --time-limit=' + str(m),
                '#FLUX: --nodes=' + str(nnodes),
                '#FLUX: --output=' + outfile,
                '#FLUX: --error=' + outfile ]

        if 'queue' in self.attrs:
            hdr.append( '#FLUX: --queue='+self.attrs['queue'] )
        if 'account' in self.attrs:
            hdr.append( '#FLUX: --setattr=system.bank='+self.attrs['account'])
        if self.xflags:
            # place on one line so a specification like "-L gpfs" will work
            hdr.append( '#FLUX: {0}'.format( ' '.join( self.xflags ) ) )

        return hdr

    def submit(self, fname, outfile):
        """
        Submit 'fname' to the batch system, and return
            ( jobid, submit command, raw output from submit command )
        where jobid is None if an error occurred or the jobid could
        not be parsed from stdout.
        """
        jobname = basename(fname)
        x,cmd,out = runcmd( ['flux', 'batch', '--job-name', jobname, fname] )

        # output should simply contain the jobid
        jobid = None
        L = out.strip().split()
        if len(L) == 1 and L[0]:
            jobid = L[0]

        return jobid,cmd,out

    def query(self, jobids):
        """
        Determine the state of the given job ids.  Returns
            ( status dictionary, query command, raw output )
        where the status dictionary maps
            job id -> "running" or "pending" (waiting to run)
        Job ids that are not running or pending are excluded from
        the return dictionary..
        """
        cmdL = ['flux', 'jobs', '--no-header', '--format={id} {state}']
        x,cmd,out = runcmd( cmdL )

        jobs = {}
        err = ''
        for line in out.splitlines():
            # a line should be something like "ƒM7Zq9AKHno RUN"
            line = line.strip()
            if line:
                L = line.split()
                if len(L) == 2:
                    jid,st = L
                    if jid in jobids:
                        if st.lower() in ['run','cleanup']:
                            jobs[jid] = 'running'
                        elif st.lower() in ['depend','priority','sched']:
                            jobs[jid] = 'pending'
                else:
                    err = '\n*** unexpected flux output line: '+repr(line)

        return jobs,cmd,out+err

    def cancel(self, jobid):
        ""
        x,cmd,out = runcmd( ['flux', 'cancel', str(jobid)], echo=True )
