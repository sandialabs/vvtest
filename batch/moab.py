#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys

"""
This batch handler was written for Trinity, but it may also work for general
MOAB systems.
"""

from .helpers import runcmd, format_shell_flags


class BatchMOAB:

    def __init__(self, **attrs):
        """
        The 'variation' keyword can be

            knl : Cray KNL partition
        """
        self.attrs = attrs
        self.variation = attrs.get( 'variation', '' )
        self.xflags = format_shell_flags( attrs.get("submit_flags",None) )

    def header(self, size, qtime, outfile):
        ""
        nnodes = size[0]

        if self.variation == 'knl':
            hdr = '#MSUB -l nodes='+str(nnodes)+':knl\n'
            hdr += '#MSUB -los=CLE_quad_cache\n'
        else:
            hdr = '#MSUB -l nodes='+str(nnodes) + '\n'
        hdr += '#MSUB -l walltime='+str(qtime) + '\n' + \
               '#MSUB -j oe' + '\n' + \
               '#MSUB -o '+outfile + '\n'

        return hdr

    def submit(self, fname, outfile):
        """
        Submit 'fname' to the batch system. Should return
            ( jobid, submit command, raw output from submit command )
        where jobid is None if an error occurred.
        """
        queue = self.attrs.get( 'queue', None )
        account = self.attrs.get( 'account', None )

        cmdL = ['msub']+self.xflags
        if queue != None: cmdL.extend(['-q',queue])
        if account != None: cmdL.extend(['-A',account])
        cmdL.extend(['-o', outfile])
        cmdL.extend(['-j', 'oe'])
        cmdL.extend(['-N', os.path.basename(fname)])
        cmdL.append(fname)

        x,cmd,out = runcmd( cmdL )

        # output should contain something like the following
        #    12345.ladmin1 or 12345.sdb
        jobid = None
        jobstr = out.strip()
        if jobstr:
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
            # a line should be something like
            #     123456.ladmin1 field1 Deferred field3
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
