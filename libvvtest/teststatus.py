#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import time


RESULTS_KEYWORDS = [ 'notrun', 'notdone',
                     'fail', 'diff', 'pass',
                     'timeout', 'skip' ]


DIFF_EXIT_STATUS = 64
SKIP_EXIT_STATUS = 63


PARAM_SKIP = 'param'
RESTART_PARAM_SKIP = 'restartparam'
KEYWORD_SKIP = 'keyword'
RESULTS_KEYWORD_SKIP = 'resultskeyword'
SUBDIR_SKIP = 'subdir'
RUNTIME_SKIP = 'runskip'
ANALYZE_SKIP = 'analyze'

SKIP_REASON = {
        PARAM_SKIP           : 'excluded by parameter expression',
        RESTART_PARAM_SKIP   : 'excluded by parameter expression',
        KEYWORD_SKIP         : 'excluded by keyword expression',
        RESULTS_KEYWORD_SKIP : 'previous result keyword expression',
        SUBDIR_SKIP          : 'current working directory',
        RUNTIME_SKIP         : 'runtime skip returned as exit status',
        'enabled'            : 'disabled',
        'platform'           : 'excluded by platform expression',
        'option'             : 'excluded by option expression',
        'tdd'                : 'TDD test',
        ANALYZE_SKIP         : 'excluded by analyze test filter',
        'search'             : 'excluded by file search expression',
        'maxprocs'           : 'exceeds max processors',
        'maxdevices'         : 'exceeds max devices',
        'runtime'            : 'runtime too low or too high',
        'nobaseline'         : 'no rebaseline specification',
        'depskip'            : 'analyze dependency skipped',
        'tsum'               : 'cummulative runtime exceeded',
    }


class TestStatus:

    def __init__(self):
        ""
        self.attrs = {}

    def setAttr(self, name, value):
        ""
        self.attrs[name] = value

    def hasAttr(self, name):
        return name in self.attrs

    def getAttr(self, name, *args):
        """
        Returns the attribute value corresponding to the attribute name.
        If the attribute name does not exist, an exception is thrown.  If
        the attribute name does not exist and a default value is given, the
        default value is returned.
        """
        if len(args) > 0:
            return self.attrs.get( name, args[0] )
        return self.attrs[name]

    def removeAttr(self, name):
        ""
        self.attrs.pop( name, None )

    def getAttrs(self):
        """
        Returns a copy of the test attributes (a name->value dictionary).
        """
        return dict( self.attrs )

    def resetResults(self):
        ""
        self.attrs['state'] = 'notrun'
        self.removeAttr( 'xtime' )
        self.removeAttr( 'xdate' )

    def getResultsKeywords(self):
        ""
        kL = []

        skip = self.attrs.get( 'skip', None )
        if skip is not None:
            kL.append( 'skip' )

        state = self.attrs.get('state',None)
        if state is None:
            kL.append( 'notrun' )
        else:
            if state == "notrun":
                kL.append( 'notrun' )
            elif state == "notdone":
                kL.extend( ['notdone', 'running'] )

        result = self.attrs.get('result',None)
        if result is not None:
            if result == 'timeout':
                kL.append( 'fail' )
            kL.append( result )

        return kL

    def markSkipByParameter(self, permanent=True):
        ""
        if permanent:
            self.markSkipped(PARAM_SKIP)
        else:
            self.markSkipped(RESTART_PARAM_SKIP)

    def skipTestByParameter(self):
        ""
        return self.attrs.get( 'skip', None ) == PARAM_SKIP

    def markSkipByKeyword(self, with_results=False):
        ""
        if with_results:
            self.markSkipped(RESULTS_KEYWORD_SKIP)
        else:
            self.markSkipped(KEYWORD_SKIP)

    def markSkipBySubdirectoryFilter(self):
        ""
        self.markSkipped(SUBDIR_SKIP)

    def markSkipByEnabled(self):
        ""
        self.markSkipped('enabled')

    def markSkipByPlatform(self):
        ""
        self.markSkipped('platform')

    def markSkipByOption(self):
        ""
        self.markSkipped('option')

    def markSkipByTDD(self):
        ""
        self.markSkipped('tdd')

    def markSkipByFileSearch(self):
        ""
        self.markSkipped('search')

    def markSkipByMaxProcessors(self):
        ""
        self.markSkipped('maxprocs')

    def markSkipByMaxDevices(self):
        ""
        self.markSkipped('maxdevices')

    def markSkipByRuntime(self):
        ""
        self.markSkipped('runtime')

    def markSkipByBaselineHandling(self):
        ""
        self.markSkipped('nobaseline')

    def markSkipByAnalyzeDependency(self):
        ""
        self.markSkipped('depskip')

    def markSkipByAnalyzeTest(self):
        ""
        self.markSkipped(ANALYZE_SKIP)

    def markSkipByCummulativeRuntime(self):
        ""
        self.markSkipped('tsum')

    def markSkipByUserValidation(self, reason):
        ""
        self.markSkipped(reason)

    def markSkipped(self, reason):
        ""
        self.attrs['skip'] = reason


    def skipTestCausingAnalyzeSkip(self):
        ""
        skipit = False

        skp = self.attrs.get( 'skip', None )
        if skp is not None:
            if skp.startswith( PARAM_SKIP ) or \
               skp.startswith( RESTART_PARAM_SKIP ) or \
               skp.startswith( RESULTS_KEYWORD_SKIP ) or \
               skp.startswith( SUBDIR_SKIP ) or \
               skp.startswith( ANALYZE_SKIP ):
                skipit = False
            else:
                skipit = True

        return skipit

    def skipTest(self):
        ""
        return self.attrs.get( 'skip', False )

    def getReasonForSkipTest(self):
        ""
        skip = self.skipTest()
        assert skip
        # a shortened skip reason is mapped to a longer description, but
        # if not found, then just return the skip value itself
        return SKIP_REASON.get( skip, skip )

    def isNotrun(self):
        ""
        # a test without a state is assumed to not have been run
        return self.attrs.get( 'state', 'notrun' ) == 'notrun'

    def isDone(self):
        ""
        return self.attrs.get( 'state', None ) == 'done'

    def isNotDone(self):
        ""
        return self.attrs.get( 'state', None ) == 'notdone'

    def passed(self):
        ""
        return self.isDone() and \
               self.attrs.get( 'result', None ) == 'pass'

    def getResultStatus(self):
        ""
        st = self.attrs.get( 'state', 'notrun' )

        if st == 'notrun':
            return 'notrun'

        elif st == 'done':
            if 'result' not in self.attrs and self.skipTest():
                return 'skip'
            else:
                return self.attrs.get( 'result', 'fail' )

        else:
            return 'notdone'

    def markStarted(self, start_time):
        ""
        self.attrs['state'] = 'notdone'
        self.attrs['xtime'] = -1
        self.attrs['xdate'] = int( 100 * start_time ) * 0.01

    def getStartDate(self, *default):
        ""
        if len( default ) > 0:
            return self.attrs.get( 'xdate', default[0] )
        return self.attrs.get( 'xdate' )

    def getRuntime(self, *default):
        ""
        xt = self.attrs.get( 'xtime', None )
        if xt is None or xt < 0:
            if len( default ) > 0:
                return default[0]
            raise KeyError( "runtime attribute not set" )
        return xt

    def setRuntime(self, num_seconds):
        ""
        self.attrs['xtime'] = num_seconds

    def getTimeoutValue(self, *default):
        ""
        tm = self.attrs.get( 'timeout', None )
        if tm is None or tm < 0:
            if len( default ) > 0:
                return default[0]
            raise KeyError( "timeout attribute not set" )
        return tm

    def setTimeoutValue(self, timeout_seconds):
        ""
        self.attrs['timeout'] = timeout_seconds

    def markDone(self, exit_status, done_time=None):
        ""
        tzero = self.getStartDate()

        self.attrs['state'] = 'done'
        if done_time is None:
            self.setRuntime( int(time.time()-tzero) )
        else:
            self.setRuntime( int(done_time-tzero) )

        self.attrs['xvalue'] = exit_status

        result = translate_exit_status_to_result_string( exit_status )
        if result == 'skip':
            self.attrs['skip'] = RUNTIME_SKIP
        else:
            self.attrs['result'] = result

    def markTimedOut(self, done_time=None):
        ""
        self.markDone( 1, done_time )
        self.attrs['result'] = 'timeout'


def copy_test_results( to_tstat, from_tstat ):
    ""
    from_attrs = from_tstat.getAttrs()

    for k,v in from_attrs.items():
        to_tstat.setAttr( k, v )

    if 'skip' in from_attrs:
        to_tstat.setAttr( 'skip', from_attrs['skip'] )
    else:
        to_tstat.removeAttr( 'skip' )


def translate_exit_status_to_result_string( exit_status ):
    ""
    if exit_status == 0:
        return 'pass'

    elif exit_status == DIFF_EXIT_STATUS:
        return 'diff'

    elif exit_status == SKIP_EXIT_STATUS:
        return 'skip'

    else:
        return 'fail'
