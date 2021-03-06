#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
sys.dont_write_bytecode = True
sys.excepthook = sys.__excepthook__
import os
import traceback
import re
import glob
import time
import subprocess
import getopt
import signal
import perms
import shutil

import timeutils


help_string = \
"""
USAGE
    trigger.py [OPTIONS] -r <directory> [jobs [jobs ...] ]

SYNOPSIS

    This is a job script launch and logging tool.  Job scripts specify a
launch time of day, day of week, etc using a comment at the top of the script.
When a job is launched, all output is logged.  The arguments to this script
are job files and/or directories containing the job files, and can be glob
patterns.

Run this script in a cron table, something like this:

    1-59/5 * * * * /path/runner --exlusive-id myname /path/trigger.py \ 
                                -r /log/path /path/jobs_dir

OPTIONS

  -r <directory> : run directory (required); this is the directory that
                   contains the main log file as well as the individual job
                   log directories

  -g <integer> : granularity in seconds (default 15); this is the time
                 between job file scans and possible job launches

  -Q <integer> : quit after this number of seconds; used in unit testing

  -E <integer> : error reset value, in hours.  Job trigger syntax errors are
                 logged, so without a throttle, the same error can flood the
        log file.  To avoid this, the same error will not be logged repeatedly.
        After the number of hours given by the -E option, however, the same
        error will be logged again.  The default is one hour.

  --group <unix group name> : group name for log file creation; also causes
                              group read permissions to be set

TRIGGER SYNTAX:

    Job scripts are only executed if a JOB TRIGGER specification is provided
at the top of the script.  One or more lines must exist with this syntax:

# JOB TRIGGER <specification string>

The parsing for job triggers will stop at the first non-comment, non-empty
line.  So the job trigger specification must occur before such a line.

To run every day at one or more specified times, use:

    <time> [, <time> [, ...] ]

where the <time> syntax can be a number of hours past midnight, such as "1" or
"18".  It can be a 12 hour time, such as "1am" or "1:30am" or "6:30pm".  It can
be military time, such as "1:00" or "18:30" or "22:00".

To run on a particular day of the week, use:

    <DOW> [, <DOW> [, ...] ] [ <time> [, <time> , ...] ]

where <DOW> is a day of the week, such as "Monday", "monday", "Mon", "mon".
A time of day specification is optional, and if not given, 5 seconds past
midnight is assumed.

To run every hour on the hour, use:

    hourly

To run every hour at a specified number of minutes past the hour, use:

    hourly <minute> [, <minute> [, ...] ]

where <minute> is an integer number of minutes past the hour.  For example,
"hourly 0, 20, 40" will trigger on the hour, 20 minutes past the hour, and 40
minutes past the hour.

To run on the first day of each month, use:

    monthly [ <time> ]

If a <time> specification is not given, then it will run at 5 seconds past
midnight.

To run on the first day of the week of each month, use:

    monthly <DOW> [ <time> ]

For example, "monthly Mon" will run on the first Monday of each month at 5
seconds past midnight.  And "monthly sun 1am" will run on the first Sunday of
each month at one AM.

Note that each job is executed with PYTHONPATH appended with the directory
containing this file.  That way, jobs can easily import utility modules.
"""


DEFAULT_GRANULARITY = 15
DEFAULT_ERROR_REPEAT = 1  # hours


def main( arglist ):
    ""
    optL,argL = getopt.getopt( arglist, 'hr:g:Q:E:', ['help','group='] )

    optD = {}
    for n,v in optL:
        if n in ['-g','-Q']:
            v = int( v )
            assert v > 0
        optD[n] = v

    if '-h' in optD or '--help' in optD:
        print3( help_string.rstrip() )
        return

    assert '-r' in optD, "the -r option is required"

    mainloop( optD, argL )


# use signals to implement a timeout mechanism
class TimeoutException(Exception): pass
def timeout_handler( signum, frame ):
    raise TimeoutException( "timeout" )

class TriggerError( Exception ):
    pass


def mainloop( optD, argL ):
    """
    """
    logdir = os.path.abspath( optD['-r'] )
    logfile = os.path.join( logdir, 'trigger.log' )

    redir = Redirect( logfile, append=True )

    printlog( 'startup', 'mach='+os.uname()[1]+' pid='+str( os.getpid() ),
                         'argv='+repr( sys.argv ) )

    signal.signal( signal.SIGALRM, timeout_handler )

    tgrain = optD.get( '-g', DEFAULT_GRANULARITY )
    tlimit = optD.get( '-Q', None )
    v = optD.get( '-E', DEFAULT_ERROR_REPEAT )
    erreset = int( max( 0, float(v) ) * 60*60 )

    if len(argL) == 0:
        argL = ['.']
    argL = [ os.path.abspath(p) for p in argL ]

    rjobs = FileJobs( logdir, argL, erreset, optD.get( '--group', None ) )

    try:
        append_to_python_path( mydir )

        tlimit_0 = time.time()
        while tlimit == None or time.time()-tlimit_0 < tlimit:

            # use alarm to timeout the file and subprocess work (resilience)
            signal.alarm( 2*tgrain )
            rjobs.checkRun( tgrain )
            signal.alarm(0)

            time.sleep( tgrain )

    except Exception:
        # all exceptions are caught and logged, before returning (exiting)
        traceback.print_exc()
        printlog( 'exception', str( sys.exc_info()[1] ) )
        rjobs.waitChildren()

    redir.close()


#########################################################################

class FileJobs:
    
    def __init__(self, logdir, jobsrcs, error_reset, log_group):
        """
        """
        self.logdir = logdir
        self.jobsrcs = jobsrcs
        self.erreset = error_reset
        self.group = log_group

        self.recent = {}  # maps job filename to launch time
        self.jobs = {}  # maps log directory to subprocess.Popen instance
        self.errD = {}  # maps job files to dictionaries, which map error
                        # strings to time stamps

    def checkRun(self, granularity):
        """
        Scans the root job source directories for files named job_*.py and
        for each one calls self.processFile().
        """
        self.reapChildren()

        for src in self.jobsrcs:
            if os.path.isdir( src ):
                src = os.path.join( src, 'job_*.py' )
            for f in glob.glob( src ):
                curtm = int( time.time() )
                self.pruneJobs( curtm, granularity )
                self.pruneErrors( curtm, granularity, f )
                self.processFile( curtm, granularity, f )

    def pruneJobs(self, tm, granularity):
        """
        Jobs that ran more than 3 grains in the past are removed from the
        recent job dict.  Those jobs will then be allowed to run again
        depending on their trigger specifications.
        """
        D = {}
        for jfile,jt in self.recent.items():
            if jt > tm - 3*granularity:
                D[jfile] = jt
        self.recent = D

    def pruneErrors(self, curtm, granularity, jfile):
        """
        """
        jD = self.errD.get( jfile, None )
        if jD != None:
            try:
                ft = os.path.getmtime( jfile )
            except Exception:
                self.errD.pop( jfile )
            else:
                if ft + granularity > curtm:
                    # recent enough time stamp, so reset history for the file
                    self.errD.pop( jfile )
                else:
                    # prune entries for this file if they are too old
                    newD = {}
                    for err,tm in jD.items():
                        if tm + self.erreset > curtm:
                            newD[ err ] = tm
                    self.errD[ jfile ] = newD

    def processFile(self, curtm, granularity, jfile):
        """
        Reads the given job file for the JOB TRIGGER specification, and if
        time, the job is run using self.launchFile().
        """
        joberrD = self.errD.get( jfile, None )
        if joberrD == None:
            joberrD = {}
            self.errD[ jfile ] = joberrD

        try:
            if jfile not in self.recent:

                trigL,loghandling = parse_trigger_specifications( jfile )

                for trig in trigL:
                    trigtm = next_trigger_time( trig, curtm )

                    if trigtm and trigtm < curtm + 2*granularity:
                        self.launchFile( jfile, trig, loghandling )
                        self.recent[jfile] = time.time()
                        break

        except TimeoutException:
            raise
        except Exception:
            err = str( sys.exc_info()[1] )
            if err not in joberrD:
                traceback.print_exc()
                printlog( 'exception', 'while processing file '+jfile,
                                       'exc='+err )
                joberrD[ err ] = time.time()

    def launchFile(self, jobfile, trigspec, loghandling):
        """
        Executes the given root job file as a subprocess.
        """
        remove_old_job_logs( self.logdir, jobfile, loghandling )

        jdir,logfp = open_log_file_for_write( self.logdir, jobfile, self.group )

        try:
            printlog( 'launch', 'trigger='+trigspec,
                                'file='+jobfile,
                                'logdir='+jdir )

            p = subprocess.Popen( [sys.executable,jobfile],
                                  stdout=logfp.fileno(),
                                  stderr=subprocess.STDOUT )

            self.jobs[ jdir ] = ( jobfile, p )

        finally:
            logfp.close()

        # ensure that each new job gets a different time stamp
        time.sleep( 1 )

    def reapChildren(self):
        """
        Checks each subprocess for completion.
        """
        pD = {}
        for d in self.jobs.keys():
            jf,p = self.jobs[d]
            x = p.poll()
            if x == None:
                pD[d] = ( jf, p )
            else:
                printlog( 'finish', 'exit='+str(x),
                                    'file='+jf,
                                    'logdir='+d )
        self.jobs = pD

    def waitChildren(self):
        """
        Waits on each subprocess for completion.
        """
        for d in self.jobs.keys():
            jf,p = self.jobs[d]
            x = p.wait()
            printlog( 'finish', 'exit='+str(x),
                                'file='+jf,
                                'logdir='+d )
        self.jobs = {}


trigger_pattern = re.compile( ' *# *JOB TRIGGER *[=:]' )
jobhandle_pattern = re.compile( ' *# *JOB LOG HANDLING *[=:]' )


def parse_trigger_specifications( filename ):
    ""
    trigL = []
    loghandling = {}

    with open( filename, 'rt' ) as fp:

        line = fp.readline()
        while line:
            line = line.strip()

            trigmatch = trigger_pattern.match( line )
            logmatch = jobhandle_pattern.match( line )

            if trigmatch:
                specstr = line[trigmatch.end():].split('#')[0].strip()
                trigL.append( specstr )

            elif logmatch:
                specstr = line[logmatch.end():].split('#')[0].strip()
                specD = parse_job_handling_specification( specstr )
                loghandling.update( specD )

            elif line and not line.startswith('#'):
                break

            elif line.startswith( '#TRIGGER_TEST_HANG_READ=' ):
                time.sleep( int( line.split( '=' )[1] ) )

            line = fp.readline()

    return trigL, loghandling


def parse_job_handling_specification( specstr ):
    ""
    specD = {}

    for spec in specstr.split(','):

        name,val = parse_name_equal_value_specifiction( spec )

        if name == 'count':
            try:
                specD[name] = int( val )
            except Exception as e:
                raise TriggerError( 'invalid "count" value: '+str(e) )

        elif name == 'age':
            age = parse_age_specification( val )
            specD[name] = time.time() - age

        else:
            raise TriggerError( 'unknown specification name: "'+name+'"' )

    return specD


def parse_name_equal_value_specifiction( spec ):
    ""
    nvL = spec.strip().split('=',1)
    if len(nvL) != 2:
        raise TriggerError( 'invalid specification: '+str(spec) )

    name = nvL[0].strip()
    val = nvL[1].strip()
    if not name or not val:
        raise TriggerError( 'invalid specification: '+str(spec) )

    return name,val


def parse_age_specification( agestr ):
    ""
    if agestr.endswith( 'day' ) or agestr.endswith( 'days' ):
        age = float( agestr.split('day')[0] ) * 24*60*60

    elif agestr.endswith( 'month' ) or agestr.endswith( 'months' ):
        age = float( agestr.split('month')[0] ) * 30*24*60*60

    elif agestr.endswith( 'year' ) or agestr.endswith( 'years' ):
        age = float( agestr.split('year')[0] ) * 365*24*60*60

    else:
        raise TriggerError( 'unknown age unit: "'+agestr+'"' )

    return age


def make_root_log_name( logpath, jobfile ):
    ""
    name = os.path.basename( jobfile )
    logroot = os.path.join( logpath, name+'_' )
    return logroot


def remove_old_job_logs( logpath, jobfile, specD ):
    ""
    rootdir = make_root_log_name( logpath, jobfile )

    fL = []
    for dn in glob.glob( rootdir+'*' ):
        fL.append( ( os.path.getmtime( dn ), dn ) )

    fL.sort()

    remove_old_job_logs_by_count( fL, specD.get( 'count', None ) )
    remove_old_job_logs_by_age( fL, specD.get( 'age', None ) )


def remove_old_job_logs_by_count( fL, cnt ):
    ""
    if cnt and cnt > 0:
        while len( fL ) > cnt:
            tm,dn = fL.pop( 0 )
            remove_path( dn )


def remove_old_job_logs_by_age( fL, age ):
    ""
    if age:
        while len( fL ) > 0:
            tm,dn = fL[ 0 ]
            if tm < age:
                fL.pop( 0 )
                remove_path( dn )
            else:
                break


def remove_path( pathname ):
    ""
    try:
        if os.path.islink( pathname ):
            os.remove( pathname )
        elif os.path.isdir( pathname ):
            shutil.rmtree( pathname )
        else:
            os.remove( pathname )

    except Exception as e:
        raise TriggerError( 'unable to remove path: "'+pathname+'", '+str(e) )


def open_log_file_for_write( logpath, jobfile, group ):
    ""
    date = time.strftime( "%a_%b_%d_%Y_%H:%M:%S_%Z" )
    joblogdir = make_root_log_name( logpath, jobfile ) + date

    if group:
        # do not mask out rx for group
        os.umask( os.umask( 0o000 ) & 0o727 )

    os.mkdir( joblogdir )

    if group:
        perms.apply( joblogdir, group, 'g+rX' )

    os.chdir( joblogdir )

    fp = open( 'log.txt', 'w' )

    if group:
        perms.apply( 'log.txt', group, 'g+r' )

    return joblogdir, fp


def next_trigger_time( spec, curtm ):
    """
    Given a string specification 'spec', this returns seconds since epoch
    for the next trigger event.  If no event will occur on the current day or
    the next day, then None is returned.

    See the help page for the syntax.
    """
    tm = None
    if spec:

        # current midnight and day of week
        epoch0 = timeutils.chop_midnight( curtm )
        dow0 = timeutils.day_of_week( curtm )

        # upcoming midnight and day of week
        epoch1 = timeutils.chop_midnight( epoch0 + 26*60*60 )
        dow1 = timeutils.day_of_week( epoch0 + 26*60*60 )

        sL = [ s.strip() for s in spec.split(',') ]
        s0 = sL[0].split()[0].lower()

        if s0 == 'hourly':
            epoch_hr0 = timeutils.chop_hour( curtm )
            epoch_hr1 = timeutils.chop_hour( epoch_hr0 + 65*60 )

            # a comma after hourly is optional, so handle both cases here
            L = sL[0].split( None, 1 )
            if len(L) > 1:
                sL[0] = L[1].strip()
            else:
                sL.pop( 0 )
            if len(sL) == 0:
                sL.append( '0' )  # default is on the hour

            for s in sL:
                try:
                    m = int( float(s) * 60 + 0.5 )
                    # TODO: could also allow minutes:seconds format here
                except Exception:
                    raise Exception( 'bad number of minutes syntax: '+s )

                tm = check_time( curtm, epoch_hr0 + m, tm )
                tm = check_time( curtm, epoch_hr1 + m, tm )

        elif s0 == 'monthly':

            d0 = timeutils.first_day_of_month( epoch0+10*60*60 )
            d1 = timeutils.first_day_of_month( d0 + 45*24*60*60 + 10*60*60 )

            # a comma after monthly is optional, so handle both cases here
            L = sL[0].split( None, 1 )
            if len(L) > 1:
                sL[0] = L[1].strip()
            else:
                sL.pop( 0 )

            dowL = []
            sL = recurse_dow( sL, dowL )
            dow = None
            if len(dowL) == 1:
                dow = dowL[0]
                if dow not in timeutils.daysofweek:
                    raise Exception( "unknown day of week: "+dowL[0] )
            elif len(dowL) > 1:
                raise Exception( "only zero or one day-of-week allowed: "+spec )

            tod = 5
            if len(sL) > 1:
                raise Exception( "only zero or one time-of-day allowed: "+spec )
            elif len(sL) == 1:
                try:
                    tod = timeutils.seconds_since_midnight( sL[0] )
                except Exception:
                    raise Exception( 'bad time syntax: '+sL[0] )

            if dow == None:
                tm = check_time( curtm, d0+tod, tm )
                tm = check_time( curtm, d1+tod, tm )

            else:
                t = timeutils.next_day_of_week( dow, d0 + 10*60*60 )
                tm = check_time( curtm, t+tod, tm )
                t = timeutils.next_day_of_week( dow, d1 + 10*60*60 )
                tm = check_time( curtm, t+tod, tm )

        else:
            # determine the days of week for which this specification is valid
            dowL = []
            sL = recurse_dow( sL, dowL )
            if len(dowL) == 0:
                # no spec means no restriction, so include all days of week
                dowL = timeutils.daysofweekL

            if len(sL) == 0:
                if dow0 in dowL:
                    # 5 seconds past midnight
                    tm = check_time( curtm, epoch0 + 5, tm )
                if dow1 in dowL:
                    tm = check_time( curtm, epoch1 + 5, tm )

            else:
                for s in sL:
                    try:
                        t = timeutils.seconds_since_midnight( s )
                    except Exception:
                        raise Exception( 'bad time syntax: '+s )

                    if dow0 in dowL:
                        tm = check_time( curtm, epoch0 + t, tm )
                    if dow1 in dowL:
                        tm = check_time( curtm, epoch1 + t, tm )

    return tm


def check_time( curtm, newtm, prevtm ):
    """
    If 'newtm' is >= 'curtm', then the minimum of 'newtm' and 'prevtm' is
    returned.
    """
    if newtm >= curtm:
        if prevtm == None:
            return newtm
        return min( prevtm, newtm )
    return prevtm


def recurse_dow( sL, dowL ):
    """
    Removes leading days-of-the-week strings from the list 'sL' and adds them
    to the 'dowL' list.  Returns the remaining strings in a list.  The days
    in 'dowL' are abbreviated and lower case.
    """
    if len(sL) > 0:
        s = sL.pop(0)
        if s[:3].lower() in timeutils.daysofweek:
            dowL.append( s[:3].lower() )
            iL = s.split( None, 1 )
            if len(iL) > 1:
                s = iL[1]
                return recurse_dow( [s]+sL, dowL )

            return recurse_dow( []+sL, dowL )

        return [s]+sL

    return []


#########################################################################

def print3( *args ):
    ""
    sys.stdout.write( ' '.join( [ str(x) for x in args ] ) + '\n' )
    sys.stdout.flush()


def printlog( *args ):
    """
    Prints the date to stdout followed by the arguments in a human readable
    format but also one that can be read by the logreadline() function.
    """
    s = '['+time.ctime()+'] '+str(len(args))
    if len(args) > 0: s += ' '+str(args[0])+':'
    if len(args) > 1: s += ' '+str(args[1])
    for v in args[2:]:
        s += '\n    '+str(v)
    sys.stdout.write( s + '\n' )
    sys.stdout.flush()


readpat = re.compile( r'\[(Mon|Tue|Wed|Thu|Fri|Sat|Sun)([^]]*20[0-9][0-9]\])+?' )

def logreadline( fp ):
    """
    Given an open file pointer, this will read one printlog() line (which may
    contain multiple newlines).  Returns a list

        [ seconds since epoch, title, arg1, arg2, ... ]

    or None if there are no more lines in the file.
    """
    val = None

    try:
        line = None
        while True:

            if line == None:
                line = fp.readline()
            if not line:
                break

            val = None
            try:
                line = line.rstrip()
                m = readpat.match( line )
                if m != None:
                    L = line[m.end():].strip().split( ' ', 1 )
                    n = int( L.pop(0) )
                    assert n < 1000  # if large, probably corruption
                    ts = line[:m.end()].strip().strip('[').strip(']')
                    tm = time.mktime( time.strptime( ts ) )
                    val = [ tm ]
                    if n > 0:
                        aL = L[0].split( ':', 1 )
                        val.append( aL[0].strip() )
                        if n > 1:
                            val.append( aL[1].strip() )
            except Exception:
                val = None
            line = None

            if val != None:
                if n > 2:
                    for i in range(n-2):
                        line = fp.readline()
                        assert line
                        if line.startswith( '    ' ):
                            val.append( line[4:].rstrip() )
                        else:
                            val = None
                            break
                if val != None:
                    break
    except Exception:
        val = None

    return val


class Redirect:
    """
    A convenience class to redirect the current process's stdout & stderr
    to a file.
    """

    def __init__(self, filename, append=False):
        """
        If the 'append' value is True, the filename is appended rather than
        overwritten.  Call the close() method to stop the redirection.
        """
        self.orig_fname = filename
        self.fname = filename

        mode = "w"
        if append: mode = "a"

        self.filep = open( self.fname, mode )
        self.save_stdout_fd = os.dup(1)
        self.save_stderr_fd = os.dup(2)
        os.dup2( self.filep.fileno(), 1 )
        os.dup2( self.filep.fileno(), 2 )

    def close(self):
        """
        Call this to stop the redirection and reset stdout & stderr.
        """
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2( self.save_stdout_fd, 1 )
        os.dup2( self.save_stderr_fd, 2 )
        os.close( self.save_stdout_fd )
        os.close( self.save_stderr_fd )
        self.filep.close()


def append_to_python_path( dirpath ):
    ""
    pypath = os.environ.get( 'PYTHONPATH', None )
    if pypath == None:
        os.environ['PYTHONPATH'] = dirpath
    else:
        os.environ['PYTHONPATH'] = pypath+':'+dirpath


#########################################################################

mydir = os.path.dirname( os.path.abspath( __file__ ) )

if __name__ == "__main__":
    main( sys.argv[1:] )
