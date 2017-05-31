#!/usr/bin/env python

import sys
sys.dont_write_bytecode = True
sys.excepthook = sys.__excepthook__
import os
import time
import subprocess
import threading
import pipes
import traceback

import runcmd
from runcmd import command, escape


"""
Functions in this file run commands in a subprocess, such that

    1. Output is always redirected to a log file
    2. Commands are run and managed in the background
    3. Commands can be executed on remote machines

The key functions are:

    run_job  : start a command in the background, and return a Job id
    poll_job : returns True if a job id has completed
    wait_job : waits for a job to complete, and returns the exit status
    wait_all : waits for multiple job ids
    run_wait : convenience function for run_job() plus wait_job()

Note also the command() and escape() functions imported from runcmd.py can
be useful in constructing the commands.

See the documentation in runcmd.py for how commands are specified to run_job(),
because they are the same.

Note: Look at the documentation below in the function "def _is_dryrun" for use
of the envronment variable COMMAND_DRYRUN for noop execution.
"""


def run_job( *args, **kwargs ):
    """
    Starts a job in the background and returns the job id.

    The shell command is formed from 'args', which must be length one or
    more.

    The keyword arguments are passed to the underlying Job object.
    """
    return RunJobs.inst.run_job( *args, **kwargs )


def poll_job( jobid ):
    """
    Returns True if the 'jobid' completed.  If the 'jobid' is unknown, an
    exception is raised.
    """
    return RunJobs.inst.poll( jobid )


def wait_job( jobid ):
    """
    Waits for the job to complete and returns the Job object.  The 'jobid'
    must exist otherwise an exception is raised.
    """
    return RunJobs.inst.wait( jobid )

def wait_all( *jobids, **kwargs ):
    """
    Waits for each job to complete and returns the list of completed Job
    objects.  If no 'jobids' are given, all background jobs are waited upon.
    The optional keyword argument 'poll_interval' can be used to specify the
    sleep time in seconds between polls.
    """
    return RunJobs.inst.wait_all( *jobids, **kwargs )


def run_wait( *args, **kwargs ):
    """
    Starts a job in the background, waits on the job, and returns the exit
    status.  The arguments are the same as for run_job().
    """
    jid = RunJobs.inst.run_job( *args, **kwargs )
    jb = wait_job( jid )
    x = jb.get( 'exit', None )
    return x


###########################################################################

class Job:
    """
    Required attributes are:

        command

    Optional attributes are:

        name
        machine
        chdir
        logdir
        timeout
        poll_interval
    """

    def __init__(self, **kwargs):
        """
        """
        self.lock = threading.Lock()

        self.attrD = {}
        for n,v in kwargs.items():
            self.set( n, v )
    
    def __bool__(self):
        """
        This allows a Job class instance to be cast (coerced) to True/False.
        That is, an instance will evaluate to True if the job exited and the
        exit status is zero.  If the job has not been run yet, or is still
        running, or the exit status is non-zero, then it evaluates to False.
        """
        x = self.get( 'exit', 1 )
        if type(x) == type(2) and x == 0:
            return True
        return False
    __nonzero__ = __bool__

    def has(self, attr_name):
        """
        Returns True if the given attribute name is defined.
        """
        self.lock.acquire()
        try:
            v = ( attr_name in self.attrD )
        finally:
            self.lock.release()
        return v

    def get(self, attr_name, *default):
        """
        Get an attribute name.  If a default is given and the attribute name
        is not set, then the default is returned.
        """
        self.lock.acquire()
        try:
            if len(default) > 0:
                v = self.attrD.get( attr_name, default[0] )
            else:
                v = self.attrD[attr_name]
        finally:
            self.lock.release()
        return v

    def clear(self, attr_name):
        """
        """
        assert attr_name and attr_name == attr_name.strip()
        self.lock.acquire()
        try:
            if attr_name in self.attrD:
                self.attrD.pop( attr_name )
        finally:
            self.lock.release()

    def set(self, attr_name, attr_value):
        """
        Set an attribute.  The attribute name cannot be empty or contain
        spaces at the beginning or end of the string.

        Some attribute names have checks applied to their values.
        """
        assert attr_name and attr_name == attr_name.strip()

        if attr_name in ["name","machine"]:
            assert attr_value and attr_value == attr_value.strip(), \
                'invalid "'+attr_name+'" value: "'+str(attr_value)+'"'
        elif attr_name == 'timeout':
            attr_value = int( attr_value )
        elif attr_name == 'poll_interval':
            attr_value = int( attr_value )
            assert attr_value > 0
        self.lock.acquire()
        try:
            self.attrD[attr_name] = attr_value
        finally:
            self.lock.release()

    def date(self):
        """
        Returns a formatted date string with no spaces.  If a 'date' attribute
        is not already set, the current time is used to create the date and
        set the 'date' attribute.
        """
        if not self.get( 'date', None ):
            self.set( 'date', time.strftime( "%a_%b_%d_%Y_%H:%M:%S_%Z" ) )
        return self.get( 'date' )

    def logname(self):
        """
        Returns the log file name for the job (without the directory).
        """
        if not self.get( 'logname', None ):
            n = self.get( 'name' )
            m = self.get( 'machine', None )
            if m: n += '-' + m
            n += '-' + self.date() + '.log'
            self.set( 'logname', n )
        return self.get( 'logname' )

    def logpath(self):
        """
        Returns the remote log file path (directory plus file name).
        """
        if not self.get( 'logpath', None ):
            logn = self.logname()
            cd = self.get( 'chdir', RunJobs.getDefault( 'chdir', None ) )
            logd = self.get( 'logdir', RunJobs.getDefault( 'logdir', cd ) )
            if logd: logf = os.path.join( logd, logn )
            else:    logf = logn
            self.set( 'logpath', logf )
        return self.get( 'logpath' )

    def jobid(self):
        """
        Returns a tuple that uniquely identifies this job.
        """
        return ( self.get( 'name', None ),
                 self.get( 'machine', None ),
                 self.date() )
    
    def finalize(self):
        """
        Create the launch command.  An exception is raised if the job is not
        well formed.  Returns the job id.
        """
        self.jobid()
        assert self.has( 'command' )
        assert self.logname()

    def execute(self):
        """
        If the job does not have a 'machine' attribute, the command is run
        directly as a subprocess with all output redirected to a log file.
        When the command finishes, the exit status is set in the 'exit'
        attribute and this function returns.

        If the job has a 'machine' attribute, the remotepython.py module is
        used to run the command on the remote machine in the background.
        Output from the remote command is redirected to a log file, and that
        log file is brought back every 'poll_interval' seconds.  When the
        remote command finishes, the exit status is set in the 'exit'
        attribute and this function returns.
        """
        self.clear( 'exit' )

        mach = self.get( 'machine', None )

        if not mach:
            self._run_wait()
        else:
            self._run_remote( mach )

    def _is_dryrun(self):
        """
        If the environment defines COMMAND_DRYRUN to an empty string or to the
        value "1", then this function returns True, which means this is a dry
        run and the job command should not be executed.

        If COMMAND_DRYRUN is set to a nonempty string, it should be a list of
        program basenames, where the list separator is a vertical bar, "|".
        If the basename of the job command program is in the list, then it is
        allowed to run (False is returned).  Otherwise True is returned and the
        command is not run.  For example,

            COMMAND_DRYRUN="scriptname.py|jobname"
        """
        v = os.environ.get( 'COMMAND_DRYRUN', None )
        if v != None:
            if v and v != "1":
                # use the job name, which is 'jobname' or basename of program
                n = self.get( 'name' )
                L = v.split('|')
                if n in L:
                    return False
            return True

        return False

    def _run_wait(self):
        """
        """
        ipoll = self.get( 'poll_interval',
                          RunJobs.getDefault( 'poll_interval' ) )
        timeout = self.get( 'timeout', RunJobs.getDefault( 'timeout' ) )

        cmd = self.get( 'command' )
        chd = self.get( 'chdir', RunJobs.getDefault( 'chdir' ) )
        logn = self.logname()

        cwd = os.getcwd()
        logfp = open( logn, 'w' )
        
        x = None
        try:
            if timeout == None:
                x = runcmd.run_command( cmd, echo=False,
                                             raise_on_failure=False,
                                             redirect=logfp.fileno(),
                                             chdir=chd )
            else:
                x = runcmd.run_timeout( cmd, timeout=timeout,
                                             echo=False,
                                             raise_on_failure=False,
                                             redirect=logfp.fileno(),
                                             poll_interval=ipoll,
                                             chdir=chd )
        finally:
            logfp.close()
        
        self.set( 'exit', x )

    def _run_remote(self, mach):
        """
        """
        timeout = self.get( 'timeout', RunJobs.getDefault( 'timeout' ) )
        cmd = self.get( 'command' )
        chd = self.get( 'chdir', RunJobs.getDefault( 'chdir' ) )
        sshexe = self.get( 'sshexe', RunJobs.getDefault( 'sshexe' ) )
        numconn = self.get( 'connection_attempts',
                            RunJobs.getDefault( 'connection_attempts' ) )

        logf = self.logpath()

        mydir = os.path.dirname( os.path.abspath( __file__ ) )
        rfile = os.path.join( mydir, 'runjob_remote.py' )

        from remotepython import RemotePython
        rmt = RemotePython( mach, sshexe=sshexe )
        rmt.addRemoteContent( filename=rfile )

        tprint( 'Connect machine:', mach )
        tprint( 'Remote command:', cmd )
        if chd:
            tprint( 'Remote dir:', chd )
        if timeout != None:
            tprint( 'Remote timeout:', timeout )

        if self._is_dryrun():
            # touch the local log file but do not execute the command
            fp = open( self.logname(), 'a' )
            fp.close()
            self.set( 'exit', 0 )

        else:
            T = self._connect( rmt, numconn )
            if T != None:
                sys.stderr.write( '[' + time.ctime() + '] ' + \
                    'Connect exception for jobid '+str(self.jobid())+'\n' + T[1] )
                sys.stderr.flush()
                raise Exception( "Could not connect to "+mach )

            try:
                rusr = rmt.timeout(30).x_evaluate( 'return os.getuid()' )

                rmt.timeout(30)
                rpid = rmt.x_background_command( cmd, logf,
                                                 chdir=chd,
                                                 timeout=timeout )

                time.sleep(2)

                self._monitor( rmt, rusr, rpid )

            finally:
                rmt.shutdown()

    def _connect(self, rmtpy, limit=10):
        """
        Tries to make a connection to the remote machine.  It tries up to
        'limit' times, sleeping 2**i seconds between each attempt.  Returns
        None if a connection was made, otherwise the return value from
        capture_traceback().
        """
        assert limit > 0

        for i in range(limit):
            if i > 0:
                time.sleep( 2**i )
            rtn = None
            try:
                rmtpy.timeout(30).connect()
            except:
                #raise  # uncomment this when debugging connections
                rtn = capture_traceback( sys.exc_info() )
            else:
                break

        return rtn

    def _monitor(self, rmtpy, rusr, rpid):
        """
        """
        ipoll = self.get( 'remote_poll_interval',
                          RunJobs.getDefault( 'remote_poll_interval' ) )
        xinterval = self.get( 'exception_print_interval',
                        RunJobs.getDefault( 'exception_print_interval' ) )
        timeout = self.get( 'timeout', RunJobs.getDefault( 'timeout' ) )

        if timeout:
            ipoll = min( ipoll, int( 0.45 * timeout ) )

        logn = self.logname()
        logf = self.logpath()

        tstart = time.time()
        texc1 = tstart
        texc2 = tstart

        pause = 2
        while True:

            if not rmtpy.isConnected():
                T = self._connect( rmtpy, 1 )
                t = time.time()
                if T != None and t - texc1 > xinterval:
                    sys.stderr.write( '[' + time.ctime() + '] ' + \
                            'Warning: remote connection failed for jobid ' + \
                            str( self.jobid() ) + '\n' + T[1] + \
                            'Exception ignored; continuing to monitor...\n' )
                    sys.stderr.flush()
                    texc1 = t

            if rmtpy.isConnected():

                elapsed = True
                try:

                    self.updateFile( rmtpy, logf, logn )

                    s = rmtpy.timeout(30).x_processes( pid=rpid, user=rusr,
                                                       fields='etime' )
                    elapsed = s.strip()

                    # TODO: add a check that the elapsed time agrees
                    #       approximately with the expected elapsed time
                    #       since the job was launched

                except:
                    xs,tb = capture_traceback( sys.exc_info() )
                    t = time.time()
                    if t - texc2 > xinterval:
                        sys.stderr.write( '[' + time.ctime() + '] ' + \
                            'Warning: exception monitoring jobid ' + \
                            str( self.jobid() ) + '\n' + tb + \
                            'Exception ignored; continuing to monitor...\n' )
                        sys.stderr.flush()
                        texc2 = t

                self.scanExitStatus( logn )

                if not elapsed:
                    # remote process id not found - assume it is done
                    break

            if timeout and time.time()-tstart > timeout:
                sys.stderr.write( 'Monitor process timed out at ' + \
                    str( int(time.time()-tstart) ) + ' seconds for jobid ' + \
                    str( self.jobid() ) + '\n' )
                sys.stderr.flush()
                # TODO: try to kill the remote process
                break

            time.sleep( pause )
            pause = min( 2*pause, ipoll )

    def updateFile(self, rmtpy, logfile, logname):
        """
        As 'logfile' on the remote side grows, the new part of the file is
        transferred back to the local side and appended to 'logname'.
        """
        from remotepython import _BYTES_
        
        small = int( self.get( 'getlog_small_file_size',
                        RunJobs.getDefault( 'getlog_small_file_size' ) ) )
        chunksize = int( self.get( 'getlog_chunk_size',
                        RunJobs.getDefault( 'getlog_chunk_size' ) ) )

        lcl_sz = -1
        if os.path.exists( logname ):
            lcl_sz = os.path.getsize( logname )

        rmt_sz = rmtpy.timeout(30).x_file_size( logfile )

        if lcl_sz != rmt_sz and rmt_sz >= 0:
            if rmt_sz < small or lcl_sz > rmt_sz or lcl_sz < 0.2*rmt_sz:
                # for small files, or if somehow the local file is larger than
                # the remote, or if not much of the file has been transferred
                # yet, just do a complete file transfer
                rmtpy.timeout(10*60).getFile( logfile, logname, preserve=True )

            else:
                # only transfer the end of the remote file that has not
                # been obtained yet (the first part of the file is assumed
                # to be the same between local and remote)
                off = lcl_sz
                fp = open( logname, 'ab' )
                rfp = None
                try:
                    # open the remote file
                    rmtpy.timeout(30)
                    mt, at, fm, rfp = rmtpy.x_open_file_read( logfile, off )

                    # get the tail of the file in chunks
                    while off < rmt_sz:
                        off2 = min( off + chunksize, rmt_sz )
                        buf = rmtpy.timeout(30).x_file_read( rfp, off2-off )
                        fp.write( _BYTES_( buf ) )
                        off = off2
                
                finally:
                    fp.close()
                    rmtpy.timeout(30).x_close_file( rfp )
                
                # match the date stamp and file mode
                os.utime( logname, (at,mt) )
                os.chmod( logname, fm )

    def scanExitStatus(self, logname):
        """
        Reads the end of the given log file name for "Subcommand exit:" and
        if found, the 'exit' attribute of this job is set to the value.
        """
        try:
            fp = None
            sz = os.path.getsize( logname )
            fp = open( logname, 'r' )
            if sz > 256:
                fp.seek( sz-256 )
            s = fp.read()
            fp.close() ; fp = None
            L = s.split( 'Subcommand exit:' )
            if len(L) > 1:
                x = L[-1].split( '\n' )[0].strip()
                if x.lower() == 'none':
                    # remote process timed out
                    x = None
                else:
                    try:
                        ix = int( x )
                    except:
                        # leave exit value as a string
                        pass
                    else:
                        # process exited normally
                        x = ix
                self.set( 'exit', x )

        except:
            if fp != None:
                fp.close()


#########################################################################

class RunJobs:
    
    def __init__(self):
        """
        """
        self.db = {}
        self.defaults = {
                            'poll_interval': 15,
                            'remote_poll_interval': 5*60,
                            'exception_print_interval': 15*60,
                            'timeout': None,
                            'chdir': None,
                            'sshexe': None,
                            'connection_attempts': 10,
                            'getlog_small_file_size': 5*1024,
                            'getlog_chunk_size': 512,
                        }

    inst = None  # a singleton RunJobs instance (set below)

    @staticmethod
    def jobDefault( attr_name, attr_value ):
        """
        Default values for job attributes can be set here.  Examples are
        'timeout' and 'poll_frequency'.
        """
        RunJobs.inst.defaults[ attr_name ] = attr_value

    @staticmethod
    def getDefault( attr_name, *args ):
        """
        Get the default value for a job attribute.
        """
        if len(args) > 0:
            return RunJobs.inst.defaults.get( attr_name, args[0] )
        return RunJobs.inst.defaults[ attr_name ]

    def insert(self, job, thr=None):
        """
        Insert the job into the database.
        """
        self.db[ job.jobid() ] = ( job, thr )

    def start(self, job):
        """
        Add the given job in the database and start the job execution in a
        separate thread.  Returns without waiting on the job.  The "done"
        message is printed at join time in poll() and wait().
        """
        # local function which serves as the thread entry point to run the
        # job; exceptions are caught, the 'exc' attribute set, and the
        # exception re-raised
        def threxec( jb ):
            try:
                jb.execute()
            except:
                xt,xv,xtb = sys.exc_info()
                xs = ''.join( traceback.format_exception_only( xt, xv ) )
                ct = time.ctime()
                jb.set( 'exc', '[' + ct + '] ' + xs )
                sys.stderr.write( '[' + ct + '] Exception: ' + xs + '\n' )
                raise

        t = threading.Thread( target=threxec, args=(job,) )
        t.setDaemon( True )  # so ctrl-C will exit the program
        self.insert( job, t )
        # set the thread name so exceptions include the job id
        if hasattr( t, 'setName' ):
            t.setName( str( job.jobid() ) )
        else:
            t.name = str( job.jobid() )
        t.start()

    def poll(self, jobid):
        """
        Tests for job completion.  Returns True if the underlying job thread
        has completed.
        """
        job,t = self.db[ jobid ]
        if t != None:
            if hasattr( t, 'is_alive' ):
                ia = t.is_alive()
            else:
                ia = t.isAlive()
            if not ia:
                t.join()
                self.db[ jobid ] = ( job, None )
                t = None
                print3( '<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<' )
                tprint( 'JobDone:', 'jobid='+str(job.jobid()),
                        'exit='+str(job.get('exit','')).strip(),
                        'exc='+str(job.get('exc','')).strip() )
        return t == None

    def wait(self, jobid):
        """
        Waits for the job to complete (for the underlying job thread to finish)
        then returns the Job object.
        """
        job,t = self.db[ jobid ]
        if t != None:
            t.join()
            self.db[ jobid ] = ( job, None )
            print3( '<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<' )
            tprint( 'JobDone:', 'jobid='+str(job.jobid()),
                    'exit='+str(job.get('exit','')).strip(),
                    'exc='+str(job.get('exc','')).strip() )
        return job

    def wait_all(self, *jobids, **kwargs):
        """
        Repeated poll of each job id, until all complete.  Returns the list
        of Jobs.
        """
        ipoll = kwargs.get( 'poll_interval',
                            RunJobs.getDefault( 'poll_interval' ) )

        if len(jobids) == 0:
            jobids = []
            for jid,T in self.db.items():
                if T[1] != None:
                    jobids.append( jid )

        jobD = {}
        while len(jobD) < len(jobids):
            for jid in jobids:
                if jid not in jobD:
                    if self.poll(jid):
                        jobD[jid] = self.wait(jid)
            if len(jobD) < len(jobids):
                time.sleep( ipoll )

        return [ jobD[jid] for jid in jobids ]

    def run_job(self, *args, **kwargs ):
        """
        A helper function that executes a job command.

        The Job.execute() is run in a separate thread and this function
        returns immediately with the job id.  Uncaught exceptions will be
        written to stderr by the normal threading behavior, and the thread
        will finish.
        """
        print3( '>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>' )
        tprint( 'RunJob:', args, kwargs )
        print3( ''.join( traceback.format_list(
                            traceback.extract_stack()[:-1] ) ).rstrip() )

        jb = Job()

        try:
            assert len(args) > 0, "empty or no command given"

            cmd,scmd = runcmd._assemble_command( *args )

            if 'name' in kwargs:
                jobname = kwargs['name']
            else:
                if type(cmd) == type(''):
                    jobname = os.path.basename( cmd.strip().split()[0] )
                else:
                    jobname = os.path.basename( cmd[0] )

            jb.set( 'name', jobname )
            jb.set( 'command', cmd )
            
            for n,v in kwargs.items():
                jb.set( n, v )

            jb.finalize()
            tprint( 'JobID: '+str(jb.jobid()) )

            # run in a thread and return without waiting
            self.start( jb )
        
        except:
            # catch all exceptions to avoid crashing the calling script;
            # instead, treat any issue as a job failure
            xs,tb = capture_traceback( sys.exc_info() )
            jb.set( 'exc', '[' + time.ctime() + '] ' + xs )
            sys.stderr.write( '['+time.ctime() +'] ' + \
                'Exception running jobid '+str( jb.jobid() )+'\n' + tb )
            sys.stderr.flush()
            self.insert( jb )  # make sure job is in the database

        # this just ensures that the next job will have a unique date stamp
        time.sleep(1)

        return jb.jobid()

# construct the RunJobs singleton instance
RunJobs.inst = RunJobs()


def capture_traceback( excinfo ):
    """
    This should be called in an except block of a try/except, and the argument
    should be sys.exc_info().  It extracts and formats the traceback for the
    exception.  Returns a pair ( the exception string, the full traceback ).
    """
    xt,xv,xtb = excinfo
    xs = ''.join( traceback.format_exception_only( xt, xv ) )
    tb = 'Traceback (most recent call last):\n' + \
         ''.join( traceback.format_list(
                        traceback.extract_stack()[:-2] +
                        traceback.extract_tb( xtb ) ) ) + xs
    return xs,tb


def print3( *args ):
    """
    Python 2 & 3 compatible print function.
    """
    s = ' '.join( [ str(x) for x in args ] )
    sys.stdout.write( s + '\n' )
    sys.stdout.flush()

def tprint( *args ):
    """
    Same as print3 but prefixes with the date.
    """
    s = ' '.join( [ str(x) for x in args ] )
    sys.stdout.write( '['+time.ctime()+'] ' + s + '\n' )
    sys.stdout.flush()
