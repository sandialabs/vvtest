#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import join as pjoin

from . import outpututils
from .pathutil import change_directory
from . import importutil
from . import pathid


class UserPluginBridge:

    def __init__(self, rtconfig, plugin_module):
        ""
        self.rtconfig = rtconfig
        self.plugin = plugin_module

        self._probe_for_functions()

        # avoid flooding output if the user plugin has an error (which
        # raises an exception) by only printing the traceback once for
        # each exception string
        self.exc_uniq = set()

        self.idcache = pathid.TestPathIdentification()

    def callPrologue(self, command_line):
        ""
        if self.prolog is not None:
            try:
                self.prolog( command_line )
            except Exception:
                xs,tb = outpututils.capture_traceback( sys.exc_info() )
                sys.stdout.write( '\n' + tb + '\n' )

    def callResultsDir(self):
        ""
        resdir = None

        if self.resultsdir is not None:
            platname = self.rtconfig.getPlatformName()
            options = self.rtconfig.getOptionList()
            try:
                resdir = self.resultsdir( platname, options )
            except Exception:
                xs,tb = outpututils.capture_traceback( sys.exc_info() )
                sys.stdout.write( '\n' + tb + '\n' )

        return resdir

    def callEpilogue(self, rundir, tcaselist):
        ""
        if self.epilog is not None and os.path.isdir(rundir):
            testD = convert_test_list_to_info_dict( self.rtconfig,
                                                    rundir,
                                                    tcaselist,
                                                    self.idcache )
            try:
                with change_directory( rundir ):
                    self.epilog( testD )
            except Exception:
                xs,tb = outpututils.capture_traceback( sys.exc_info() )
                sys.stdout.write( '\n' + tb + '\n' )

    def validateTest(self, tcase):
        """
        Returns non-empty string (an explanation) if user validation fails.
        """
        rtn = None
        if self.validate is not None:
            specs = make_test_to_user_interface_dict( self.rtconfig, tcase, self.idcache )
            try:
                rtn = self.validate( specs )
            except Exception:
                xs,tb = outpututils.capture_traceback( sys.exc_info() )
                self._check_print_exc( xs, tb )
                rtn = xs.strip().replace( '\n', ' ' )[:160]

        return rtn

    def testTimeout(self, tcase):
        """
        Returns None for no change or an integer value.
        """
        return self._call_time_function( tcase, self.timeout )

    def testRuntime(self, tcase):
        """
        Returns None for no change or an integer value.
        """
        return self._call_time_function( tcase, self.runtime )

    def testPreload(self, tcase):
        """
        May modify os.environ and return value is either None/empty or
        a string containing the python to use.
        """
        prog = None

        if self.preload is not None:
            specs = make_test_to_user_interface_dict( self.rtconfig, tcase, self.idcache )
            try:
                label = tcase.getSpec().getPreloadLabel()
                if label:
                    specs['preload'] = label
                prog = self.preload( specs )
                if prog is not None:
                    if type(prog) != type(''):
                        raise Exception( "function 'preload' returned an object "
                            "of type "+str(type(prog))+" but only None or "
                            "string are allowed" )
                    if not prog.strip():
                        raise Exception( "function 'preload' returned an "
                            "empty string" )
            except Exception:
                xs,tb = outpututils.capture_traceback( sys.exc_info() )
                sys.stdout.write( '\n' + tb + '\n' )
                prog = None

        return prog

    def _call_time_function(self, tcase, func):
        ""
        rtn = None

        if func is not None:
            specs = make_test_to_user_interface_dict( self.rtconfig, tcase, self.idcache )
            try:
                rtn = func( specs )
                if rtn is not None:
                    rtn = max( 0, int(rtn) )
            except Exception:
                xs,tb = outpututils.capture_traceback( sys.exc_info() )
                self._check_print_exc( xs, tb )
                rtn = None

        return rtn

    def _probe_for_functions(self):
        ""
        self.validate = None
        if self.plugin and hasattr( self.plugin, 'validate_test' ):
            self.validate = self.plugin.validate_test

        self.timeout = None
        if self.plugin and hasattr( self.plugin, 'test_timeout' ):
            self.timeout = self.plugin.test_timeout

        self.preload = None
        if self.plugin and hasattr( self.plugin, 'test_preload' ):
            self.preload = self.plugin.test_preload

        self.prolog = None
        if self.plugin and hasattr( self.plugin, 'prologue' ):
            self.prolog = self.plugin.prologue

        self.epilog = None
        if self.plugin and hasattr( self.plugin, 'epilogue' ):
            self.epilog = self.plugin.epilogue

        self.runtime = None
        if self.plugin and hasattr( self.plugin, 'test_runtime' ):
            self.runtime = self.plugin.test_runtime

        self.resultsdir = None
        if self.plugin and hasattr( self.plugin, 'results_directory' ):
            self.resultsdir = self.plugin.results_directory

    def _check_print_exc(self, xs, tb):
        ""
        if xs not in self.exc_uniq:
            sys.stdout.write( '\n' + tb + '\n' )
            self.exc_uniq.add( xs )


def convert_test_list_to_info_dict( rtconfig, rundir, tcaselist, idcache ):
    ""
    testD = {}

    for tcase in tcaselist:

        infoD = make_test_to_user_interface_dict( rtconfig, tcase, idcache )

        tspec = tcase.getSpec()
        tstat = tcase.getStat()

        result = tstat.getResultStatus()
        xdir = tspec.getExecuteDirectory()

        infoD[ 'result'  ] = result
        infoD[ 'runtime' ] = tstat.getRuntime( None )
        infoD[ 'rundir'  ] = xdir
        infoD[ 'timeout' ] = tstat.getAttr( 'timeout', None )

        if tstat.skipTest():
            infoD['skip'] = tstat.getReasonForSkipTest()
        elif result not in ['notrun','skip']:
            log = outpututils.get_log_file_path( rundir, tspec )
            infoD['command'] = outpututils.get_test_command_line( log )

        testD[ tspec.getDisplayString() ] = infoD

    return testD


def make_test_to_user_interface_dict( rtconfig, tcase, idcache ):
    ""
    tspec = tcase.getSpec()
    testid = idcache.get_testid( tspec.getFilename(), tspec.getID() )

    specs = {
        'name'       : tspec.getName(),
        'keywords'   : tspec.getKeywords( include_implicit=False ),
        'parameters' : tspec.getParameters(),
        'timeout'    : tspec.getTimeout(),
        'platform'   : rtconfig.getPlatformName(),
        'options'    : rtconfig.getOptionList(),
        'testid'     : testid,
    }

    return specs


def import_user_plugin( modulename ):
    ""
    mod = None
    err = ''

    try:
        mod = importutil.import_file_from_sys_path( modulename+'.py' )
    except Exception:
        xs,tb = outpututils.capture_traceback( sys.exc_info() )
        err = tb

    return mod, err
