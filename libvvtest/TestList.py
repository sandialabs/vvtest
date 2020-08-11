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
from .testctor import TestConstructor


default_filename = 'testlist'


class TestList:
    """
    Stores a set of TestCase objects and has utilities to read and write them
    to a file.
    """

    def __init__(self, filename=None, testctor=None):
        ""
        if filename:
            self.filename = normpath( abspath( filename ) )
        else:
            self.filename = abspath( default_filename )

        self.tctor = testctor

        self.rundate = None
        self.startdate = None
        self.finishdate = None

        self.tlistwriter = None
        self.groups = None  # a ParameterizeAnalyzeGroups class instance
        self.tcasemap = {}  # TestSpec ID -> TestCase object

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
        tm = time.strftime( "%Y-%m-%d_%H:%M:%S", tup )
        return self.filename+'.'+tm

    def stringFileWrite(self, extended=False, **file_attrs):
        """
        Writes all the tests in this container to the test list file.  If
        'extended' is True, additional information is written to make the
        file more self-contained.
        """
        assert self.filename

        # magic: why not always write the attrs?

        tlw = testlistio.TestListWriter( self.filename )

        if self.rundate != None:
            tlw.start( rundate=self.rundate, **file_attrs )
        else:
            tlw.start( **file_attrs)

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

            tlr = testlistio.TestListReader( self.filename )
            tlr.read( self.tctor )

            rd = tlr.getAttr( 'rundate', None )
            if rd != None:
                self.rundate = rd

            for xdir,tcase in tlr.getTests().items():
                if xdir not in self.tcasemap:
                    self.tcasemap[ xdir ] = tcase

    def readTestResults(self, preserve_skips=False):
        """
        Glob for results filenames and read them all in increasing order
        by rundate.

        If 'preserve_skips' is False, each test read in from a results file
        will have its skip setting removed from the test.
        """
        fL = glob_results_files( self.filename )
        file_attrs = self._read_file_list( fL, preserve_skips )
        return file_attrs

    def resultsFileIsMarkedFinished(self):
        ""
        finished = True

        rfileL = glob_results_files( self.filename )
        if len(rfileL) > 0:
           if not testlistio.file_is_marked_finished( rfileL[-1] ):
                finished = False

        return finished

    def _read_file_list(self, files, preserve_skips):
        ""
        file_attrs = {}

        for fn in files:

            tlr = testlistio.TestListReader( fn )
            tlr.read( self.tctor )

            self.startdate = tlr.getStartDate()
            self.finishdate = tlr.getFinishDate()

            file_attrs.clear()
            file_attrs.update( tlr.getAttrs() )

            tctor = make_TestConstructor( file_attrs )

            for xdir,tcase in tlr.getTests().items():

                t = self.tcasemap.get( xdir, None )
                if t != None:
                    tctor.resetTestID( t.getSpec() )
                    copy_test_results( t, tcase )
                    if not preserve_skips:
                        t.getStat().removeAttr( 'skip' )

        return file_attrs

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

    def encodeIntegerWarning(self):
        ""
        # magic: move this encoding logic out of this class
        ival = 0
        for tcase in self.tcasemap.values():
            if not tcase.getStat().skipTest():
                result = tcase.getStat().getResultStatus()
                if   result == 'diff'   : ival |= ( 2**1 )
                elif result == 'fail'   : ival |= ( 2**2 )
                elif result == 'timeout': ival |= ( 2**3 )
                elif result == 'notdone': ival |= ( 2**4 )
                elif result == 'notrun' : ival |= ( 2**5 )
        return ival

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


def glob_results_files( basename ):
    ""
    assert basename
    fileL = glob.glob( basename+'.*' )
    fileL.sort()
    return fileL


def make_TestConstructor( file_attrs ):
    ""
    tctor = TestConstructor()

    nc = file_attrs.get( 'shortxdirs', None )
    if nc != None:
        tctor.setShorten( int(nc) )

    return tctor
