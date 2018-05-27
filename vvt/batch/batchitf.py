#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
sys.dont_write_bytecode = True
sys.excepthook = sys.__excepthook__
import os
import time
import subprocess
import traceback


"""
This file defines a programmatic interface into batch systems, such as SLURM,
LSF, etc.

Defined here is an abstract interface, called BatchInterface.  Derived classes
interact with a given batch system by submitting script files and querying
their status using shell commands.

A job script file is composed like this:

    <shebang>  : like #!/bin/bash -l
    <header>   : batch system directives
    <begin>    : startup shell commands
    <commands> : job shell commands
    <finish>   : informational job completion shell commands
"""



#############################################################################

class BatchInterface:

    def __init__(self):
        ""
        self.ppn = None

        self.jobs = {}  # jobid -> BatchJob

        self.timeouts = {
                'script'  : 5*60,
                'missing' : 10*60,
                'complete': 60,
                'logcheck': 60,
            }

    def addJob(self, job):
        """
        """
        self.jobs[ job.getJobId() ] = job

    def removeJob(self, jobid):
        """
        """
        self.jobs.pop( jobid )

    def setProcessorsPerNode(self, ppn):
        ""
        self.ppn = ppn

    def getProcessorsPerNode(self, *default):
        ""
        if len(default) > 0 and self.ppn == None:
            return default[0]
        return self.ppn

    def computeNumNodes(self, num_cores, cores_per_node=None):
        """
        Returns minimum number of compute nodes to fit the requested
        number of cores.
        """
        ppn = self.getProcessorsPerNode()
        return compute_num_nodes( num_cores, cores_per_node, ppn )

    def setTimeout(self, name, timeout_seconds):
        """
        The 'name' must be one of

            script : once the queue shows the job done, wait this long before
                     giving up on the script to have a stop date
            missing : if the job never shows up in the queue, this is the time
                      after the submit date when it will be marked done
            complete : if the job never shows up in the queue, this is the time
                       after the script done date when it will be marked done
            logcheck : minimum time between opening the job log file to parse
                       the script dates (this is to avoid disk thrashing)
        """
        assert name in ['script','missing','complete','logcheck']
        self.timeouts[name] = timeout_seconds

    def getTimeout(self, name):
        ""
        return self.timeouts[name]

    def writeScriptHeader(self, job, fileobj):
        """
        """
        raise NotImplementedError( "Method writeScriptHeader()" )

    def submit(self, job):
        """
        If the submission fails, then the job ID will be None.  The submit
        stdout and stderr are set either way.
        """
        try:
            jobid,out,err = self.submitJobScript( job )

        except Exception:
            err = traceback.format_exc()
            out = ''
            jobid = None

        if jobid == None:
            err += '\n*** submit appears to have failed ***\n'
        else:
            job.setJobId( jobid )
            self.addJob( job )

        job.setQueueDates( submit=time.time() )
        job.setSubmitOutput( out=out, err=err )

    def submitJobScript(self, job):
        """
        Return jobid, stdout, stderr with 'jobid' being None if the submission
        fails.
        """
        raise NotImplementedError( "Method submit()" )

    def queryQueue(self, jobtable):
        """
        """
        raise NotImplementedError( "Method queryQueue()" )

    def cancel(self, job_list=None):
        ""
        raise NotImplementedError( "Method cancel()" )

    def poll(self):
        """
        """
        jqtab = JobQueueTable()
        self.queryQueue( jqtab )

        for jid,job in list( self.jobs.items() ):

            self.updateBatchJobResults( job, jqtab )

            if job.isFinished():
                self.removeJob( jid )

    def updateBatchJobResults(self, job, jqtab):
        """
        """
        if not job.isFinished():

            curtime = time.time()

            self.updateJobScriptDates( job, curtime )
            self.updateJobQueueDates( job, jqtab, curtime )
            self.updateJobFinished( job, curtime )

    def updateJobScriptDates(self, job, curtime):
        ""
        start,stop,done = job.getScriptDates()

        last_check = get_parse_script_date( job )
        tm = self.getTimeout( 'logcheck' )

        if not stop and curtime-last_check > tm:

            start,stop = self.parseScriptDates( job.getLogFileName() )

            job.setScriptDates( start=start, stop=stop )

            set_parse_script_date( job, curtime )

    def updateJobQueueDates(self, job, jqtab, curtime):
        ""
        dt,was_pending,was_running,dt,dt = job.getQueueDates()

        jid = job.getJobId()

        if jqtab.hasJob( jid ):

            st = jqtab.getState( jid )
            start = jqtab.getStartDate( jid )
            tused = jqtab.getTimeUsed( jid )

            if st == 'running':
                if not start: start = curtime
                job.setQueueDates( run=start )

            elif st == 'pending':
                job.setQueueDates( pending=curtime )

            else:
                if st == 'complete':
                    if start and tused:
                        tm = start+tused
                    else:
                        tm = curtime
                    job.setQueueDates( complete=tm )

                job.setQueueDates( done=curtime )

        elif was_pending or was_running:
            job.setQueueDates( done=curtime )

    def updateJobFinished(self, job, curtime):
        ""
        start,stop,sdone = job.getScriptDates()
        sub,pend,run,comp,qdone = job.getQueueDates()

        if stop:
            job.setScriptDates( done=curtime )

        else:
            tm = self.getTimeout( 'script' )
            if qdone and curtime-qdone > tm:
                job.setScriptDates( done=curtime )

        if not ( pend or run or comp or qdone ):
            if sdone:
                tm = self.getTimeout( 'complete' )
                if curtime-sdone > tm:
                    job.setQueueDates( done=curtime )
            else:
                tm = self.getTimeout( 'missing' )
                if curtime-sub > tm:
                    job.setQueueDates( done=curtime )

    def writeScriptFile(self, job):
        ""
        batname = job.getBatchFileName()

        fp = open( batname, 'w' )
        try:
            self.writeScriptShebang( job, fp )
            self.writeScriptHeader( job, fp )
            self.writeScriptBegin( job, fp )
            fp.write( '\n' + job.getRunCommands() + '\n' )
            self.writeScriptFinish( job, fp )

        finally:
            fp.close()

    def writeScriptShebang(self, job, fileobj):
        """
        """
        fileobj.write( '#!/bin/bash -l\n' )

    def writeScriptBegin(self, job, fileobj):
        """
        """
        lineprint( fileobj,
            'echo "SCRIPT START DATE: `date`"',
            'env',
            'echo "UNAME: `uname -a`"' )

        rdir = job.getRunDirectory()
        if rdir:
            lineprint( fileobj,
                'echo "cd '+rdir+'"',
                'cd "'+rdir+'" || exit 1' )

        lineprint( fileobj, '' )

    def writeScriptFinish(self, job, fileobj):
        """
        """
        lineprint( fileobj,
            '',
            'echo "SCRIPT STOP DATE: `date`"' )

    def parseScriptDates(self, filename):
        ""
        start = None
        stop = None

        if os.path.exists( filename ):

            fp = open( filename, 'r' )
            try:
                started = False
                line = fp.readline()
                while line:

                    if not started:
                        L = line.split( 'SCRIPT START DATE:', 1 )
                        if len(L) == 2:
                            tm = parse_date_string( L[1].strip() )
                            if tm:
                                start = tm
                            started = True

                    L = line.split( 'SCRIPT STOP DATE:', 1 )
                    if len(L) == 2:
                        tm = parse_date_string( L[1].strip() )
                        if tm:
                            stop = tm

                    line = fp.readline()

            finally:
                fp.close()

        return start, stop


#############################################################################

class JobQueueTable:

    def __init__(self):
        ""
        self.jobinfo = {}  # job id -> [ state, subdate, startdate, timeused ]

    def setJobInfo(self, jobid, state, startdate, timeused):
        ""
        assert state in ['pending','running','complete','done']
        self.jobinfo[ jobid ] = [ state, startdate, timeused ]

    def numJobs(self):
        ""
        return len( self.jobinfo )

    def hasJob(self, jobid):
        ""
        return jobid in self.jobinfo

    def getState(self, jobid):
        ""
        return self.jobinfo[jobid][0]

    def getStartDate(self, jobid):
        ""
        return self.jobinfo[jobid][1]

    def getTimeUsed(self, jobid):
        ""
        return self.jobinfo[jobid][2]


def run_shell_command( cmd ):
    ""
    p = subprocess.Popen( cmd, shell=True,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE )

    out,err = p.communicate()

    if sys.version_info[0] > 2:
        if out != None:
            out = out.decode()
        if err != None:
            err = err.decode()

    return p.returncode, out, err


def get_parse_script_date( job ):
    """
    The last time the job log file was parsed for the start/stop dates.
    """
    if hasattr( job, 'parse_script_date' ):
        return job.parse_script_date
    return 0


def set_parse_script_date( job, timevalue ):
    ""
    job.parse_script_date = timevalue


def lineprint( fileobj, *lines ):
    """
    """
    for line in lines:
        fileobj.write( line + '\n' )


def parse_variant( variant_string ):
    """
    Splits the given string of the form

        "key=value key=value ..."

    into a dict and returns it.
    """
    D = {}

    for s in variant_string.strip().split():

        L = s.split('=',1)

        if len(L) == 1:
            D[s] = None
        else:
            D[ L[0] ] = L[1]

    return D


def compute_num_nodes( requested_num_cores,
                       requested_cores_per_node,
                       platform_ppn ):
    """
    Returns minimum number of compute nodes to fit the requested number of
    cores.  If 'requested_num_cores' is less than one, then one is assumed.
    The 'platform_ppn' is used as the number of cores per node unless the
    'requested_cores_per_node' value is non-None.  If both 'platform_ppn'
    and 'requested_cores_per_node' are None, then one is returned.
    """
    if requested_cores_per_node != None:
        ppn = int( requested_cores_per_node )
    elif platform_ppn != None:
        ppn = int( platform_ppn )
    else:
        return 1

    assert ppn > 0

    requested_num_cores = max( 1, int(requested_num_cores) )

    n = int( requested_num_cores / ppn )
    r = int( requested_num_cores % ppn )

    if r == 0:
        return n
    else:
        return n+1


days_of_week = 'sun mon tue wed thu fri sat'.split() + \
    'sunday monday tuesday wednesday thursday friday saturday'.split()
months_of_year = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()
time_zones = 'EST EDT CST CDT MST MDT PST PDT'.split()

def parse_date_string( datestr ):
    """
    """
    tm = None

    try:
        fmt = ''
        val = ''

        L = datestr.split()
        i = 0
        while i < len(L):
            s = L[i]

            if s.lower() in days_of_week:
                pass

            elif s in months_of_year:
                fmt += ' %b'
                val += ' '+s
                i += 1
                s = L[i]
                fmt += ' %d'
                val += ' '+s

            elif s in time_zones:
                fmt += ' %Z'
                val += ' '+s

            elif ':' in s:
                sL = s.split(':')
                if len(sL) == 3:
                    fmt += ' %H:%M:%S'
                    val += ' '+s
                elif len(sL) == 2:
                    fmt += ' %H:%M'
                    val += ' '+s
            else:
                try:
                    yr = int(s)
                    if yr > 1970 and yr < 3000:
                        fmt += ' %Y'
                        val += ' '+s
                except Exception:
                    pass

            i += 1

        if fmt:
            tup = time.strptime( val, fmt )
            tm = time.mktime( tup )

    except Exception:
        pass

    return tm


def format_time_to_HMS( num_seconds ):
    """
    Formats 'num_seconds' in H:MM:SS format.  If the argument is a string,
    then it checks for a colon.  If it has a colon, the string is returned
    untouched. Otherwise it assumes seconds and converts to an integer before
    changing to H:MM:SS format.
    """
    if type(num_seconds) == type(''):
        if ':' in num_seconds:
            return num_seconds

    secs = int(num_seconds)

    nhrs = secs // 3600
    secs = secs % 3600
    nmin = secs // 60
    nsec = secs % 60

    hms = str(nhrs)+':'
    if nmin < 10: hms += '0'
    hms += str(nmin)+':'
    if nsec < 10: hms += '0'
    hms += str(nsec)

    return hms


class AutoPoller:
    """
    """

    def __init__(self, poll_function, poll_interval):
        ""
        assert poll_interval > 0

        self.pollfunc = poll_function
        self.ipoll = poll_interval

        self.stop_event = threading.Event()

        self.thr = threading.Thread( target=self.pollLoop )
        self.thr.daemon = True
        self.thr.start()

    def stop(self):
        ""
        self.stop_event.set()
        self.thr.join()

    def pollLoop(self):
        ""
        tstart = time.time()

        while True:

            if self.isStopped():
                break

            if time.time() - tstart > self.ipoll:
                self.pollfunc()
                tstart = time.time()

            time.sleep(1)

    def isStopped(self):
        ""
        if hasattr( self.stop_event, 'is_set' ):
            stopped = self.stop_event.is_set()
        else:
            stopped = self.stop_event.isSet()

        return stopped

