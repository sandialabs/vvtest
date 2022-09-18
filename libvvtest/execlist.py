#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys

from .testexec import TestExec
from . import depend
from .teststatus import copy_test_results


class TestExecList:

    def __init__(self, tlist, handler):
        ""
        self.tlist = tlist
        self.handler = handler

        self.backlog = TestBacklog()
        self.waiting = {}  # TestSpec ID -> TestExec object
        self.started = {}  # TestSpec ID -> TestExec object
        self.stopped = {}  # TestSpec ID -> TestExec object

    def getTestCaseFactory(self):
        ""
        return self.tlist.getTestCaseFactory()

    def createTestExecs(self, check_dependencies=True):
        """
        Creates the set of TestExec objects from the active test list.
        """
        self._generate_backlog_from_testlist()
        self._sort_by_size_and_runtime()
        self._connect_execute_dependencies( check_dependencies )

        for texec in self.backlog.iterate():
            self.handler.initialize_for_execution( texec )

    def getExecutionHandler(self):
        ""
        return self.handler

    def popNext(self, maxsize):
        """
        Finds a test to execute.  Returns a TestExec object, or None if no
        test can run.  In this latter case, one of the following is true

            1. there are not enough free processors to run another test
            2. the only tests left have a dependency with a bad result (like
               a fail) preventing the test from running

        For case #2, numRunning() will be zero.
        """
        # find longest runtime test with size constraint
        texec = self._pop_next_test( maxsize )
        if texec == None and len(self.started) == 0:
            # find longest runtime test without size constraint
            texec = self._pop_next_test( None )

        if texec != None:
            self._move_to_started( texec )

        return texec

    def consumeBacklog(self):
        ""
        for texec in self.backlog.consume():
            tcase = texec.getTestCase()
            self.waiting[ tcase.getSpec().getID() ] = tcase
            self._move_to_started( texec )
            yield texec

    def popRemaining(self):
        """
        All remaining tests are removed from the backlog and returned as a
        list of (testexec,blocked_reason).
        """
        tL = []
        for texec in self.backlog.consume():
            tcase = texec.getTestCase()
            tL.append( (texec,tcase.getBlockedReason()) )
        return tL

    def getRunning(self):
        """
        Return the list of TestExec that are still running.
        """
        return self.started.values()

    def testDone(self, texec):
        ""
        tcase = texec.getTestCase()
        xid = tcase.getSpec().getID()
        self.tlist.appendTestResult( tcase )
        self.started.pop( xid, None )
        self.stopped[ xid ] = texec

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

    def sortBySizeAndTimeout(self):
        ""
        self.backlog.sort( secondary='timeout' )

    def getNextTest(self):
        ""
        texec = self.backlog.pop()

        if texec != None:
            tcase = texec.getTestCase()
            self.waiting[ tcase.getSpec().getID() ] = texec

        return texec

    def checkStateChange(self, tmp_tcase):
        ""
        tid = tmp_tcase.getSpec().getID()

        texec = None

        if tid in self.waiting:
            if tmp_tcase.getStat().isNotDone():
                texec = self.waiting.pop( tid )
                self.started[ tid ] = texec
            elif tmp_tcase.getStat().isDone():
                texec = self.waiting.pop( tid )
                self.stopped[ tid ] = texec

        elif tid in self.started:
            if tmp_tcase.getStat().isDone():
                texec = self.started.pop( tid )
                self.stopped[ tid ] = texec

        if texec:
            tcase = texec.getTestCase()
            copy_test_results( tcase.getStat(), tmp_tcase.getStat() )
            self.tlist.appendTestResult( tcase )

        return texec

    def _move_to_started(self, texec):
        ""
        tcase = texec.getTestCase()

        tid = tcase.getSpec().getID()

        self.waiting.pop( tid )
        self.started[ tid ] = texec

    def _generate_backlog_from_testlist(self):
        ""
        for tcase in self.tlist.getTests():
            if not tcase.getStat().skipTest():
                assert tcase.getSpec().constructionCompleted()
                texec = TestExec( tcase )
                self.backlog.insert( texec )

    def _sort_by_size_and_runtime(self):
        """
        Sort the TestExec objects by runtime, descending order.  This is so
        popNext() will try to avoid launching long running tests at the end
        of the testing sequence, which can add significantly to the total wall
        time.
        """
        self.backlog.sort()

    def _connect_execute_dependencies(self, strict):
        ""
        tmap = self.tlist.getTestMap()
        groups = self.tlist.getGroupMap()

        for texec in self.backlog.iterate():

            tcase = texec.getTestCase()
            if tcase.getSpec().isAnalyze():
                grpL = groups.getGroup( tcase )
                depend.connect_analyze_dependencies( tcase, grpL, tmap )

            depend.check_connect_dependencies( tcase, tmap, strict )

    def _pop_next_test(self, maxsize):
        ""
        constraint = TestConstraint( maxsize )

        texec = self.backlog.pop( constraint )

        if texec != None:
            tcase = texec.getTestCase()
            self.waiting[ tcase.getSpec().getID() ] = tcase

        return texec


class TestConstraint:

    def __init__(self, maxsize):
        ""
        self.maxsize = maxsize

    def getMaxNP(self):
        ""
        if self.maxsize == None:
            return None
        else:
            return self.maxsize[0]

    def apply(self, texec):
        ""
        tcase = texec.getTestCase()

        if self.maxsize != None:

            np,nd = tcase.getSize()
            maxnp,maxnd = self.maxsize

            if np > maxnp or nd > maxnd:
                return False

        if tcase.isBlocked():
            return False

        return True


class TestBacklog:
    """
    Stores a list of TestExec objects.  They can be sorted either by

        ( num procs, runtime )
    or
        ( num procs, timeout ).

    The former is used for pooled execution, while the latter for collecting
    groups of tests for batching.
    """

    def __init__(self):
        ""
        self.tests = []
        self.testcmp = None

    def insert(self, texec):
        """
        Note: to support streaming, this function would have to use
              self.testcmp to do an insert (rather than an append)
        """
        self.tests.append( texec )

    def sort(self, secondary='runtime'):
        ""
        if secondary == 'runtime':
            self.testcmp = TestExecCompare( make_runtime_key )
        else:
            assert secondary == 'timeout'
            self.testcmp = TestExecCompare( make_timeout_key )

        if sys.version_info[0] < 3:
            self.tests.sort( self.testcmp.compare, reverse=True )
        else:
            self.tests.sort( key=self.testcmp.getKey, reverse=True )

    def pop(self, constraint=None):
        ""
        texec = None

        if constraint:
            idx = self._get_starting_index( constraint.getMaxNP() )
        else:
            idx = 0

        while idx < len( self.tests ):
            if constraint == None or constraint.apply( self.tests[idx] ):
                texec = self.tests.pop( idx )
                break
            idx += 1

        return texec

    def consume(self):
        ""
        while len( self.tests ) > 0:
            texec = self.tests.pop( 0 )
            yield texec

    def iterate(self):
        ""
        for texec in self.tests:
            yield texec

    def _get_starting_index(self, max_np):
        ""
        if max_np == None:
            return 0
        else:
            return bisect_left( self.tests, max_np )


def make_runtime_key( texec ):
    ""
    tcase = texec.getTestCase()
    return [ tcase.getSize()[0], tcase.getStat().getRuntime( 0 ) ]

def make_timeout_key( texec ):
    ""
    tcase = texec.getTestCase()
    return [ tcase.getSize()[0], tcase.getStat().getAttr( 'timeout' ) ]


class TestExecCompare:
    """
    This class is a convenience for supporting Python 2 and 3 sorting.
    Python 2 needs the compare function.  Python 3 just needs a "get key"
    function, which could easily be done without this class.
    """

    def __init__(self, make_key):
        ""
        self.kfunc = make_key

    def compare(self, x, y):
        ""
        k1 = self.kfunc(x)
        k2 = self.kfunc(y)
        if k1 < k2: return -1
        if k2 < k1: return 1
        return 0

    def getKey(self, x):
        ""
        return self.kfunc( x )


def bisect_left( tests, np ):
    ""
    lo = 0
    hi = len(tests)
    while lo < hi:
        mid = (lo+hi)//2
        if np < tests[mid].getTestCase().getSize()[0]: lo = mid+1
        else: hi = mid
    return lo

# To insert into the sorted test list, a specialization of insort_right is
# needed.  The comparison is based on np, and the list is in descending order.
# This function is just the python implementation of bisect.insort_right()
# and would need to be modified to work for this use case.
# def insort_right( a, x, less_than ):
#     ""
#     lo = 0
#     hi = len(a)
#     while lo < hi:
#         mid = (lo+hi)//2
#         if less_than( x, a[mid] ): hi = mid
#         else: lo = mid+1
#     a.insert(lo, x)
