#!/usr/bin/env python 

import os, sys

from .teststatus import TestStatus


class TestCase:

    def __init__(self, testspec, nodesize=None):
        ""
        self.tspec = testspec
        self.nsize = nodesize
        self.tstat = TestStatus()

        self.deps = []
        self.depdirs = {}  # xdir -> match pattern
        self.has_dependent = False

    def getSpec(self):
        ""
        return self.tspec

    def getStat(self):
        ""
        return self.tstat

    def getSize(self):
        ""
        return determine_test_size( self.getSpec().getParameters(), self.nsize )

    def setHasDependent(self):
        ""
        self.has_dependent = True

    def hasDependent(self):
        ""
        return self.has_dependent

    def addDependency(self, testdep):
        ""
        append = True
        for i,tdep in enumerate( self.deps ):
            if tdep.getTestID() == testdep.getTestID():
                # if same test ID, overwrite
                self.deps[i] = testdep
                append = False
                break

        if append:
            self.deps.append( testdep )

            if testdep.ranOrCouldRun():
                pat,depdir = testdep.getMatchDirectory()
                self.addDepDirectory( pat, depdir )

    def numDependencies(self):
        ""
        return len( self.deps )

    def isBlocked(self):
        ""
        for tdep in self.deps:
            if tdep.isBlocking():
                return True
        return False

    def getBlockedReason(self):
        ""
        for tdep in self.deps:
            if tdep.isBlocking():
                return tdep.blockedReason()
        return ''

    def willNeverRun(self):
        ""
        for tdep in self.deps:
            if tdep.willNeverRun():
                return True

        return False

    def addDepDirectory(self, match_pattern, exec_dir):
        ""
        if exec_dir:
            self.depdirs[ exec_dir ] = match_pattern

    def getDepDirectories(self):
        ""
        dirlist = []
        for dep_dir,match_pattern in self.depdirs.items():
            dirlist.append( (match_pattern,dep_dir) )
        return dirlist


def determine_test_size( params, nodesize ):

    np = max( 1, int( params['np'] ) )      if 'np'      in params else 0
    nd = max( 0, int( params['ndevice'] ) ) if 'ndevice' in params else 0
    nn = max( 1, int( params['nnode'] ) )   if 'nnode'   in params else 0

    if nodesize:
        ppn,dpn = nodesize
    else:
        ppn,dpn = None,None

    if ppn:
        if np and nn:
            np = max( np, nn*ppn )
        elif nn:
            np = nn*ppn
    if not np:
        np = 1

    if dpn:
        if nd and nn:
            nd = max( nd, nn*dpn )
        elif nn:
            nd = nn*dpn
    if not nd:
        nd = 0

    return np,nd
