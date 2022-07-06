#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import fnmatch


class DependencyPattern:
    """
    A dependency pattern consists of a simple shell pattern (not a regular
    expression), an "expect" pattern applied to the number of dependency match
    results, and an optional word expression to be applied to the test result.

    Example pattern: "subdir/name*.np=8"
    Example word expressions: "pass or diff", "pass"

    The expect pattern is one of
        '+' : one or more matches must be found
        '*' : zero or more matches
        '?' : exactly one match
         N  : an integer number of matches must be found (non-negative)
    """

    def __init__(self, pattern, expect='+', result_word_expr=None):
        ""
        self.pat = pattern
        self.expect = expect
        self.expr = result_word_expr

    def find_deps(self, strict, testfile, params, testcasemap):
        ""
        depL = self._find_tests( testfile, params, testcasemap )
        if self._matched_as_expected( depL, strict ):
            return depL,''
        else:
            errinfo = self._match_info( testfile, params, len(depL) )
            return None,errinfo

    def _find_tests(self, testfile, params, testcasemap):
        ""
        srcdir = os.path.dirname( testfile )
        matchpat = self._make_match_pattern( testfile, params )
        dep_ids = find_tests_by_pattern( srcdir, matchpat, testcasemap )
        depL = [ testcasemap[tid] for tid in dep_ids ]
        return depL

    def _matched_as_expected(self, depL, strict=True):
        ""
        if strict:
            if self.expect == '*':
                return True
            elif self.expect == '?':
                return len( depL ) in [0,1]
            elif self.expect == '+':
                return len( depL ) > 0
            else:
                ival = int( self.expect )
                return len( depL ) == ival

        return True

    def _make_match_pattern(self, testfile, params):
        ""
        srcdir = os.path.dirname( testfile )
        matchpat = apply_variable_substitution( self.pat, params )
        return matchpat

    def _match_info(self, testfile, params, num_matches):
        ""
        infL = [ '   test file='+repr(testfile) ]
        depline = '   depends on pattern='+repr(self.pat)
        matchpat = self._make_match_pattern( testfile, params )
        if matchpat != self.pat:
            depline += ' (expanded='+repr(matchpat)+')'
        depline += ', match(es) expected='+repr(self.expect)
        depline += ', but got '+repr(num_matches)
        infL.append( depline )
        return '\n'.join( infL )


class TestDependency:

    def __init__(self, tcase, matchpat, wordexpr):
        ""
        self.tcase = tcase
        self.matchpat = matchpat
        self.wordexpr = wordexpr

    def getTestID(self):
        ""
        return self.tcase.getSpec().getID()

    def ranOrCouldRun(self):
        ""
        tstat = self.tcase.getStat()

        if tstat.isNotrun() and tstat.skipTest():
            return False

        return True

    def satisfiesResult(self):
        ""
        result = self.tcase.getStat().getResultStatus()

        if self.wordexpr is None:
            if result not in ['pass','diff']:
                return False

        elif not self.wordexpr.evaluate( result ):
            return False

        return True

    def getMatchDirectory(self):
        ""
        return self.matchpat, self.tcase.getSpec().getExecuteDirectory()

    def isBlocking(self):
        ""
        tstat = self.tcase.getStat()

        if tstat.isDone() or tstat.skipTest():
            if not self.satisfiesResult():
                return True

        elif tstat.isNotDone():
            return True

        else:
            assert tstat.isNotrun()

            if self.tcase.willNeverRun():
                if not self.satisfiesResult():
                    return True
            else:
                return True

        return False

    def blockedReason(self):
        ""
        return self.tcase.getSpec().getDisplayString()

    def willNeverRun(self):
        ""
        tstat = self.tcase.getStat()

        if tstat.isDone() or tstat.skipTest():
            if not self.satisfiesResult():
                return True

        elif tstat.isNotrun() and self.tcase.willNeverRun():
            if not self.satisfiesResult():
                return True

        return False


class FailedTestDependency:
    """
    For test dependencies that will never be satisfied, such as when a
    'depends on' globbing match criterion is not satisfied.
    """
    def __init__(self, reason): self.reason = reason
    def getTestID(self): return None
    def ranOrCouldRun(self): return False
    def satisfiesResult(self): return False
    def getMatchDirectory(self): return None,None
    def isBlocking(self): return True
    def blockedReason(self): return self.reason
    def willNeverRun(self): return True


def find_tests_by_pattern( srcdir, pattern, testcasemap ):
    """
    The 'srcdir' is the directory of the dependent test source file relative
    to the scan root.  The shell glob 'pattern' is matched against the match
    strings of tests in the 'testcasemap', in this order:

        1. srcdir/pat
        2. srcdir/*/pat
        3. pat
        4. *pat

    The first of these that matches at least one test will be returned.

    If more than one staged test is matched, then only the last stage is
    included (unless none of them are a last stage, in which case all of
    them are included).

    A python set of TestSpec ID is returned.
    """
    if srcdir == '.':
        srcdir = ''
    elif srcdir:
        srcdir += '/'

    pat1 = os.path.normpath( srcdir+pattern )
    pat2 = srcdir+'*/'+pattern
    pat3 = pattern
    pat4 = '*'+pattern

    L1 = [] ; L2 = [] ; L3 = [] ; L4 = []

    for tid,tcase in testcasemap.items():

        tspec = tcase.getSpec()
        displ = tspec.getTestID().computeMatchString()

        if fnmatch.fnmatch( displ, pat1 ):
            L1.append( tid )

        if fnmatch.fnmatch( displ, pat2 ):
            L2.append( tid )

        if fnmatch.fnmatch( displ, pat3 ):
            L3.append( tid )

        if fnmatch.fnmatch( displ, pat4 ):
            L4.append( tid )

    for L in [ L1, L2, L3, L4 ]:
        if len(L) > 0:
            return collect_matching_test_ids( L, testcasemap )

    return set()


def collect_matching_test_ids( idlist, testcasemap ):
    ""
    idset = set()

    stagemap = map_staged_test_id_to_tspec_list( idlist, testcasemap )

    for tid in idlist:
        tspec = testcasemap[tid].getSpec()
        if not_duplicate_stage( tspec, stagemap ):
            idset.add( tid )

    return idset


def not_duplicate_stage( tspec, stagemap ):
    """
    if the expression matched more than one stage of a staged test, we only
    want to keep the last stage
    """
    tid = tspec.getTestID().computeID( compress_stage=True )
    stagL = stagemap.get( tid, None )

    if stagL == None or len(stagL) == 1:
        # not part of a staged test or only a single stage matched
        return True

    return tspec.isLastStage() or no_last_stages( stagL )


def no_last_stages( tspecs ):
    ""
    for tspec in tspecs:
        if tspec.isLastStage():
            return False

    return True


def map_staged_test_id_to_tspec_list( idlist, testcasemap ):
    ""
    stagemap = {}

    for tid in idlist:
        tspec = testcasemap[tid].getSpec()
        if tspec.getStageID() != None:
            add_test_to_map( stagemap, tspec )

    return stagemap


def add_test_to_map( stagemap, tspec ):
    ""
    tid = tspec.getTestID().computeID( compress_stage=True )
    tL = stagemap.get( tid, None )
    if tL == None:
        stagemap[tid] = [tspec]
    else:
        tL.append( tspec )


def apply_variable_substitution( pat, paramD ):
    ""
    for n,v in paramD.items():
        pat = pat.replace( '${'+n+'}', v )
    return pat


def connect_analyze_dependencies( analyze, tcaseL, testcasemap ):
    ""
    for tcase in tcaseL:
        tspec = tcase.getSpec()
        if not tspec.isAnalyze():
            connect_dependency( analyze, tcase )
            gxt = testcasemap.get( tspec.getID(), None )
            if gxt != None:
                gxt.setHasDependent()


def check_connect_dependencies( tcase, testcasemap, strict=True ):
    ""
    tspec = tcase.getSpec()

    for dpat in tspec.getDependencyPatterns():

        depL,info = dpat.find_deps( strict, tspec.getFilepath(), tspec.getParameters(), testcasemap )

        if depL is None:
            # print ( 'magic: failed dep '+tspec.getDisplayString()+'\n' + info )
            connect_failed_dependency( tcase, info )
        else:
            for dep in depL:
                connect_dependency( tcase, dep, dpat.pat, dpat.expr )

def connect_dependency( from_tcase, to_tcase, pattrn=None, expr=None ):
    ""
    testdep = TestDependency( to_tcase, pattrn, expr )
    from_tcase.addDependency( testdep )

    to_tcase.setHasDependent()


def connect_failed_dependency( from_tcase, info ):
    ""
    testdep = FailedTestDependency( "failed 'depends on' matching criteria" )
    from_tcase.addDependency( testdep )
