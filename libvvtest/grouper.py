#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
import os

from . import TestList


class BatchTestGrouper:

    def __init__(self, tlist, batch_length):
        ""
        self.tlist = tlist

        if batch_length is None:
            self.tsize = 30*60
        else:
            self.tsize = batch_length

    def createGroups(self):
        ""
        self._process_groups()
        self._sort_groups()

    def getGroups(self):
        ""
        return self.batches

    def _sort_groups(self):
        ""
        sortL = []
        for grp in self.batches:
            sortL.append( ( grp.makeSortableKey(), grp ) )
        sortL.sort( reverse=True )

        self.batches = [ grp for _,grp in sortL ]

    def _process_groups(self):
        ""
        self.batches = []
        self.group = None
        self.num_groups = 0

        back = self.tlist.getActiveTests()
        back.sort(
            key=lambda tc: [ tc.getSize()[0], tc.getStat().getAttr('timeout') ],
            reverse=True )

        for tcase in back:
            assert tcase.getSpec().constructionCompleted()
            self._add_test_case( tcase )

        if self.group != None and not self.group.empty():
            self.batches.append( self.group )

    def _add_test_case(self, tcase):
        ""
        timeval = tcase.getStat().getAttr('timeout')

        if tcase.numDependencies() > 0:
            # tests with dependencies (like analyze tests) get their own group
            self._add_single_group( tcase, timeval )

        elif timeval < 1:
            # a zero timeout means no limit
            self._add_single_group( tcase, 0 )

        else:
            self._check_start_new_group( tcase )

    def _check_start_new_group(self, tcase):
        ""
        size = tcase.getSize()
        timeval = tcase.getStat().getAttr('timeout')

        if self.group is None:
            self.group = self._make_new_group()

        elif self.group.needNewGroup( size, timeval, self.tsize ):
            self.batches.append( self.group )
            self.group = self._make_new_group()

        self.group.appendTest( tcase, timeval )

    def _add_single_group(self, tcase, timeval):
        ""
        grp = self._make_new_group()
        grp.appendTest( tcase, timeval )
        self.batches.append( grp )

    def _make_new_group(self):
        ""
        grplist = TestList.TestList( self.tlist.getTestCaseFactory() )
        grp = BatchGroup( grplist, self.num_groups )
        self.num_groups += 1
        return grp


class BatchGroup:

    def __init__(self, testlist, groupid):
        ""
        self.groupid = groupid
        self.tlist = testlist

        self.size = None
        self.tsum = 0

    def getTests(self):
        ""
        return self.tlist.getTests()

    def getTime(self):
        ""
        return self.tsum

    def appendTest(self, tcase, timeval):
        ""
        if self.size is None:
            self.size = tcase.getSize()
        self.tlist.addTest( tcase )
        self.tsum += timeval

    def getTestList(self):
        ""
        return self.tlist

    def empty(self):
        ""
        return len( self.tlist.getTests() ) == 0

    def needNewGroup(self, size, timeval, tlimit):
        ""
        if len( self.tlist.getTests() ) > 0:
            if self.size != size or self.tsum + timeval > tlimit:
                return True

        return False

    def makeSortableKey(self):
        ""
        return ( self.tsum, self.size, self.groupid )


def partition_tests( tlist, numparts ):
    ""
    grpr = BatchTestGrouper( tlist, None )
    grpr.createGroups()

    tL = []
    for grp in grpr.getGroups():
        # print('magic: group id',grp.groupid)
        # print('magic: part tlist name',grp.getTestList().getFilename())
        tL.append( grp.getTestList() )

    return tL
