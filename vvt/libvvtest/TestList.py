#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time
import fnmatch
import glob

from . import TestSpec
from . import TestExec
from . import TestSpecCreator
from . import CommonSpec
from . import testlistio


class TestList:
    """
    Stores a set of TestSpec objects.  Has utilities to read/write to a text
    file and to read from a test XML file.
    """

    version = '32'

    def __init__(self, filename, runtime_config=None):
        ""
        if filename:
            self.filename = os.path.normpath( filename )
        else:
            # use case: scanning tests, but never reading or writing
            self.filename = None

        self.results_suffix = None
        self.results_file = None

        self.datestamp = None
        self.finish = None

        self.groups = {}  # (test filepath, test name) -> list of TestSpec

        self.tspecs = {}  # TestSpec xdir -> TestSpec object
        self.active = {}  # TestSpec xdir -> TestSpec object

        self.xtlist = {}  # np -> list of TestExec objects
        self.started = {}  # TestSpec xdir -> TestExec object
        self.stopped = {}  # TestSpec xdir -> TestExec object
        
        self.rtconfig = runtime_config

    def setResultsSuffix(self, suffix=None):
        ""
        if suffix:
            self.results_suffix = suffix
        elif not self.results_suffix:
            self.results_suffix = time.strftime( "%Y-%m-%d_%H:%M:%S" )

        return self.results_suffix

    def getResultsSuffix(self):
        ""
        return self.results_suffix

    def stringFileWrite(self, include_results_suffix=False):
        """
        Writes all the tests in this container to the test list file.  If
        'include_results_suffix' is True, the results suffix is written as
        an attribute in the file.
        """
        assert self.filename

        check_make_directory_containing_file( self.filename )

        tlw = testlistio.TestListWriter( self.filename )

        if include_results_suffix:
            assert self.results_suffix
            tlw.start( results_suffix=self.results_suffix )
        else:
            tlw.start()

        for t in self.tspecs.values():
            tlw.append( t )

        tlw.finish()

    def initializeResultsFile(self):
        ""
        self.setResultsSuffix()

        rfile = self.filename + '.' + self.results_suffix
        
        self.results_file = testlistio.TestListWriter( rfile )

        self.results_file.start()

        return rfile

    def addIncludeFile(self, testlist_path):
        """
        Appends the given filename to the test results file.
        """
        assert self.results_suffix, 'suffix must have already been set'
        inclf = testlist_path + '.' + self.results_suffix
        self.results_file.addIncludeFile( inclf )

    def appendTestResult(self, tspec):
        """
        Appends the results file with the name and attributes of the given
        TestSpec object.
        """
        self.results_file.append( tspec )

    def writeFinished(self):
        """
        Appends the results file with a finish marker that contains the
        current date.
        """
        self.results_file.finish()

    def readTestList(self):
        ""
        assert self.filename

        self.tspecs.clear()

        tlr = testlistio.TestListReader( self.filename )
        tlr.read()

        self.results_suffix = tlr.getAttr( 'results_suffix', None )

        self.tspecs.update( tlr.getTests() )

    def readTestListIfNoTestResults(self):
        ""
        if len( self.getResultsFilenames() ) == 0:
            self.readTestList()

    def readTestResults(self, resultsfilename=None):
        ""
        if resultsfilename == None:
            self._read_file_list( self.getResultsFilenames() )
        else:
            self._read_file_list( [ resultsfilename ] )

    def getResultsFilenames(self):
        ""
        assert self.filename
        fileL = glob.glob( self.filename+'.*' )
        fileL.sort()
        return fileL

    def _read_file_list(self, files):
        ""
        for fn in files:

            tlr = testlistio.TestListReader( fn )
            tlr.read()

            self.datestamp = tlr.getStartDate()
            self.finish = tlr.getFinishDate()

            for xdir,tspec in tlr.getTests().items():

                t = self.tspecs.get( xdir, None )
                if t == None:
                    self.tspecs[ xdir ] = tspec
                else:
                    for k,v in tspec.getAttrs().items():
                        t.setAttr( k, v )

    def inlineIncludeFiles(self):
        ""
        rfile = self.filename + '.' + self.results_suffix
        testlistio.inline_include_files( rfile )

    def getDateStamp(self, default=None):
        """
        Return the start date from the last test results file read using the
        readTestResults() function.  If a read has not been done, the 'default'
        argument is returned.
        """
        if self.datestamp:
            return self.datestamp
        return default

    def getFinishDate(self, default=None):
        """
        Return the finish date from the last test results file read using the
        readTestResults() function.  If a read has not been done, or vvtest is
        still running, or vvtest got killed in the middle of running, the
        'default' argument is returned.
        """
        if self.finish:
            return self.finish
        return default

    def getTests(self):
        """
        Returns, in a list, all tests either scanned or read from a file.
        """
        return self.tspecs.values()

    def loadAndFilter(self, maxprocs, filter_dir=None,
                            analyze_only=0, prune=False,
                            baseline=False ):
        """
        Creates the active test list using the scanned tests and the tests
        read in from a test list file.  A subdirectory filter is applied and
        the filter given in the constructor.

        If 'prune' is true, then analyze tests are filtered out if they have
        inactive children that did not pass/diff in a previous run.

        Returns a list of (analyze test, child test) for analyze tests that
        were pruned.  The second item is the child that did not pass/diff.
        """
        self.active = {}

        self._create_parameterize_analyze_group_map()

        subdir = None
        if filter_dir != None:
          subdir = os.path.normpath( filter_dir )
          if subdir == '' or subdir == '.':
            subdir = None

        rmD = {}
        for xdir,t in self.tspecs.items():

            # TODO: is it possible that the filter apply before refresh could
            #       miss a test that changed since last time and now should
            #       be included !!
            keep = self._apply_filters( xdir, t, subdir, analyze_only )

            if keep:
                # apply runtime filtering
                tm = testruntime(t)
                if tm != None and not self.rtconfig.evaluate_runtime( tm ):
                    keep = False
                    rmD[ xdir ] = t

            if keep:
                if 'file' in t.getOrigin():
                    self.active[ xdir ] = t
                else:
                    # read from test source, which double checks filtering
                    keep = TestSpecCreator.refreshTest( t, self.rtconfig )
                    if baseline and not t.hasBaseline():
                        keep = False
                    if keep:
                        self.active[ xdir ] = t

        # remove tests that do not meet runtime requirements
        self._remove_tests( rmD )

        rtsum = self.rtconfig.getAttr( 'runtime_sum', None )
        if rtsum != None:
            # filter by cummulative runtime; first, generate list with times
            rmD.clear()
            tL = []
            for xdir,t in self.active.items():
                tm = testruntime(t)
                if tm == None: tm = 0
                tL.append( (tm,xdir,t) )
            tL.sort()
            # accumulate tests until allowed runtime is exceeded
            tsum = 0.
            i = 0 ; n = len(tL)
            while i < n:
                tm,xdir,t = tL[i]
                tsum += tm
                if tsum > rtsum:
                    break
                i += 1
            # put the rest of the tests in the remove dict
            while i < n:
                tm,xdir,t = tL[i]
                rmD[xdir] = t
                i += 1
            tL = None
            self._remove_tests( rmD )

        pruneL = []
        cntmax = 0
        if prune:
            
            # remove analyze tests from the active set if they have inactive
            # children that have a bad result
            for xdir,t in self.tspecs.items():

                pxdir = self._find_group_analyze_test( t )

                # does this test have a parent and is this test inactive
                if pxdir != None and xdir not in self.active:

                    # is the parent active and does the child have a bad result
                    if pxdir in self.active and \
                          ( t.getAttr('state') != 'done' or \
                            t.getAttr('result') not in ['pass','diff'] ):
                        # remove the parent from the active set
                        pt = self.active.pop( pxdir )
                        pruneL.append( (pt,t) )

            # Remove tests that exceed the platform resources (num processors).
            # For execute/analyze, if an execute test exceeds the resources
            # then the entire test set is removed.
            rmD.clear()
            cntmax = 0
            for xdir,t in self.active.items():
                np = int( t.getParameters().get( 'np', 1 ) )
                assert maxprocs != None
                if np > maxprocs:
                    rmD[xdir] = t
                    cntmax += 1
            self._remove_tests( rmD )

        rmD = None

        return pruneL, cntmax

    def _apply_filters(self, xdir, tspec, subdir, analyze_only):
        """
        """
        if self.rtconfig.getAttr('include_all',0):
            return True
        
        kwL = tspec.getResultsKeywords() + tspec.getKeywords()
        if not self.rtconfig.satisfies_keywords( kwL ):
            return False
        
        if subdir != None and subdir != xdir and not is_subdir( subdir, xdir ):
            return False
        
        # want child tests to run with the "analyze only" option ?
        # if yes, then comment this out; if no, then uncomment it
        #if analyze_only and tspec.getParent() != None:
        #  return 0
        
        if not self.rtconfig.evaluate_parameters( tspec.getParameters() ):
            return False

        if not self.rtconfig.getAttr( 'include_tdd', False ) and \
           tspec.hasAttr( 'TDD' ):
            return False

        return True

    def _remove_tests(self, removeD):
        """
        The 'removeD' should be a dict mapping xdir to TestSpec.  Those tests
        will be removed from the self.tspecs and self.active sets.  If any test
        to be removed is part of a parameterize/analyze group, then the entire
        group is removed.
        """
        for xdir,t in removeD.items():

            key = ( t.getFilepath(), t.getName() )

            grpL = self.groups[key]

            if not self._test_group_has_analyze( grpL ):
                # not a parameterize/analyze test, so just remove the test
                grpL = [ t ]

            for grpt in grpL:

                xdir = grpt.getExecuteDirectory()

                if xdir in self.active:
                    self.active.pop( xdir )

                # don't remove a test from the TestResults test list if
                # it was there previously
                if xdir in self.tspecs and 'string' not in t.getOrigin():
                    self.tspecs.pop( xdir )

    def _create_parameterize_analyze_group_map(self):
        ""
        self.groups.clear()

        for xdir,t in self.tspecs.items():

            # this key is common to each test in a parameterize/analyze
            # test group (including the analyze test)
            key = ( t.getFilepath(), t.getName() )

            L = self.groups.get( key, None )
            if L == None:
                L = []
                self.groups[ key ] = L

            L.append( t )

    def markTestsWithDependents(self):
        ""
        for np,txL in self.xtlist.items():
            for tx in txL:
                for tdep,_,_ in tx.getDependencies():
                    if isinstance( tdep, TestExec.TestExec ):
                        tdep.atest.setAttr( 'hasdependent', True )
                    else:
                        tdep.setAttr( 'hasdependent', True )

    def _test_group_has_analyze(self, grpL):
        ""
        for t in grpL:
            if t.isAnalyze():
                return True
        return False

    def _find_group_analyze_test(self, testobj):
        ""
        key = ( testobj.getFilepath(), testobj.getName() )

        grpL = self.groups[key]

        for t in grpL:
            if t != testobj and t.isAnalyze():
                return t.getExecuteDirectory()

        return None

    def _has_dependent_test(self, testobj):
        ""
        if testobj.getAttr( 'hasdependent', False ):
            return True

        key = ( testobj.getFilepath(), testobj.getName() )

        grpL = self.groups[key]

        for t in grpL:
            if t != testobj and t.isAnalyze():
                return True

        return False

    def getActiveTests(self, sorting=''):
        """
        Get a list of the active tests (after filtering).  If 'sorting' is
        not an empty string, it should be a set of characters that control the
        way the test sorting is performed.
                n : test name (the default)
                x : execution directory name
                t : test run time
                d : execution date
                s : test status (such as pass, fail, diff, etc)
                r : reverse the order
        """
        if not sorting:
            tL = list( self.active.values() )
            tL.sort()
        else:
            tL = []
            for t in self.active.values():
                L = []
                for c in sorting:
                    if c == 'n':
                        L.append( t.getName() )
                    elif c == 'x':
                        L.append( t.getExecuteDirectory() )
                    elif c == 't':
                        tm = testruntime(t)
                        if tm == None: tm = 0
                        L.append( tm )
                    elif c == 'd':
                        L.append( t.getAttr( 'xdate', 0 ) )
                    elif c == 's':
                        st = t.getAttr( 'state', 'notrun' )
                        if st == 'notrun':
                            L.append( st )
                        elif st == 'done':
                            L.append( t.getAttr( 'result', 'unknown' ) )
                        else:
                            L.append( 'notdone' )
                L.append( t )
                tL.append( L )
            tL.sort()
            if 'r' in sorting:
                tL.reverse()
            tL = [ L[-1] for L in tL ]

        return tL

    def scanDirectory(self, base_directory, force_params=None):
        """
        Recursively scans for test XML or VVT files starting at 'base_directory'.
        If 'force_params' is not None, it must be a dictionary mapping
        parameter names to a list of parameter values.  Any test that contains
        a parameter in this dictionary will take on the given values for that
        parameter.
        """
        bdir = os.path.normpath( os.path.abspath(base_directory) )
        for root,dirs,files in os.walk( bdir ):
            self._scan_recurse( bdir, force_params, root, dirs, files )
    
    def _scan_recurse(self, basedir, force_params, d, dirs, files):
        """
        This function is given to os.walk to recursively scan a directory
        tree for test XML files.  The 'basedir' is the directory originally
        sent to the os.walk function.
        """
        d = os.path.normpath(d)
        
        if basedir == d:
          reldir = '.'
        else:
          assert basedir+os.sep == d[:len(basedir)+1]
          reldir = d[len(basedir)+1:]

        # scan files with extension "xml" or "vvt"; soft links to directories
        # are skipped by os.walk so special handling is performed

        for f in files:
            bn,ext = os.path.splitext(f)
            df = os.path.join(d,f)
            if bn and ext in ['.xml','.vvt']:
                self.readTestFile( basedir, os.path.join(reldir,f), force_params )

        linkdirs = []
        for subd in list(dirs):
            rd = os.path.join( d, subd )
            if not os.path.exists(rd) or \
                    subd.startswith("TestResults.") or \
                    subd.startswith("Build_"):
                dirs.remove( subd )
            elif os.path.islink(rd):
                linkdirs.append( rd )

        # TODO: should check that the soft linked directories do not
        #       point to a parent directory of any of the directories
        #       visited thus far (to avoid an infinite scan loop)
        #       - would have to use os.path.realpath() or something because
        #         the actual path may be the softlinked path rather than the
        #         path obtained by following '..' all the way to root

        # manually recurse into soft linked directories
        for ld in linkdirs:
            for lroot,ldirs,lfiles in os.walk( ld ):
                self._scan_recurse( basedir, force_params, lroot, ldirs, lfiles )
    
    def readTestFile(self, basepath, relfile, force_params):
        """
        Initiates the parsing of a test file.  XML test descriptions may be
        skipped if they don't appear to be a test file.  Attributes from
        existing tests will be absorbed.
        """
        assert basepath
        assert relfile
        assert os.path.isabs( basepath )
        assert not os.path.isabs( relfile )
        
        basepath = os.path.normpath( basepath )
        relfile  = os.path.normpath( relfile )
        
        assert relfile
        
        try:
          testL = TestSpecCreator.createTestObjects(
                        basepath, relfile, force_params, self.rtconfig )
        except TestSpecCreator.TestSpecError:
          print3( "*** skipping file " + os.path.join( basepath, relfile ) + \
                  ": " + str( sys.exc_info()[1] ) )
          testL = []
        
        for t in testL:
            # this new test is ignored if it was already read from source
            # (or a different test source but the same relative path from root)
            xdir = t.getExecuteDirectory()

            t2 = self.tspecs.get( xdir, None )
            if t2 == None:
                self.tspecs[xdir] = t
            elif 'file' in t2.getOrigin():
                # this new test is ignored because there is a previous test
                # (generated from a file) with the same execute directory
                pass
            else:
                # existing test was read from a test list file; use the new
                # test instance but take on the attributes from the previous
                for n,v in t2.getAttrs().items():
                    t.setAttr(n,v)
                self.tspecs[xdir] = t

    def addTest(self, t):
        """
        Add a test to the test spec list.  Will overwrite an existing test.
        """
        self.tspecs[ t.getExecuteDirectory() ] = t
    
    def createTestExecs(self, test_dir, platform, config, perms):
        """
        Creates the set of TestExec objects from the active test list.
        """
        d = os.path.join( config.get('toolsdir'), 'libvvtest' )
        c = config.get('configdir')
        xdb = CommonSpec.loadCommonSpec( d, c )
        
        self._createTestExecList( perms )
        
        for xt in self.getTestExecList():
          xt.init( test_dir, platform, xdb, config )
    
    def _createTestExecList(self, perms):
        """
        """
        self.xtlist = {}
        
        xtD = {}
        for t in self.active.values():

          assert 'file' in t.getOrigin()

          has_dependent = self._has_dependent_test( t )

          xt = TestExec.TestExec( t, perms, has_dependent )
          
          np = int( t.getParameters().get('np', 0) )
          if np in self.xtlist:
            self.xtlist[np].append(xt)
          else:
            self.xtlist[np] = [xt]
          
          xtD[ t.getExecuteDirectory() ] = xt
        
        # sort tests longest running first; 
        self.sortTestExecList()

        self._add_analyze_dependencies( xtD )
        self._add_general_dependencies( xtD )

    def _add_analyze_dependencies(self, xdir2testexec):
        """
        add dependencies of analyze tests to TestExec objects
        """
        for xt in self.getTestExecList():
            analyze_xdir = self._find_group_analyze_test( xt.atest )
            if analyze_xdir != None:
                # this test has an analyze dependent
                analyze_xt = xdir2testexec.get( analyze_xdir, None )
                if analyze_xt != None:
                    analyze_xt.addDependency( xt )
            elif xt.atest.isAnalyze():
                key = ( xt.atest.getFilepath(), xt.atest.getName() )
                grpL = self.groups.get( key, None )
                for gt in grpL:
                    if not gt.isAnalyze():
                        xt.addDependency( gt )

    def _add_general_dependencies(self, xdir2testexec):
        """
        add general dependencies to TestExec objects
        """
        xdirlist = self.tspecs.keys()
        for xt in self.getTestExecList():
            xdir = xt.atest.getExecuteDirectory()
            for dep_pat,expr in xt.atest.getDependencies():
                depL = find_tests_by_execute_directory_match(
                                                xdir, dep_pat, xdirlist )
                for dep_xdir in depL:
                    dep_obj = xdir2testexec.get(
                                    dep_xdir,
                                    self.tspecs.get( dep_xdir, None ) )
                    if dep_obj != None:
                        xt.addDependency( dep_obj, dep_pat, expr )

    def sortTestExecList(self):
        """
        Sort the TestExec objects by runtime, descending order.  This is so
        popNext() will try to avoid launching long running tests at the end
        of the testing sequence, which can add significantly to the total wall
        time.
        """
        for np,L in self.xtlist.items():
            sortL = []
            for tx in L:
                t = tx.atest
                tm = testruntime(t)
                if tm == None: tm = 0
                sortL.append( (tm,tx) )
            sortL.sort()
            sortL.reverse()
            L[:] = [ tx for tm,tx in sortL ]

    def getTestExecProcList(self):
        """
        Returns a list of integers; each integer is the number of processors
        needed by one or more tests in the TestExec list.
        """
        return self.xtlist.keys()
    
    def getTestExecList(self, numprocs=None):
        """
        If 'numprocs' is None, all TestExec objects are returned.  If 'numprocs'
        is not None, a list of TestExec objects is returned each of which need
        that number of processors to run.
        """
        L = []
        if numprocs == None:
          for txL in self.xtlist.values():
            L.extend( txL )
        else:
          L.extend( self.xtlist.get(numprocs,[]) )
        return L
    
    def popNext(self, platform):
        """
        Finds a test to execute.  Returns a TestExec object, or None if no
        test can run.  In this case, one of the following is true
        
            1. there are not enough free processors to run another test
            2. the only tests left are parent tests that cannot be run
               because one or more of their children did not pass or diff

        In the latter case, numRunning() will be zero.
        """
        npL = list( self.xtlist.keys() )
        npL.sort()
        npL.reverse()

        # find longest runtime test such that the num procs is available
        tx = self._pop_next_test( npL, platform )
        if tx == None and len(self.started) == 0:
            # search for tests that need more processors than platform has
            tx = self._pop_next_test( npL )

        if tx != None:
            self.started[ tx.atest.getExecuteDirectory() ] = tx

        return tx

    def popRemaining(self):
        """
        All remaining tests are removed from the run list and returned.
        """
        tL = []
        for np,L in list( self.xtlist.items() ):
            tL.extend( L )
            del L[:]
            self.xtlist.pop( np )
        return tL

    def getRunning(self):
        """
        Return the list of tests that are still running.
        """
        return self.started.values()

    def testDone(self, tx):
        """
        """
        xdir = tx.atest.getExecuteDirectory()
        self.appendTestResult( tx.atest )
        self.started.pop( xdir )
        self.stopped[ xdir ] = tx

    def numActive(self):
        """
        Return the total number of active tests (the tests that are to be run).
        """
        return len(self.active)

    def numDone(self):
        """
        Return the number of tests that have been run.
        """
        return len(self.stopped)

    def numRunning(self):
        """
        Return the number of tests are currently running.
        """
        return len(self.started)

    def _pop_next_test(self, npL, platform=None):
        """
        """
        for np in npL:
            if platform == None or platform.queryProcs(np):
                tL = self.xtlist[np]
                N = len(tL)
                i = 0
                while i < N:
                    tx = tL[i]
                    if tx.getBlockingDependency() == None:
                        self._pop_test_exec( np, i )
                        return tx
                    i += 1
        return None

    def _pop_test_exec(self, np, i):
        """
        """
        L = self.xtlist[np]
        del L[i]
        if len(L) == 0:
            self.xtlist.pop( np )


def is_subdir(parent_dir, subdir):
    """
    TODO: test for relative paths
    """
    lp = len(parent_dir)
    ls = len(subdir)
    if ls > lp and parent_dir + '/' == subdir[0:lp+1]:
      return subdir[lp+1:]
    return None


def check_make_directory_containing_file( filename ):
    ""
    d,b = os.path.split( filename )
    if d and d != '.':
        if not os.path.exists(d):
            os.mkdir( d )


def testruntime( testobj ):
    """
    Get and return the test 'xtime'.  If that was not set, then get the
    'runtime'.  If neither are set, then return None.
    """
    tm = testobj.getAttr( 'xtime', None )
    if tm == None or tm < 0:
        tm = testobj.getAttr( 'runtime', None )
    return tm


def find_tests_by_execute_directory_match( xdir, pattern, xdir_list ):
    """
    Given 'xdir' dependent execute directory, the shell glob 'pattern' is
    matched against the execute directories in the 'xdir_list', in this order:

        1. basename(xdir)/pat
        2. basename(xdir)/*/pat
        3. pat
        4. *pat

    The first of these that matches at least one test will be returned.

    A python set of xdir is returned.
    """
    tbase = os.path.dirname( xdir )
    if tbase == '.':
        tbase = ''
    elif tbase:
        tbase += '/'

    L1 = [] ; L2 = [] ; L3 = [] ; L4 = []

    for xdir in xdir_list:

        p1 = os.path.normpath( tbase+pattern )
        if fnmatch.fnmatch( xdir, p1 ):
            L1.append( xdir )

        if fnmatch.fnmatch( xdir, tbase+'*/'+pattern ):
            L2.append( xdir )

        if fnmatch.fnmatch( xdir, pattern ):
            L3.append( xdir )

        if fnmatch.fnmatch( xdir, '*'+pattern ):
            L4.append( xdir )

    for L in [ L1, L2, L3, L4 ]:
        if len(L) > 0:
            return set(L)

    return set()


def print3( *args ):
    sys.stdout.write( ' '.join( [ str(arg) for arg in args ] ) + '\n' )
    sys.stdout.flush()
