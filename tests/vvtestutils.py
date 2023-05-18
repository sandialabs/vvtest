#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
import os
import shlex
import time
import fnmatch
import signal
import subprocess
import unittest
import shutil
import platform
try:
    from shlex import quote
except Exception:
    from pipes import quote

from os.path import dirname, abspath
from os.path import join as pjoin

import testutils as util


testsrcdir = dirname( abspath( sys.argv[0] ) )
topdir = dirname( testsrcdir )
trigdir = pjoin( topdir, 'trig' )

# imports for core vvtest modules are relative to the "vvt" directory
sys.path.insert( 0, topdir )

# import paths for shared modules
sys.path.insert( 1, trigdir )

cfgdir = os.path.join( topdir, 'config' )

vvtest_file = pjoin( topdir, 'vvtest' )
resultspy = pjoin( topdir, 'libvvtest', 'results.py' )

import libvvtest.testspec as testspec
import libvvtest.testcase as testcase
import libvvtest.teststatus as teststatus
from libvvtest.runconfig import RuntimeConfig
from libvvtest.userplugin import UserPluginBridge, import_user_plugin
import libvvtest.paramset as paramset
from libvvtest.testlist import TestList
from libvvtest.execlist import TestExecList
import libvvtest.testcreator as testcreator
from libvvtest.scanner import TestFileScanner
from libvvtest.wordexpr import WordExpression
from libvvtest.depend import connect_dependency
from libvvtest.tcfactory import TestCaseFactory
from libvvtest.location import Locator


##########################################################################

import functools

windows = platform.uname()[0].lower().startswith('win')

def not_windows(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not windows:
            return func(*args, **kwargs)
    return wrapper


class vvtestTestCase( unittest.TestCase ):

    def setUp(self, cleanout=True):
        ""
        util.setup_test( cleanout )

        # for batch tests
        os.environ['VVTEST_BATCH_CHECK_INTERVAL'] = '1'
        os.environ['VVTEST_BATCH_CHECK_TIMEOUT'] = '5'
        os.environ['VVTEST_BATCH_SLEEP_LENGTH'] = '1'

        # force the results files to be written locally for testing;
        # it is used in vvtest when handling the --save-results option
        os.environ['TESTING_DIRECTORY'] = os.getcwd()

        self.savePATH = os.environ.get( 'PATH', None )

    def tearDown(self):
        ""
        if self.savePATH is None:
            if 'PATH' in os.environ:
                del os.environ['PATH']
        else:
            os.environ['PATH'] = self.savePATH


def copy_vvtest_into_directory( dest_dir ):
    """
    copies vvtest and makes symlinks to required source code directories
    """
    shutil.copy( vvtest_file, dest_dir+'/vvtest' )

    for fn in os.listdir( topdir ):
        if fn != 'vvtest':
            os.symlink( topdir+'/'+fn, dest_dir+'/'+fn )


def core_platform_name():
    """
    Returns either Darwin or Linux, depending on the current platform.
    """
    plat = platform.uname()[0].lower()
    if plat.startswith( 'darwin' ):
        return 'Darwin'
    elif plat.startswith( 'win' ):
        return 'Windows'
    else:
        return 'Linux'


def launch_vvtest_then_terminate_it( *cmd_args, **options ):
    ""
    signum = options.pop( 'signum', signal.SIGTERM )
    seconds_before_signaling = options.pop( 'seconds_before_signaling', 4 )
    logfilename = options.pop( 'logfilename', 'run.log' )
    batch = options.pop( 'batch', False )
    addverbose = options.pop( 'addverbose', True )

    cmdL = vvtest_command_line( *cmd_args, batch=batch, addverbose=addverbose )

    fp = open( logfilename, 'w' )
    try:
        print ( cmdL )
        pop = subprocess.Popen( cmdL,
                    stdout=fp.fileno(), stderr=fp.fileno(),
                    preexec_fn=lambda:os.setpgid(os.getpid(),os.getpid()) )

        time.sleep( seconds_before_signaling )

        os.kill( -pop.pid, signum )

        pop.wait()

    finally:
        fp.close()

    return util.readfile( logfilename )


def interrupt_test_hook( batch=False, count=None, signum=None, qid=None ):
    ""
    valL = []
    if count != None:
        valL.append( "count="+str(count) )
    if signum != None:
        valL.append( "signum="+signum )
    if qid != None:
        valL.append( "qid="+str(qid) )

    if batch:
        spec = "batch:" + ','.join( valL )
    else:
        spec = "run:" + ','.join( valL )

    return spec


def interrupt_vvtest_run( vvtest_args, count=None, signum=None, qid=None ):
    ""
    spec = interrupt_test_hook( count=count, signum=signum, qid=qid )
    return run_vvtest_with_hook( vvtest_args, spec )


def interrupt_vvtest_batch( vvtest_args, count=None, signum=None ):
    ""
    spec = interrupt_test_hook( batch=True, count=count, signum=signum )
    return run_vvtest_with_hook( vvtest_args, spec, batch=True )


def run_vvtest_with_hook( vvtest_args, envspec, batch=False ):
    ""
    cmdL = vvtest_command_line( vvtest_args, batch=batch )

    os.environ['VVTEST_UNIT_TEST_SPEC'] = envspec
    try:
        x,out = util.runcmd( cmdL, raise_on_error=False )
    finally:
        del os.environ['VVTEST_UNIT_TEST_SPEC']

    return x, out


def clean_sys_path_for_testing():
    """
    Use like this:

        savepath = clean_sys_path_for_testing()
        try:
            # do stuff with sys.path
        finally:
            sys.path[:] = savepath
    """
    save = list( sys.path )

    len1 = len( sys.path )
    len0 = len1+1
    while len0 != len1:
        for i,path in enumerate(sys.path):
            # TODO: the platform_plugin.py mechanism was deprecated in Jan 2022
            if os.path.exists( pjoin( path, 'idplatform.py' ) ) or \
               os.path.exists( pjoin( path, 'platform_plugin.py' ) ):
                sys.path.pop(i)
                break
        len0 = len1
        len1 = len( sys.path )

    return save


class clean_sys_path:
    """
    with clean_sys_path():
        pass
    """

    def __init__(self):
        ""
        self.savepath = clean_sys_path_for_testing()

    def __enter__(self):
        ""
        pass

    def __exit__(self, type, value, traceback):
        ""
        sys.path[:] = self.savepath


def remove_results():
    """
    Removes all TestResults from the current working directory.
    If a TestResults directory is a soft link, the link destination is
    removed as well.
    """
    for f in os.listdir('.'):
        if f.startswith( 'TestResults.' ):
            if os.path.islink(f):
                dest = os.readlink(f)
                print ( 'rm -rf ' + dest )
                util.fault_tolerant_remove( dest )
                print ( 'rm ' + f )
                os.remove(f)
            else:
                print ( 'rm -rf ' + f )
                util.fault_tolerant_remove( f )


class VvtestCommandRunner:

    def __init__(self, cmdL):
        ""
        self.cmdL = cmdL

    def run(self, **options):
        ""
        quiet          = options.get( 'quiet',          False )
        raise_on_error = options.get( 'raise_on_error', True )
        chdir          = options.get( 'chdir',          None )

        verb = 1
        if quiet: verb = 0

        x,out = util.runcmd( self.cmdL, chdir=chdir,
                             raise_on_error=False, verbose=verb )

        if x == 0:
            print ( out )

        self.x = x
        self.out = out
        self.cntD = parse_vvtest_counts( out )
        self.testdates = None

        self.plat = get_platform_name( out )

        self.rdir = get_results_dir( out )
        if self.rdir:
            if not os.path.isabs( self.rdir ):
                if chdir:
                    self.rdir = abspath( pjoin( chdir, self.rdir ) )
                else:
                    self.rdir = abspath( self.rdir )
        elif chdir:
            self.rdir = abspath( chdir )
        else:
            self.rdir = os.getcwd()

        assert x == 0 or not raise_on_error, \
            'vvtest command returned nonzero exit status: '+str(x)

    def assertCounts(self, total=None, finish=None,
                           npass=None, diff=None,
                           fail=None, timeout=None,
                           notrun=None, notdone=None,
                           skip=None ):
        ""
        if total   != None: assert total   == self.cntD['total']
        if npass   != None: assert npass   == self.cntD['npass']
        if diff    != None: assert diff    == self.cntD['diff']
        if fail    != None: assert fail    == self.cntD['fail']
        if timeout != None: assert timeout == self.cntD['timeout']
        if notrun  != None: assert notrun  == self.cntD['notrun']
        if notdone != None: assert notdone == self.cntD['notdone']
        if skip    != None: assert skip    == self.cntD['skip']

        if finish != None:
            assert finish == self.cntD['npass'] + \
                             self.cntD['diff'] + \
                             self.cntD['fail']

    def resultsDir(self):
        ""
        return self.rdir

    def platformName(self):
        ""
        return self.plat

    def grepTestLines(self, shell_pattern):
        ""
        return greptestlist( shell_pattern, self.out )

    def countTestLines(self, shell_pattern):
        ""
        return len( self.grepTestLines( shell_pattern ) )

    def grepLines(self, shell_pattern):
        ""
        return util.greplines( shell_pattern, self.out )

    def countLines(self, shell_pattern):
        ""
        return len( self.grepLines( shell_pattern ) )

    def greplogs(self, shell_pattern, testid_pattern=None):
        ""
        xL = util.findfiles( 'execute.log', self.rdir )
        if testid_pattern != None:
            xL = filter_logfile_list_by_testid( xL, testid_pattern )
        return util.grepfiles( shell_pattern, *xL )

    def countGrepLogs(self, shell_pattern, testid_pattern=None):
        ""
        return len( self.greplogs( shell_pattern, testid_pattern ) )

    def getTestIds(self):
        ""
        return parse_test_ids( self.out )

    def startedTestIds(self):
        ""
        return parse_started_tests( self.out, self.resultsDir() )

    def startDate(self, testpath):
        ""
        if self.testdates == None:
            self.parseTestDates()

        return self.testdates[ testpath ][0]

    def endDate(self, testpath):
        ""
        if self.testdates == None:
            self.parseTestDates()

        return self.testdates[ testpath ][1]

    def parseTestDates(self):
        ""
        tdir = os.path.basename( self.resultsDir() )

        self.testdates = {}
        for xpath,start,end in testtimes( self.out ):

            # do not include the test results directory name
            pL = xpath.split( tdir+os.sep, 1 )
            if len(pL) == 2:
                xdir = pL[1]
            else:
                xdir = xpath

            self.testdates[ xdir ] = ( start, end )

    def getTimeoutInfoSection(self):
        ""
        inside = False
        tL = None
        tsum = None
        for line in self.out.splitlines():
            if inside:
                if line.strip().startswith( 'TIMEOUT SUM' ):
                    tsum = parse_time( line.strip().split()[-1] )
                    inside = False
                else:
                    lineL = line.strip().split( None, 2 )
                    to = parse_time(lineL[0])
                    if len( lineL ) == 2:
                        tL.append( [ to, -1, lineL[1] ] )
                    else:
                        rt = parse_time(lineL[1])
                        tL.append( [ to, rt, lineL[2] ] )
            elif line.strip().split() == ['TIMEOUT','RUNTIME','TEST']:
                tL = []
                tsum = None
                inside = True
        return tL,tsum


def runvvtest( *cmd_args, **options ):
    """
    Options:  batch=True (default=False)
              quiet=True (default=False)
              raise_on_error=False (default=True)
              chdir=some/path (default=None)
              addplatform=True
    """
    cmdL = vvtest_command_line( *cmd_args, **options )
    vrun = VvtestCommandRunner( cmdL )
    vrun.run( **options )
    return vrun


def vvtest_command_line( *cmd_args, **options ):
    """
    Options:  batch=True (default=False)
              addplatform=True
              addverbose=True
              vvtestpath=/path/vvtest (default is 'vvtest_file' from this file)
    """
    argstr = ' '.join( cmd_args )
    argL = shlex.split( argstr )

    cmdL = [ sys.executable, options.get( 'vvtestpath', vvtest_file ) ]

    if need_to_add_verbose_flag( argL, options ):
        # add -v when running in order to extract the full test list
        cmdL.append( '-v' )

    if options.get( 'addplatform', True ) and '--plat' not in argL:
        cmdL.extend( [ '--plat', core_platform_name() ] )

    if options.get( 'batch', False ):

        cmdL.append( '--batch' )

        if '--batch-limit' not in argL:
            cmdL.extend( [ '--batch-limit', '5' ] )

        if '--batch-length' not in argL:
            cmdL.extend( [ '--batch-length', '0' ] )

    elif '--batch' not in argL:
        if '-n' not in argL:
            cmdL.extend( [ '-n', '8' ] )

    if argstr:
        cmdL.extend( shlex.split(argstr))

    return cmdL


def need_to_add_verbose_flag( vvtest_args, options ):
    ""
    if options.get( 'addverbose', True ):
        if '-i' in vvtest_args: return False
        if '-g' in vvtest_args: return False
        if '-v' in vvtest_args: return False
        if '-vv' in vvtest_args: return False
        return True
    else:
        return False


def parse_vvtest_counts( out ):
    ""
    ntot = 0
    np = 0 ; nf = 0 ; nd = 0 ; nn = 0 ; nt = 0 ; nr = 0 ; ns = 0

    for line in extract_testlines( out ):

        lineL = line.strip().split()

        if   check_pass   ( lineL ): np += 1
        elif check_fail   ( lineL ): nf += 1
        elif check_diff   ( lineL ): nd += 1
        elif check_notrun ( lineL ): nn += 1
        elif check_timeout( lineL ): nt += 1
        elif check_notdone( lineL ): nr += 1
        elif check_skip   ( lineL ): ns += 1
        elif lineL[0] == '...':
            break  # a truncated test listing message starts with "..."
        else:
            raise Exception( 'unable to parse test line: '+line )

        ntot += 1

    cntD = { 'total'  : ntot,
             'npass'  : np,
             'fail'   : nf,
             'diff'   : nd,
             'notrun' : nn,
             'timeout': nt,
             'notdone': nr,
             'skip'   : ns }

    return cntD


# these have to be modified if/when the output format changes in vvtest
def check_pass(L): return len(L) >= 4 and L[0] == 'pass'
def check_fail(L): return len(L) >= 4 and L[0] == 'fail'
def check_diff(L): return len(L) >= 4 and L[0] == 'diff'
def check_notrun(L): return len(L) >= 2 and L[0] == 'notrun'
def check_timeout(L): return len(L) >= 3 and L[0] == 'timeout'
def check_notdone(L): return len(L) >= 2 and L[0] == 'notdone'
def check_skip(L): return len(L) >= 3 and L[0] == 'skip'


def parse_test_ids( vvtest_output ):
    ""
    tlist = []
    for line in extract_testlines( vvtest_output ):

        s = line.strip().split()[-1]
        if s.startswith( 'stage=' ):
            s = ' '.join( line.strip().split()[-2:] )

        d1 = util.first_path_segment(s)+os.sep
        if d1.startswith( 'TestResults.' ):
            tid = s.split(d1)[1]
        else:
            tid = s

        tlist.append( tid )

    return tlist


def parse_started_tests( vvtest_output, results_dir ):
    ""
    tdir = os.path.basename( results_dir )

    startlist = []
    for line in vvtest_output.splitlines():
        if line.startswith( 'Starting: ' ):
            s = line.split( 'Starting: ' )[1].strip()
            if s.startswith( tdir+os.sep ):
                startlist.append( s.split( tdir+os.sep )[1] )

    return startlist


def filter_logfile_list_by_testid( logfiles, testid_pattern ):
    ""
    pat = util.adjust_shell_pattern_to_work_with_fnmatch( testid_pattern )

    newL = []

    for pn in logfiles:
        d,b = os.path.split( pn )
        assert b == 'execute.log'
        if fnmatch.fnmatch( os.path.basename( d ), pat ):
            newL.append( pn )

    return newL


def get_platform_name( vvtest_output ):
    ""
    platname = None

    for line in vvtest_output.splitlines():
        line = line.strip()
        if line.startswith( 'Test directory:' ):
            L1 = line.split( 'Test directory:', 1 )
            if len(L1) == 2:
                L2 = os.path.basename( L1[1].strip() ).split('.')
                if len(L2) >= 2:
                    platname = L2[1]

    return platname


def get_results_dir( out ):
    """
    """
    tdir = None

    for line in out.split( os.linesep ):
        if line.strip().startswith( 'Test directory:' ):
            tdir = line.split( 'Test directory:', 1 )[1].strip()

    return tdir


def greptestlist( shell_pattern, vvtest_output ):
    ""
    pattern = util.adjust_shell_pattern_to_work_with_fnmatch( shell_pattern )

    matchlines = []
    for line in extract_testlines( vvtest_output ):
        if fnmatch.fnmatch( line, pattern ):
            matchlines.append( line )

    return matchlines


def extract_testlines( vvtest_output ):
    ""
    lineL = []
    mark = False
    for line in vvtest_output.splitlines():
        if mark:
            if line.startswith( "==========" ) or \
               line.startswith( 'Test list:' ) or \
               line.startswith( 'Summary:' ):  # happens if test list is empty
                mark = False
            else:
                lineL.append( line )

        elif line.startswith( "==========" ):
            mark = True
            del lineL[:]  # reset list so only last cluster is considered

    return lineL


def testtimes(out):
    """
    Parses the test output and obtains the start time (seconds since epoch)
    and finish time of each test.  Returns a list of
          [ test execute dir, start time, end time ]
    """
    timesL = []

    fmt = '%Y %m/%d %H:%M:%S'
    for line in extract_testlines(out):
        L = line.strip().split()
        try:
            s = time.strftime('%Y ')+L[2]+' '+L[3]
            t = time.mktime( time.strptime( s, fmt ) )
            e = t + parse_runtime_from_output_line( L )
            timesL.append( [ L[-1], t, e ] )
        except Exception:
            pass

    return timesL


def parse_runtime_from_output_line( lineL ):
    ""
    hmsL = lineL[1].split(':')
    assert len(hmsL) in [2,3]
    if len(hmsL) == 2:
        return int(hmsL[0])*60 + int(hmsL[1])
    else:
        return int(hmsL[0])*60*60 + int(hmsL[1])*60 + int(hmsL[2])


def parse_summary_string( summary_string ):
    """
    Parses the summary string from vvtest output, such as

        Summary: pass=0, fail=1, diff=0, timeout=0, notdone=0, notrun=1, skip=0

    Returns dictionary of these names to their values.
    """
    valD = {}

    for spec in summary_string.split():
        spec = spec.strip(',')
        if '=' in spec:
            nv = spec.split('=')
            assert len(nv) == 2
            valD[ nv[0] ] = int( nv[1] )

    return valD


def assert_summary_string( summary_string,
                           npass=None, fail=None, diff=None,
                           timeout=None, notdone=None, notrun=None,
                           skip=None ):
    """
    Parses the summary string and asserts any given values.
    """
    valD = parse_summary_string( summary_string )

    if npass   != None: assert valD['pass']    == npass
    if fail    != None: assert valD['fail']    == fail
    if diff    != None: assert valD['diff']    == diff
    if timeout != None: assert valD['timeout'] == timeout
    if notdone != None: assert valD['notdone'] == notdone
    if notrun  != None: assert valD['notrun']  == notrun
    if skip    != None: assert valD['skip']    == skip


def parse_time( colon_time_string ):
    ""
    sL = colon_time_string.split(':')
    sL.reverse()
    tval = int( sL[0] )
    if len( sL ) > 1:
        tval += 60*int( sL[1] )
    if len( sL) > 2:
        tval += 60*60*int( sL[2] )
    return tval


def creator( idflags={}, platname=None, opts=[] ):
    ""
    return testcreator.TestCreator( idflags, platname, opts )


def create_tests_from_file( filename, platname=core_platform_name(),
                                      optionlist=[] ):
    ""
    tc = creator( {}, platname, optionlist )

    assert not os.path.isabs( filename )
    assert not os.path.normpath(filename).startswith('..')

    dname,fname = os.path.split( filename )

    tL = []
    for tspec in tc.fromFile( fname, dname ):
        tL.append( [tspec.getDisplayString(), testcase.TestCase( tspec )] )

    tL.sort()

    return [ tcase for _,tcase in tL ]


def parse_single_test_file( filename, optionlist=[] ):
    ""
    tL = create_tests_from_file( filename, optionlist=optionlist )
    assert len( tL ) == 1
    return tL[0].getSpec()


def create_testlist_from_test_files( *filenames ):
    ""
    tlist = TestList( TestCaseFactory() )

    for fn in filenames:
        for t in create_tests_from_file( fn ):
            tlist.addTest(t)

    return tlist


def make_test_case( filepath, content ):
    ""
    util.writefile( filepath, content )
    tL = create_tests_from_file( filepath )
    assert len(tL) == 1
    return tL[0]


def make_fake_TestSpec( name='atest', keywords=['key1','key2'], idflags=None ):
    ""
    if idflags is not None:
        ts = testspec.TestSpec( name, os.getcwd(), 'sdir/'+name+'.vvt', idflags )
    else:
        ts = testspec.TestSpec( name, os.getcwd(), 'sdir/'+name+'.vvt' )

    ts.setKeywordList( keywords )
    ts.setParameters( { 'np':'4' } )

    ts.setConstructionCompleted()

    return ts


def make_fake_TestCase( result=None, runtime=None, name='atest',
                        keywords=['key1','key2'], timeout=None ):
    ""
    tspec = make_fake_TestSpec( name, keywords )
    tcase = testcase.TestCase( tspec )
    tstat = tcase.getStat()

    tstat.resetResults()

    if result:
        tm = time.time()
        if result == 'skip':
            tstat.markSkipByPlatform()
        elif result == 'skippass':
            tstat.markStarted( tm )
            tstat.markDone( 0 )
            tstat.markSkipByPlatform()
        elif result == 'skipfail':
            tstat.markStarted( tm )
            tstat.markDone( 1 )
            tstat.markSkipByPlatform()
        elif result == 'runskip':
            tstat.markStarted( tm )
            tstat.markDone( teststatus.SKIP_EXIT_STATUS )
        elif result == 'timeout':
            tstat.markStarted( tm )
            tstat.markTimedOut()
        elif result == 'pass':
            tstat.markStarted( tm )
            tstat.markDone( 0 )
        elif result == 'diff':
            tstat.markStarted( tm )
            tstat.markDone( teststatus.DIFF_EXIT_STATUS )
        elif result == 'notdone':
            tstat.markStarted( tm )
        elif result == 'notrun':
            pass
        elif result == 'running':
            tstat.markStarted( tm )
        else:
            assert result == 'fail', '*** error (value='+str(result)+')'
            tstat.markStarted( tm )
            tstat.markDone( 1 )

    if runtime != None:
        tstat.setRuntime( runtime )

    if timeout != None:
        tspec.setTimeout( timeout )

    return tcase


def make_TestCase_with_a_dependency( test_result, result_expr=None,
                                     second_level_result=None ):
    ""
    src_tcase = make_fake_TestCase( name='srctest' )
    tcase = make_fake_TestCase( test_result )

    wordexpr = make_dependency_word_expression( result_expr )

    connect_dependency( src_tcase, tcase, None, wordexpr )

    if second_level_result:
        tcase2 = make_fake_TestCase( second_level_result, name='btest' )
        wordexpr2 = make_dependency_word_expression( None )
        connect_dependency( tcase, tcase2, None, wordexpr2 )

    return src_tcase


def add_dependency( tcase, test_result ):
    ""
    dep_tcase = make_fake_TestCase( test_result )
    connect_dependency( tcase, dep_tcase, None, None )


def make_dependency_word_expression( string_expr ):
    ""
    if string_expr == None:
        wx = None
    elif string_expr == '*':
        wx = WordExpression()
    else:
        wx = WordExpression( string_expr )

    return wx


def make_fake_staged_TestCase( stage_index=0 ):
    ""
    tcase = make_fake_TestCase()
    tspec = tcase.getSpec()

    pset = paramset.ParameterSet()
    pset.addParameters( ('stage','np'), [ ('1','1'), ('2','4'), ('3','1') ] )

    if stage_index == 0:
        tspec.setParameters( { 'stage':'1', 'np':'1' } )
        tspec.setStagedParameters( True, False, 'stage', 'np' )
    elif stage_index == 1:
        tspec.setParameters( { 'stage':'2', 'np':'4' } )
        tspec.setStagedParameters( False, False, 'stage', 'np' )
    elif stage_index == 2:
        tspec.setParameters( { 'stage':'3', 'np':'1' } )
        tspec.setStagedParameters( False, True, 'stage', 'np' )

    return tcase


def make_TestCase_list( timespec='runtime' ):
    ""
    tests = []

    for i in range(2):
        for j in range(2):

            tspec = make_fake_TestSpec( name='atest'+str(i) )
            tspec.setParameters( { 'np':str(j+1) } )

            tcase = testcase.TestCase( tspec )
            tstat = tcase.getStat()

            tstat.resetResults()

            if timespec == 'runtime':
                tstat.setRuntime( (i+1)*10+j+1 )
                # print( 'tcase', tcase.getSpec().getDisplayString(), tstat.getRuntime() )
            else:
                assert timespec == 'timeout'
                tstat.setAttr( 'timeout', (i+1)*10+j+1 )

            tests.append( tcase )

    return tests


def make_fake_TestList( timespec='runtime' ):
    ""
    tests = make_TestCase_list( timespec=timespec )

    tlist = TestList( TestCaseFactory() )
    for tcase in tests:
        tlist.addTest( tcase )

    return tlist


def scan_to_make_TestList( path, timeout_attr=None ):
    ""
    tlist = TestList( TestCaseFactory() )

    tc = creator( platname='XBox' )
    scan = TestFileScanner( Locator(os.getcwd()), tc, TestCaseFactory() )
    scan.scanPath( tlist, path )

    if timeout_attr != None:
        for tcase in tlist.getTests():
            tcase.getStat().setAttr( 'timeout', timeout_attr )

    tlist.createAnalyzeGroupMap()
    tlist.connectDependencies()

    return tlist


class FakeHandler:
    def initialize_for_execution(self, *args):
        pass


def make_fake_TestExecList( timespec='runtime' ):
    ""
    tests = make_TestCase_list( timespec=timespec )

    tlist = TestList( TestCaseFactory() )
    for tcase in tests:
        tlist.addTest( tcase )

    xlist = TestExecList( tlist, FakeHandler() )

    return tlist, xlist


def scan_to_make_TestExecList( path, timeout_attr=None ):
    ""
    tlist = TestList( TestCaseFactory() )

    tc = creator( platname='XBox' )
    scan = TestFileScanner( Locator(os.getcwd()), tc, TestCaseFactory() )
    scan.scanPath( tlist, path )

    if timeout_attr != None:
        for tcase in tlist.getTests():
            tcase.getStat().setAttr( 'timeout', timeout_attr )

    tlist.createAnalyzeGroupMap()
    tlist.connectDependencies()

    xlist = TestExecList( tlist, FakeHandler() )

    return tlist, xlist


def make_user_plugin( content=None, platname=None, options=None ):
    ""
    plugname = 'plugin'

    subdir = 'adir'
    if content != None:
        util.writefile( subdir+'/'+plugname+'.py', content )
        time.sleep(1)

    rtconfig = make_RuntimeConfig( platname, options )

    sys.path.insert( 0, os.path.abspath(subdir) )
    try:
        mod,err = import_user_plugin( plugname )
        assert not err
        plug = UserPluginBridge( rtconfig, mod )
    finally:
        sys.path.pop( 0 )

    return plug


def make_RuntimeConfig( platname='XBox', options=[] ):
    ""
    rtconfig = RuntimeConfig()

    if platname:
        rtconfig.setPlatformName( platname )
        rtconfig.setPlatformExpression( None, platname )
    if options:
        rtconfig.setOptionList( options )

    return rtconfig


def make_fake_PermissionSetter():
    ""
    class DummyPermissionSetter:
        def __init__(self): pass
        def set(self, path): pass
        def apply(self, path): pass
        def recurse(self, path): pass

    return DummyPermissionSetter()
