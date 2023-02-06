#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys

from .testexec import TestExec
from .backlog import TestBacklog


class TestExecList:

    def __init__(self, tlist, handler):
        ""
        self.tlist = tlist
        self.handler = handler

        self.backlog = TestBacklog()
        self.started = {}  # TestSpec ID -> TestExec object
        self.stopped = {}  # TestSpec ID -> TestExec object

        self._prepare_test_backlog()

    def createExecutionDirectories(self):
        """
        Creates the execution directory for each test to be run.
        """
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
        Return the number of tests currently running.
        """
        return len(self.started)

    def _move_to_started(self, tcase):
        ""
        tid = tcase.getSpec().getID()

        texec = TestExec( tcase )
        self.handler.initialize_for_execution( texec )

        self.started[ tid ] = texec

        return texec

    def _prepare_test_backlog(self):
        ""
        tL = self.tlist.getActiveTests()
        for tcase in tL:
            assert tcase.getSpec().constructionCompleted()
            self.backlog.insert( tcase )

        # sort by runtime, descending order so that popNext() will try to avoid
        # launching long running tests at the end of the testing sequence
        self.backlog.sort()

        for tcase in tL:
            tcase.getStat().resetResults()
