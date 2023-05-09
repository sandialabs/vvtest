#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time
import glob
from os.path import abspath, normpath
from os.path import join as pjoin

from . import testlistio
from .groups import ParameterizeAnalyzeGroups
from .teststatus import copy_test_results
from . import depend


default_filename = 'testlist'


class TestList:
    """
    Stores a set of TestCase objects and has utilities to read and write them
    to a file.
    """

    def __init__(self, tcasefactory, filename=None):
        ""
        self.fact = tcasefactory
        self.setFilename( filename )

        self.rundate = None
        self.startdate = None
        self.finishdate = None

        self.tlistwriter = None
        self.groups = None  # a ParameterizeAnalyzeGroups class instance
        self.tcasemap = {}  # TestSpec ID -> TestCase object

    def setFilename(self, filename):
        ""
        if filename:
            self.filename = normpath( abspath( filename ) )
        else:
            self.filename = abspath( default_filename )

    def getFilename(self):
        ""
        return self.filename

    def setResultsDate(self, epochtime=None):
        ""
        if epochtime != None:
            self.rundate = int( float( epochtime ) + 0.5 )
        else:
            self.rundate = int( float( time.time() ) + 0.5 )

    def getResultsDate(self):
        ""
        return self.rundate

    def getResultsFilename(self):
        ""
        tup = time.localtime( self.rundate )
        tm = time.strftime( "%Y-%m-%d_%Hh%Mm%Ss", tup )
        return self.filename+'.'+tm

    def stringFileWrite(self, extended=False, **file_attrs):
        """
        Writes all the tests in this container to the test list file.  If
        'extended' is True, additional information is written to make the
        file more self-contained.
        """
        assert self.filename

        tlw = testlistio.TestListWriter( self.filename )

        tlw.start( rundate=self.rundate, **file_attrs )

        for tcase in self.tcasemap.values():
            tlw.append( tcase, extended=extended )

        tlw.finish()

        return self.filename

    def initializeResultsFile(self, **file_attrs):
        ""
        rfile = self.getResultsFilename()
        self.tlistwriter = testlistio.TestListWriter( rfile )
        self.tlistwriter.start( **file_attrs )

        return rfile

    def addIncludeFile(self, filename):
        """
        Appends the given filename to the test results file.
        """
        self.tlistwriter.addIncludeFile( filename )

    def completeIncludeFile(self, filename):
        ""
        self.tlistwriter.includeFileCompleted( filename )

    def appendTestResult(self, tcase):
        """
        Appends the results file with the name and attributes of the given
        TestCase object.
        """
        self.tlistwriter.append( tcase )

    def writeFinished(self):
        """
        Appends the results file with a finish marker that contains the
        current date.
        """
        self.tlistwriter.finish()

    def readTestList(self):
        ""
        assert self.filename

        if os.path.exists( self.filename ):

            tlr = testlistio.TestListReader( self.fact, self.filename )
            tlr.read()

            rd = tlr.getAttr( 'rundate', None )
            if rd is not None:
                self.rundate = rd

            for xdir,tcase in tlr.getTests().items():
                if xdir not in self.tcasemap:
                    self.tcasemap[ xdir ] = tcase

    def readTestResults(self):
        """
        Glob for results filenames and read them all in increasing order
        by rundate, replacing tests in this object.
        """
        fL = glob_results_files( self.filename )
        file_attrs = self._read_file_list( fL )
        return file_attrs

    def _read_file_list(self, files):
        ""
        file_attrs = {}

        for fn in files:

            tlr = testlistio.TestListReader( self.fact, fn )
            tlr.read()

            self.startdate = tlr.getStartDate()
            self.finishdate = tlr.getFinishDate()

            file_attrs.clear()
            file_attrs.update( tlr.getAttrs() )

            for xdir,tcase in tlr.getTests().items():
                self.tcasemap[ xdir ] = tcase

        return file_attrs

    def addTestsWithoutOverwrite(self, tcaselist):
        ""
        for tcase in tcaselist:
            tid = tcase.getSpec().getID()
            if tid not in self.tcasemap:
                self.tcasemap[ tid ] = tcase

    def copyTestResults(self, tcaselist):
        ""
        for tcase in tcaselist:
            tspec = tcase.getSpec()
            t = self.tcasemap.get( tspec.getID(), None )
            if t is not None:
                copy_test_results( t.getStat(), tcase.getStat() )
                t.getSpec().setIDTraits( tspec.getIDTraits() )

    def resultsFileIsMarkedFinished(self):
        ""
        finished = True

        rfileL = glob_results_files( self.filename )
        if len(rfileL) > 0:
           if not testlistio.file_is_marked_finished( rfileL[-1] ):
                finished = False

        return finished

    def getDateStamp(self):
        """
        Return the start date contained in the last test results file (set
        by readTestResults()). Or None if no read was done.
        """
        return self.startdate

    def getFinishDate(self):
        """
        Return the finish date as marked in the last test results file (set by
        readTestResults()). Or None if the last results file did not finish.
        """
        return self.finishdate

    def getTests(self):
        """
        Returns, in a list, all tests either scanned or read from a file.
        """
        return self.tcasemap.values()

    def getTestMap(self):
        """
        Returns all tests as a map from test ID to TestCase.
        """
        return self.tcasemap

    def getGroupMap(self):
        ""
        return self.groups

    def countActive(self):
        ""
        cnt = 0
        for tcase in self.tcasemap.values():
            if not tcase.getStat().skipTest():
                cnt += 1
        self.numactive = cnt

    def numActive(self):
        """
        Return the total number of active tests (the tests to be run).
        """
        return self.numactive

    def getActiveTests(self, sorting=''):
        """
        Get a list of the active tests (after filtering).  If 'sorting' is
        not an empty string, it should be a set of characters that control the
        way the test sorting is performed.
                n : test name
                x : execution directory name (the default)
                t : test run time
                d : execution date
                s : test status (such as pass, fail, diff, etc)
                r : reverse the order
        """
        if not sorting:
            sorting = 'xd'

        tL = []

        for idx,tcase in enumerate( self.tcasemap.values() ):
            t = tcase.getSpec()
            if not tcase.getStat().skipTest():
                subL = []
                for c in sorting:
                    if c == 'n':
                        subL.append( t.getName() )
                    elif c == 'x':
                        subL.append( t.getDisplayString() )
                    elif c == 't':
                        tm = tcase.getStat().getRuntime( None )
                        if tm == None: tm = 0
                        subL.append( tm )
                    elif c == 'd':
                        subL.append( tcase.getStat().getStartDate( 0 ) )
                    elif c == 's':
                        subL.append( tcase.getStat().getResultStatus() )

                subL.extend( [ idx, tcase ] )
                tL.append( subL )
        tL.sort()
        if 'r' in sorting:
            tL.reverse()
        tL = [ L[-1] for L in tL ]

        return tL

    def addTest(self, tcase):
        """
        Add/overwrite a test in the list.
        """
        self.tcasemap[ tcase.getSpec().getID() ] = tcase

    def createAnalyzeGroupMap(self):
        ""
        if self.groups == None:
            self.groups = ParameterizeAnalyzeGroups()
            self.groups.rebuild( self.tcasemap )

        return self.groups

    def getTestCaseFactory(self):
        ""
        return self.fact

    def connectDependencies(self, check_dependencies=True):
        """
        Find and set inter-test dependencies. If 'check_dependencies' is True
        and a dependency cannot be found or will always fail, then a warning
        is printed.
        """
        tmap = self.getTestMap()
        groups = self.getGroupMap()

        for tcase in self.getTests():
            if not tcase.getStat().skipTest():
                assert tcase.getSpec().constructionCompleted()
                if tcase.getSpec().isAnalyze():
                    grpL = groups.getGroup( tcase )
                    depend.connect_analyze_dependencies( tcase, grpL, tmap )

                depend.check_connect_dependencies( tcase, tmap, check_dependencies )

    def copyResultsIfStateChange(self, tests):
        """
        For each test in the given list of tests, if the test status is
        different from the test in this TestList object, then the test
        results are copied from the given test to the corresponding test in
        this TestList.

        A list of tests whose state changed to "done" is returned.
        """
        donetests = []

        for src_tcase in tests:
            tid = src_tcase.getSpec().getID()
            tstat = src_tcase.getStat()
            tcase = self._check_state_change( tid, tstat )

            if tcase and tcase.getStat().isDone():
                donetests.append( tcase )

        return donetests

    def _check_state_change(self, testid, teststatus):
        """
        Finds the corresponding test in this TestList and if the result status
        is different, then the test results are copied into this object's
        test and the test list file is appended.

        Returns None if the test's result status did not change, or the test
        itself if the status did change.
        """
        tcase = self.tcasemap[testid]

        old = tcase.getStat().getResultStatus()
        new = teststatus.getResultStatus()

        if new != old:
            copy_test_results( tcase.getStat(), teststatus )
            self.appendTestResult( tcase )
            return tcase

        return None  # return None if no state change


def glob_results_files( basename ):
    ""
    assert basename
    fileL = glob.glob( basename+'.*' )
    fileL.sort()
    return fileL
