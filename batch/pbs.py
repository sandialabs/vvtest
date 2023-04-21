#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys

from .helpers import runcmd, format_shell_flags, get_node_size


class BatchPBS:

    def __init__(self, **attrs):
        """
        The 'variation' attribute causes the header to be created a little
        differently.  The only known value is:

          "select" : The -lselect= option is used instead of -lnodes= such as
                       -l select=<num nodes>:mpiprocs=<ppn>:ncpus=<ppn>
                     where <num nodes> is the number of nodes needed and <ppn>
                     is the number of processors per node.

        By default, the -lnodes method is used.
        """
        self.attrs = attrs
        self.ppn,self.dpn = get_node_size( attrs )
        self.variation = attrs.get( 'variation', None )
        self.xflags = format_shell_flags( attrs.get("submit_flags",None) )

    def header(self, size, qtime, outfile):
        ""
        nnodes = size[0]

        if self.variation != None and self.variation == "select":
            hdr = '#PBS -l select=' + str(nnodes) + \
                   ':mpiprocs=' + str(self.ppn) + ':ncpus='+str(self.ppn)+'\n'
        else:
            hdr = '#PBS -l nodes=' + str(nnodes) + ':ppn=' + str(self.ppn)+'\n'

        hdr = hdr +  '#PBS -l walltime=' + HMSformat(qtime) + '\n' + \
                     '#PBS -j oe\n' + \
                     '#PBS -o ' + outfile + '\n'

        return hdr


    def submit(self, fname, outfile):
        """
        Submit 'fname' to the batch system. Should return
            ( jobid, submit command, raw output from submit command )
        where jobid is None if an error occurred.
        """
        queue = self.attrs.get( 'queue', None )
        account = self.attrs.get( 'account', None )

        cmdL = ['qsub']+self.xflags
        if queue != None: cmdL.extend(['-q',queue])
        if account != None: cmdL.extend(['-A',account])
        cmdL.extend(['-o', outfile])
        cmdL.extend(['-j', 'oe'])
        cmdL.append(fname)

        x,cmd,out = runcmd( cmdL )

        # output should contain something like the following
        #    12345.ladmin1
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
        x,cmd,out = runcmd( ['qstat'] )

        jobs = {}
        err = ''
        for line in out.strip().splitlines():
            line = line.strip()
            # a line should be something like
            #     123456.ladmin1 field1 field2 field3 Q field6
            # A real-life example from 2023-04-10:
            #Job id            Name             User              Time Use S Queue
            #----------------  ---------------- ----------------  -------- - -----
            #9932285.foospam-* hello_world.sh   mswan                    0 W serial
            if line:
                sL = line.split()
                if len(sL) >= 6:
                    jid,st = sL[0],sL[4]
                    # the output from qstat may return a truncated job id,
                    # so match the beginning of the incoming 'jobids' strings
                    for j in jobids:
                        is_truncated = (jid[-1] == "*")
                        if j == jid or (is_truncated and j.startswith(jid[:-1])):
                            if st in ['R']:
                                jobs[j] = 'running'
                            elif st in ['Q']:
                                jobs[j] = 'pending'
                            break
                else:
                    err = '\n*** unexpected qstat output line: '+repr(line)

        return jobs,cmd,out+err


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
