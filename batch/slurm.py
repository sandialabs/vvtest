#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys

from .helpers import format_shell_flags, runcmd


class BatchSLURM:

    def __init__(self, **attrs):
        ""
        self.attrs = attrs
        self.xflags = format_shell_flags( self.attrs.get("submit_flags",None) )

    def header(self, size, qtime, outfile):
        ""
        nnodes = size[0]

        hdr = [ '#SBATCH --time=' + HMSformat(qtime),
                '#SBATCH --nodes=' + str(nnodes),
                '#SBATCH --output=' + outfile,
                '#SBATCH --error=' + outfile ]

        if 'queue' in self.attrs:
            hdr.append( '#SBATCH --partition='+self.attrs['queue'] )
        if 'account' in self.attrs:
            hdr.append( '#SBATCH --account='+self.attrs['account'] )
        if 'QoS' in self.attrs:
            hdr.append( '#SBATCH --qos='+self.attrs['QoS'] )
        if self.xflags:
            # place on one line so a specification like "-L gpfs" will work
            hdr.append( '#SBATCH {0}'.format( ' '.join( self.xflags ) ) )

        return hdr

    def submit(self, fname, outfile):
        """
        Submit 'fname' to the batch system. Should return
            ( jobid, submit command, raw output from submit command )
        where jobid is None if an error occurred.
        """
        x,cmd,out = runcmd( ['sbatch', fname] )

        # output should contain something like the following
        #    sbatch: Submitted batch job 291041
        jobid = None
        i = out.find( "Submitted batch job" )
        if i >= 0:
            L = out[i:].split()
            if len(L) > 3 and L[3]:
                jobid = L[3]

        return jobid,cmd,out

    def query(self, jobids):
        """
        Determine the state of the given job ids.  Should return
            ( status dictionary, query command, raw output )
        where the status dictionary maps
            job id -> "running" or "pending" (waiting to run)
        Exclude job ids that are not running or pending.
        """
        cmdL = ['squeue', '--noheader', '-o', '%i %t', '--clusters=all']
        x,cmd,out = runcmd( cmdL )

        jobs = {}
        err = ''
        for line in out.splitlines():
            # a line should be something like "16004759 PD"
            line = line.strip()
            if line:
                L = line.split()
                if len(L) == 2:
                    jid,st = L
                    if jid in jobids:
                        if st in ['R']:
                            jobs[jid] = 'running'
                        elif st in ['PD']:
                            jobs[jid] = 'pending'
                else:
                    err = '\n*** unexpected squeue output line: '+repr(line)

        return jobs,cmd,out+err

    def cancel(self, jobid):
        ""
        x,cmd,out = runcmd( ['scancel',str(jobid),'--clusters=all'], echo=True )


def HMSformat( nseconds ):
    """
    Formats 'nseconds' in H:MM:SS format.  If the argument is a string, then
    it checks for a colon.  If it has a colon, the string is untouched.
    Otherwise it assumes seconds and converts to an integer before changing
    to H:MM:SS format.
    """
    if type(nseconds) == type(''):
        if ':' in nseconds:
            return nseconds
    nseconds = int(nseconds)
    nhrs = int( float(nseconds)/3600.0 )
    t = nseconds - nhrs*3600
    nmin = int( float(t)/60.0 )
    nsec = t - nmin*60
    if nsec < 10: nsec = '0' + str(nsec)
    else:         nsec = str(nsec)
    if nhrs == 0:
        return str(nmin) + ':' + nsec
    else:
        if nmin < 10: nmin = '0' + str(nmin)
        else:         nmin = str(nmin)
    return str(nhrs) + ':' + nmin + ':' + nsec
