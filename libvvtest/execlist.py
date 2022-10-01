#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys

from .testexec import TestExec
from .teststatus import copy_test_results
from .backlog import TestBacklog


class TestExecList:

    def __init__(self, tlist, handler):
        ""
        self.tlist = tlist
        self.handler = handler

        # magic: have the backlog passed in as an argument
        self.backlog = TestBacklog()
        self.started = {}  # TestSpec ID -> TestExec object
        self.stopped = {}  # TestSpec ID -> TestExec object

    def getTestCaseFactory(self):
        ""
        return self.tlist.getTestCaseFactory()

    def createTestExecs(self):
        """
        Creates the set of TestExec objects from the active test list.
        """
        # magic: change this function to only call the create_execution_directory,
        #        change its name, and move the backlog population elsewhere

        self._generate_backlog_from_testlist()

        for tcase in self.backlog.iterate():
            self.handler.create_execution_directory( tcase )

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
        tcase = self.backlog.pop_by_size( maxsize )
        if tcase is None and len(self.started) == 0:
            # find longest runtime test without size constraint
            tcase = self.backlog.pop_by_size( None )

        if tcase is not None:
            return self._move_to_started( tcase )

        return None

    def consumeBacklog(self):
        ""
        for tcase in self.backlog.consume():
            texec = self._move_to_started( tcase )
            yield texec

    def consumeTest(self, tcase):
        ""
        # magic: assert that tcase is in tlist
        assert False  # magic: WIP

    def popRemaining(self):
        """
        All remaining tests are removed from the backlog and returned as a
        list of (testexec,blocked_reason).
        """
        tL = []
        for tcase in self.backlog.consume():
            tL.append( tcase )
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
        # magic: this should be decided by the type of TestBacklog object
        self.backlog.sort( secondary='timeout' )

    def getNextTest(self):
        ""
        # magic: is this function needed??
        return self.backlog.pop()

    def checkStateChange(self, testid, teststatus):
        """
        Finds the test in the TestList and compares its test status to the
        given argument. If the status is different, the status results are
        copied into the TestList's copy, the test results are appended to
        the results file, and non-None is returned. If the status has not
        changed, returns None.
        """
        tcase = self.tlist.getTestMap()[testid]

        old = tcase.getStat().getResultStatus()
        new = teststatus.getResultStatus()

        if new != old:
            copy_test_results( tcase.getStat(), teststatus )
            self.tlist.appendTestResult( tcase )
            return tcase

        return None  # return None if no state change

    def _move_to_started(self, tcase):
        ""
        tid = tcase.getSpec().getID()

        texec = TestExec( tcase )
        self.handler.initialize_for_execution( texec )

        self.started[ tid ] = texec

        return texec

    def _generate_backlog_from_testlist(self):
        ""
        # magic: move this function into TestBacklog ?? somewhere else?
        for tcase in self.tlist.getTests():
            if not tcase.getStat().skipTest():
                assert tcase.getSpec().constructionCompleted()
                # texec = TestExec( tcase )
                self.backlog.insert( tcase )

        # sort by runtime, descending order so that popNext() will try to avoid
        # launching long running tests at the end of the testing sequence
        self.backlog.sort()
