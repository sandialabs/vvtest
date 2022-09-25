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
        """
        Returns ( list of TestCase, failure reason ), where 'reason' is
        None on success.

        If 'strict' is True, then any issue gathering the dependencies is
        treated as a failure. If False, then all matching dependencies are
        gathered and returned in the list.
        """
        depL = self._find_tests( testfile, params, testcasemap )
        if self._matched_as_expected( depL, strict ):
            return depL,None
        else:
            reason = self._make_match_fail_reason( testfile, params, depL )
            return None,reason

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

    def _make_match_fail_reason(self, testfile, params, depL):
        ""
        matchpat = self._make_match_pattern( testfile, params )
        return BadMatchReason( self.pat, matchpat, self.expect, depL )


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

    def getBlocking(self):
        """
        Returns a pair ( is_blocked, blocked_reason ).
        """
        tstat = self.tcase.getStat()

        if tstat.isDone():
            if not self.satisfiesResult():
                return True, BadResultReason( self.tcase, 'is done', self.wordexpr )

        elif tstat.skipTest():
            if not self.satisfiesResult():
                return True, BadResultReason( self.tcase, 'was skipped', self.wordexpr )

        elif tstat.isNotDone():
            return True, SimpleReason( self.tcase, 'is not done' )

        else:
            assert tstat.isNotrun()

            if self.tcase.willNeverRun():
                if not self.satisfiesResult():
                    return True, BadResultReason( self.tcase, 'will never run', self.wordexpr )
            else:
                return True, SimpleReason( self.tcase, 'has not run' )

        return False,None

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
    def getBlocking(self): return True,self.reason
    def willNeverRun(self): return True


class SimpleReason:
    def __init__(self, tcase, reason):
        self.testname = tcase.getSpec().getDisplayString()
        self.reason = reason
    def __str__(self):
        return 'test '+repr(self.testname)+' '+self.reason


class BadResultReason:

    def __init__(self, tcase, state, wordexpr):
        ""
        self.testname = tcase.getSpec().getDisplayString()
        self.state = state
        self.file = tcase.getSpec().getFilepath()

        result = tcase.getStat().getResultStatus()
        tmp = "pass or diff" if wordexpr is None else str(wordexpr)
        self.expr = repr(result)+' does NOT satisfy '+repr(tmp)

    def __str__(self):
        ""
        s =  '\n    - dependency test ' + repr( self.testname ) + ' ' + self.state
        s += '\n    - result expression: '+self.expr
        s += '\n    - dependency filename '+repr(self.file)
        return s


class BadMatchReason:

    def __init__(self, pattern, expanded, expect, deplist):
        ""
        self.pat = pattern
        self.matchpat = expanded
        self.expect = expect
        self.deplist = deplist

    def __str__(self):
        ""
        s =  '\n    - failed "depends on" matching criterion'
        s += '\n    - match pattern: ' + repr(self.pat)
        if self.matchpat != self.pat:
            s += ', expanded = '+repr(self.matchpat)
        s += '\n    - num matches expected: '+repr(self.expect)
        s += '\n    - actual matches: '+repr(len(self.deplist))
        for i,tc in enumerate(self.deplist):
            s += '\n        '+str(i+1)+') '+repr( tc.getSpec().getDisplayString() )
        return s


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

        depL,reason = dpat.find_deps( strict,
                                      tspec.getFilepath(),
                                      tspec.getParameters(), 
                                      testcasemap )

        if depL is None:
            if strict:
                print ( '*** Warning: test "'+tspec.getDisplayString()+'" '+\
                        'will not be run due to dependency:'+str(reason) )
            connect_failed_dependency( tcase, reason )
        else:
            for dep in depL:
                connect_dependency( tcase, dep, dpat.pat, dpat.expr )

def connect_dependency( from_tcase, to_tcase, pattrn=None, expr=None ):
    ""
    testdep = TestDependency( to_tcase, pattrn, expr )
    from_tcase.addDependency( testdep )

    to_tcase.setHasDependent()


def connect_failed_dependency( from_tcase, reason ):
    ""
    testdep = FailedTestDependency( reason )
    from_tcase.addDependency( testdep )
