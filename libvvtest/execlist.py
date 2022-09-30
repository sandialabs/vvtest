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

        self.backlog = TestBacklog()
        # magic: TODO: change waiting to TestCase and delay initialize_for_execution
        self.waiting = {}  # TestSpec ID -> TestExec object
        self.started = {}  # TestSpec ID -> TestExec object
        self.stopped = {}  # TestSpec ID -> TestExec object

    def getTestCaseFactory(self):
        ""
        return self.tlist.getTestCaseFactory()

    def createTestExecs(self):
        """
        Creates the set of TestExec objects from the active test list.
        """
        # magic: this function changes to calling the backlog obj with self.tlist
        self._generate_backlog_from_testlist()

        # magic: - add separate function in ExecutionHandler to create the
        #          test exec directory, and only call that function here
        #          (that function only needs TestSpec)
        #        - then for each new TestExec, need to call the handler to
        #          set a few other things in the TestExec object
        for tcase in self.backlog.iterate():
            self.handler.create_execution_directory( tcase )
            # self.handler.initialize_for_execution( texec )

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
        for tcase in self.backlog.consume():
            # tcase = texec.getTestCase()
            texec = TestExec( tcase )
            self.handler.initialize_for_execution( texec )
            self.waiting[ tcase.getSpec().getID() ] = texec
            self._move_to_started( texec )
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
            # magic: don't need texec here
            # tcase = texec.getTestCase()
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
        tcase = self.backlog.pop()

        if tcase is not None:
            # tcase = texec.getTestCase()
            # magic: maybe short term, but create TestExec
            texec = TestExec( tcase )
            self.handler.initialize_for_execution( texec )
            self.waiting[ tcase.getSpec().getID() ] = texec
            return texec

        return None

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
        # magic: have backlog store tcase (not TestExec)
        # magic: move this function into TestBacklog
        for tcase in self.tlist.getTests():
            if not tcase.getStat().skipTest():
                assert tcase.getSpec().constructionCompleted()
                # texec = TestExec( tcase )
                self.backlog.insert( tcase )

        # sort by runtime, descending order so that popNext() will try to avoid
        # launching long running tests at the end of the testing sequence
        self.backlog.sort()

    def _pop_next_test(self, maxsize):
        ""
        tcase = self.backlog.pop_by_size( maxsize )

        if tcase is not None:
            # magic: make a new TestExec and init with handler
            # tcase = texec.getTestCase()
            texec = TestExec( tcase )
            self.handler.initialize_for_execution( texec )
            self.waiting[ tcase.getSpec().getID() ] = texec
            return texec

        return None
