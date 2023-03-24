#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys

from .pathutil import is_subdir


class TestFilter:

    def __init__(self, rtconfig, user_plugin):
        ""
        self.rtconfig = rtconfig
        self.plugin = user_plugin
        self.skipped = {}  # test id to TestCase

    def checkSubdirectory(self, tcase, subdir):
        ""
        ok = True

        tspec = tcase.getSpec()
        xdir = tspec.getExecuteDirectory()
        if subdir and subdir != xdir and not is_subdir( subdir, xdir ):
            ok = False
            tcase.getStat().markSkipBySubdirectoryFilter()

        self._record_skipped_tests( ok, tcase )
        return ok

    def checkEnabled(self, tcase):
        ""
        tspec = tcase.getSpec()
        ok = tspec.isEnabled()
        if not ok:
            tcase.getStat().markSkipByEnabled()

        self._record_skipped_tests( ok, tcase )
        return ok

    def checkSkipped(self, tcase):
        ""
        tspec = tcase.getSpec()
        ok = tspec.skip_reason is None
        if not ok:
            tcase.getStat().markSkipped(tspec.skip_reason)
        self._record_skipped_tests( ok, tcase )
        return ok

    def checkPlatform(self, tcase):
        ""
        tspec = tcase.getSpec()

        wx = tspec.getPlatformEnableExpression()
        ok = self.rtconfig.evaluate_platform_include( wx )

        if not ok:
            tcase.getStat().markSkipByPlatform()

        self._record_skipped_tests( ok, tcase )
        return ok

    def checkOptions(self, tcase):
        ""
        tspec = tcase.getSpec()

        optexpr = tspec.getOptionEnableExpression()
        ok = self.rtconfig.evaluate_option_expr( optexpr )

        if not ok:
            tcase.getStat().markSkipByOption()

        self._record_skipped_tests( ok, tcase )
        return ok

    def checkKeywords(self, tcase, results_keywords=True):
        ""
        tspec = tcase.getSpec()

        kwlist = tspec.getKeywords() + tcase.getStat().getResultsKeywords()

        if results_keywords:
            ok = self.rtconfig.satisfies_keywords( kwlist, True )
            if not ok:
                nr_ok = self.rtconfig.satisfies_keywords( kwlist, False )
                if nr_ok:
                    # only mark failed by results keywords if including
                    # results keywords is what causes it to fail
                    tcase.getStat().markSkipByKeyword( with_results=True )
                else:
                    tcase.getStat().markSkipByKeyword( with_results=False )

        else:
            ok = self.rtconfig.satisfies_keywords( kwlist, False )
            if not ok:
                tcase.getStat().markSkipByKeyword( with_results=False )

        self._record_skipped_tests( ok, tcase )
        return ok

    def checkTDD(self, tcase):
        ""
        tspec = tcase.getSpec()

        ok = self.rtconfig.evaluate_TDD( tspec.getKeywords() )

        if not ok:
            tcase.getStat().markSkipByTDD()

        self._record_skipped_tests( ok, tcase )
        return ok

    def checkParameters(self, tcase, permanent=True):
        ""
        tspec = tcase.getSpec()

        if tspec.isAnalyze():
            # analyze tests are not excluded by parameter expressions
            ok = True
        else:
            ok = self.rtconfig.evaluate_parameters( tspec.getParameters() )

        if not ok:
            tcase.getStat().markSkipByParameter( permanent=permanent )

        self._record_skipped_tests( ok, tcase )
        return ok

    def checkFileSearch(self, tcase):
        ""
        tspec = tcase.getSpec()

        ok = self.rtconfig.evaluate_file_search(
                            tspec.getFilename(),
                            tspec.getName(),
                            tspec.getParameters(),
                            tspec.getLinkFiles()+tspec.getCopyFiles() )

        if not ok:
            tcase.getStat().markSkipByFileSearch()

        self._record_skipped_tests( ok, tcase )
        return ok

    def checkMaxSize(self, tcase):
        ""
        tspec = tcase.getSpec()

        ok = self.rtconfig.evaluate_maxprocs( tcase.getSize() )
        if not ok:
            tcase.getStat().markSkipByMaxProcessors()
        else:
            ok = self.rtconfig.evaluate_maxdevices( tcase.getSize() )
            if not ok:
                tcase.getStat().markSkipByMaxDevices()

        self._record_skipped_tests( ok, tcase )
        return ok

    def checkRuntime(self, tcase):
        ""
        ok = True

        tm = tcase.getStat().getRuntime( None )
        if tm != None and not self.rtconfig.evaluate_runtime( tm ):
            ok = False
        if not ok:
            tcase.getStat().markSkipByRuntime()

        self._record_skipped_tests( ok, tcase )
        return ok

    def userValidation(self, tcase):
        ""
        ok = True

        reason = self.plugin.validateTest( tcase )
        if reason:
            ok = False
            reason = 'validate: '+reason
            tcase.getStat().markSkipByUserValidation( reason )

        self._record_skipped_tests( ok, tcase )
        return ok

    def checkAnalyze(self, analyze_tcase, analyze_deps):
        """
        Certain analyze dependency skips cause the analyze test to be skipped.
        If analyze dependencies are skipped in a way that does NOT cause the
        analyze test to be skipped, then the analyze parameter set must be
        adjusted to reflect the reduced dependencies.
        """
        skip_analyze = False
        paramsets = []

        for tcase in analyze_deps:
            if tcase.getStat().skipTestCausingAnalyzeSkip():
                skip_analyze = True
            else:
                paramsets.append( tcase.getSpec().getParameters() )

        if skip_analyze:
            if not analyze_tcase.getStat().skipTest():
                analyze_tcase.getStat().markSkipByAnalyzeDependency()
            self._record_skipped_tests( False, analyze_tcase )
        else:
            pset = analyze_tcase.getSpec().getParameterSet()
            pset.intersectionFilter( paramsets )

            # skip the analyze test if all dependencies are skipped
            if pset.isEmpty():
                analyze_tcase.getStat().markSkipByAnalyzeDependency()
                self._record_skipped_tests( False, analyze_tcase )

    def applyBaselineSkips(self, tcase_map):
        ""
        for xdir,tcase in tcase_map.items():
            tspec = tcase.getSpec()
            if not tcase.getStat().skipTest():
                if not tspec.hasBaseline():
                    tcase.getStat().markSkipByBaselineHandling()
                    self._record_skipped_tests( False, tcase )

    def applyPermanent(self, tcase_map):
        ""
        for tcase in tcase_map.values():

            self.checkParameters( tcase, permanent=True ) and \
                self.checkKeywords( tcase, results_keywords=False ) and \
                self.checkEnabled( tcase ) and \
                self.checkSkipped( tcase ) and \
                self.checkPlatform( tcase ) and \
                self.checkOptions( tcase ) and \
                self.checkTDD( tcase ) and \
                self.checkFileSearch( tcase ) and \
                self.checkMaxSize( tcase ) and \
                self.checkRuntime( tcase ) and \
                self.userValidation( tcase )

        self.filterByCummulativeRuntime( tcase_map )

    def applyRuntime(self, tcase_map, filter_dir, force_checks=False):
        ""
        subdir = normalize_filter_directory( filter_dir )

        for tcase in tcase_map.values():

            tspec = tcase.getSpec()

            if not tcase.getStat().skipTest() or force_checks:

                self.checkSubdirectory( tcase, subdir ) and \
                    self.checkKeywords( tcase, results_keywords=True ) and \
                    self.checkParameters( tcase, permanent=False ) and \
                    self.checkTDD( tcase ) and \
                    self.checkMaxSize( tcase ) and \
                    self.checkRuntime( tcase )

                # these don't work in restart mode because they require
                # the test file to be reparsed
                #   self.checkFileSearch( tcase )
                #   self.checkEnabled( tcase )
                #   self.userValidation( tcase )
                #   self.checkPlatform( tcase )
                #   self.checkOptions( tcase )

        self.filterByCummulativeRuntime( tcase_map )

    def filterByCummulativeRuntime(self, tcase_map):
        ""
        rtsum = self.rtconfig.getRuntimeSum()
        if rtsum is not None:

            # first, generate list with times
            tL = []
            for tcase in tcase_map.values():
                tm = tcase.getStat().getRuntime( None )
                if tm is None: tm = 0
                xdir = tcase.getSpec().getDisplayString()
                tL.append( (tm,xdir,tcase) )
            tL.sort()

            # accumulate tests until allowed runtime is exceeded
            tsum = 0.
            i = 0 ; n = len(tL)
            while i < n:
                tm,xdir,tcase = tL[i]
                if not tcase.getStat().skipTest():
                    tsum += tm
                    if tsum > rtsum:
                        tcase.getStat().markSkipByCummulativeRuntime()
                        self._record_skipped_tests( False, tcase )

                i += 1

    def _record_skipped_tests(self, keep_test, tcase):
        ""
        if not keep_test:
            self.skipped[ tcase.getSpec().getID() ] = tcase

    def getSkipped(self):
        ""
        return self.skipped.values()

    def removeNewSkips(self, tcasemap):
        ""
        for tid,tcase in self.skipped.items():
            tcasemap.pop( tid )


def normalize_filter_directory( filter_dir ):
    ""
    subdir = None

    if filter_dir is not None:
        subdir = os.path.normpath( filter_dir )
        if subdir == '' or subdir == '.':
            subdir = None

    return subdir
