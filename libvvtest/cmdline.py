#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys, os
import re
import time

from . import argutil

from .keyexpr import create_keyword_expression
from .platexpr import create_platform_expression
from .paramexpr import create_parameter_expression
from . import wordcheck
from timeutils import parse_num_seconds

def parse_command_line( argvlist, vvtest_version=None ):
    ""
    psr = create_parser( argvlist, vvtest_version )

    opts = psr.parse_args( argvlist )

    args = opts.directory

    check_deprecated_option_use( opts )
    check_for_command_line_usage_warnings( opts )
    check_print_version( opts, vvtest_version )
    derived_opts = adjust_options_and_create_derived_options( opts )

    return opts, derived_opts, args


##############################################################################

description = """\
The vvtest program generates and runs a set of scripts, called tests.
In normal operation, a list of tests to run is determined by recursively
scanning the directory arguments (or the current working directory if
none are given).  The tests are filtered using the command line options,
then run in a subdirectory prefixed with "TestResults".
"""

def create_parser( argvlist, vvtest_version ):
    ""
    argutil.set_num_columns_for_help_formatter()

    psr = argutil.ArgumentParser(
                        prog='vvtest',
                        description=description,
                        formatter_class=argutil.ParagraphHelpFormatter )

    psr.add_argument( '--version', action='store_true',
        help='Print the version of vvtest and exit.' )
    psr.add_argument( '-v', dest='dash_v', action='count',
        help='Add verbosity to console output.  Can be repeated, which gives '
             'even more verbosity.' )
    psr.add_argument( '-q', dest='dash_q', action='count',
        help='Quiet (reduce verbosity level by one). Using -q without -v '
             'will show a progress bar as tests are run' )

    grp = psr.add_argument_group( 'Test selection / filters' )

    # keyword filtering
    grp.add_argument( '-k', metavar='EXPR', dest='dash_k', action='append',
        help='Filter tests by including those with a keyword or keyword '
              'expression, such as "-k fast" or "-k fail/diff".' )
    grp.add_argument( '-K', metavar='EXPR', dest='dash_K', action='append',
        help='Filter tests by excluding those with a keyword or keyword '
             'expression, such as "-K long" or "-K fail/notdone".' )
    grp.add_argument( '-R', dest='dash_R', action='store_true',
        help='Rerun tests.  Normally tests are not run if they previously '
             'completed.' )

    # parameter filtering
    grp.add_argument( '-p', metavar='EXPR', dest='dash_p', action='append',
        help='Filter tests by parameter name and value, such as '
             '"-p np=8" or "-p np<8" or "-p np".' )
    grp.add_argument( '-P', metavar='EXPR', dest='dash_P', action='append',
        help='Filter the set of tests by excluding those with a parameter '
             'name and value, such as "-P np".' )
    grp.add_argument( '-S', metavar='KEYVAL', dest='dash_S', action='append',
        help='Using name=value will set the parameter name to that value in '
             'any test that defines the parameter, such as "-S np=16".' )

    # platform filtering
    grp.add_argument( '-x', metavar='EXPR', dest='dash_x', action='append',
        help='Include tests that would, by default, run for the given '
             'platform name, such as "-x Linux" or "-x TLCC2/CTS1".' )
    grp.add_argument( '-X', metavar='EXPR', dest='dash_X', action='append',
        help='Exclude tests that would, by default, run for the given '
             'platform name, such as "-X Linux" or "-X TLCC2/CTS1".' )
    grp.add_argument( '-A', dest='dash_A', action='store_true',
        help='Ignore platform exclusions specified in the tests.' )

    # runtime filtering
    grp.add_argument( '--tmin',
        help='Only include tests whose previous runtime is greater than '
             'the given number of seconds.' )
    grp.add_argument( '--tmax',
        help='Only include tests whose previous runtime is less than the '
             'given number of seconds.' )
    grp.add_argument( '--tsum',
        help='Include as many tests as possible such that the sum of their '
             'runtimes is less than the given number of seconds.' )

    # more filtering
    grp.add_argument( '--search', metavar='REGEX', dest='search', action='append',
        help='Include tests that have an input file containing the '
             'given regular expression.  Multiple are ORed together.' )
    grp.add_argument( '--include-tdd', action='store_true',
        help='Include tests that contain the keyword "TDD", which are '
             'normally not included.' )
    grp.add_argument( '--scan-type', metavar='TYPE', dest='scan_type', action='append',
        help='Value can be "vvt" or "xml" or "vvt,xml", and restricts test '
             'file scanning to certain type(s) of test specification (i.e., the '
             'test file extensions). Default is only *.vvt files.' )

    # behavior
    grp = psr.add_argument_group( 'Runtime behavior' )
    grp.add_argument( '-o', metavar='OPTS', dest='dash_o', action='append',
        help='Turn option(s) on, such as "-o dbg" or "-o intel17+dbg".' )
    grp.add_argument( '-O', metavar='OPTS', dest='dash_O', action='append',
        help='Turn option(s) off if they would be on by default.' )
    grp.add_argument( '-w', dest='dash_w', action='store_true',
        help='Wipe previous test results, if present.' )
    grp.add_argument( '-m', dest='dash_m', action='store_true',
        help='Do not clean out test result directories before running.' )
    grp.add_argument( '--perms', action='append',
        help='Apply permission settings and/or a group name to files and '
             'directories in the test execution area.' )
    grp.add_argument( '-C', '--postclean', dest='postclean', action='store_true',
        help='Clean the test execution directory after a "pass".' )
    grp.add_argument( '--force', action='store_true',
        help='Force vvtest to run even if a separate vvtest process appears to '
             'be running.' )
    grp.add_argument( '-M', metavar='PATH', dest='dash_M',
        help='Use this path to contain the test executions.' )
    grp.add_argument( '--run-dir',
        help='The name of the directory to contain the test execution results. '
             'Defaults to TestResults.*, where * is the platform name plus '
             '-o options.' )
    grp.add_argument( '-L', dest='dash_L', action='store_true',
        help='Do not redirect test output to log files.' )
    grp.add_argument( '-a', '--analyze', dest='analyze', action='store_true',
        help='Causes the option --execute-analysis-sections to be given to '
             'each test invocation.  Only makes sense in combination with -R.' )
    grp.add_argument( '--test-args', metavar='ARGS', action='append',
        help='Pass options and/or arguments to each test script.' )
    grp.add_argument( '--encode-exit-status', action='store_true',
        help='Exit nonzero if at least one test did not pass or did not run.' )
    grp.add_argument( '--short-xdirs', metavar='NUMCHARS',
        help='Shorten long execution directory names with more characters '
             'than the given value (default is 100).' )
    grp.add_argument( '--minimal-xdirs', action='store_true',
        help='Shorten execution directory names by excluding parameterize '
             'names with only one value.' )

    # resources
    grp = psr.add_argument_group( 'Resource controls' )
    grp.add_argument( '-n', metavar='NUM_CORES', dest='dash_n', type=int,
        help='The number of CPU cores to occupy at any one time. '
             'Tests taking more than this number are run last.  '
             'Defaults to MAX_CORES.' )
    grp.add_argument( '-N', metavar='MAX_CORES', dest='dash_N', type=int,
        help='The max number of CPU cores available for each test.  Tests '
             'taking more than this value are not run.  Defaults to platform '
             'plugin value if set, or a system probe if not.' )
    grp.add_argument( '--devices', metavar='NUM_DEVICES', type=int,
        help='The number of devices (e.g. GPUs) to occupy at any one time. '
             'Tests taking more than this number are run last.  '
             'Defaults to MAX_DEVICES.' )
    grp.add_argument( '--max-devices', metavar='MAX_DEVICES', type=int,
        help='The max number of devices available for each test (e.g. max '
             'GPUs). Tests taking more than this value are not run. '
             'Defaults to platform plugin value if set, or zero if not.' )
    grp.add_argument( '--plat',
        help='Use this platform name for defaults and plugins.' )
    grp.add_argument( '--platopt', action='append',
        help='Pass through name=value settings to the platform, such '
             'as "--platopt ppn=4".' )
    grp.add_argument( '-T', metavar='SECONDS', dest='dash_T',
        help='Apply a timeout to each test (number of seconds or 10m or '
             '2h or MM:SS or HH:MM:SS). A zero or negative value means '
             'do not apply a timeout.' )
    grp.add_argument( '--timeout-multiplier', metavar='NUMBER',
        help='Apply a multiplier to the timeout value for each test. '
             'Can be a positive integer or float.' )
    grp.add_argument( '--max-timeout', metavar='SECONDS',
        help='Maximum timeout value for each test and for batch jobs '
             '(number of seconds or 10m or 2h or HH:MM:SS). A zero '
             'or negative value means no maximum.' )
    grp.add_argument( '--total-timeout', metavar='SECONDS',
        help='Stop running tests but exit normally after this amount of time '
             '(number of seconds or 10m or 2h or HH:MM:SS). A zero '
             'or negative value means no timeout, which is the default.' )

    # config
    grp = psr.add_argument_group( 'Runtime configuration' )
    grp.add_argument( '-j', '--bin-dir', dest='bin_dir', metavar='BINDIR',
        help='Specify the directory containing the project executables.' )
    grp.add_argument( '--config', action='append',
        help='Directory containing testing plugins and helpers. '
             'Same as VVTEST_CONFIGDIR environment variable.' )
    grp.add_argument( '-e', action='store_true',
        help='Deprecated; will be removed next release.' )
    grp.add_argument( '--user-args', metavar='ARGS',
        help='Ignored by vvtest.  Use --user-args to pass arguments through '
             'sys.argv to user plugin functions.  User plugin functions are '
             'responsible for parsing sys.argv to find --user-args.' )

    # batch
    grp = psr.add_argument_group( 'Batching / queuing' )
    grp.add_argument( '--batch', action='store_true',
        help='Groups tests, submits to the batch queue manager, and '
             'monitors for completion.' )
    grp.add_argument( '--batch-limit', type=int,
        help='Limit the number of batch jobs in the queue at any one time. '
             'Default is 5.' )
    grp.add_argument( '--batch-length',
        help='Limit the number of tests in each job group such that the '
             'sum of their runtimes is less than the given value (number '
             'of seconds or 10m or 2h or HH:MM:SS). Default is 30 minutes.' )
    psr.add_argument( '--batch-id', type=int, help=argutil.SUPPRESS )

    # results
    grp = psr.add_argument_group( 'Results handling' )
    grp.add_argument( '-i', dest='dash_i', action='store_true',
        help='Read and display testing results. Can be run while another '
             'vvtest is running.' )
    grp.add_argument( '--sort', metavar='LETTERS', action='append',
        help='Sort test listings.  Letters include n=name, '
             'x=execution name, t=runtime, d=execution date, '
             's=status, r=reverse the order.' )
    helpstr = ( 'Optionally --save-results=<directory>.  Save test results '
                'to the TESTING_DIRECTORY or the given directory.' )
    if an_argument_startswith( '--save-results=', argvlist ):
        grp.add_argument( '--save-results', action='store',
                          metavar='DIRECTORY', help=helpstr )
    else:
        grp.add_argument( '--save-results', action='store_true', help=helpstr )
    grp.add_argument( '--results-tag',
        help='Add an arbitrary tag to the --save-results output file.' )
    grp.add_argument( '--results-date', metavar='DATE',
        help='Specify the testing date, used as a marker or file name in some '
             'output formats. Can be seconds since epoch or a date string.' )
    grp.add_argument( '--junit', metavar='FILENAME',
        help='Writes a test summary file in the JUnit XML format.' )
    grp.add_argument( '--json', metavar='FILENAME',
        help='Writes a test summary file in json format.' )
    grp.add_argument( '--html', metavar='FILENAME',
        help='Write a test summary file in HTML format.' )
    grp.add_argument( '--gitlab', metavar='LOCATION',
        help='Write test summary as a set of files in the GitLab '
             'Flavored Markdown format.  If LOCATION is a Git repository '
             'URL, then push results files to branches there.' )
    grp.add_argument( '--cdash', metavar='SPECS',
        help='Write test results for CDash, where SPECS is of the form '
             '"location, project=*, date=*, group=*, site=*, name=*" '
             'and location is either a file name or an http URL.' )
    grp.add_argument( '--cdash-project', metavar='NAME', action='store',
        help='Alternate way to specify the CDash project name.' )

    grp = psr.add_argument_group( 'Other operating modes' )
    grp.add_argument( '-b', dest='rebase', action='store_true',
        help='Rebaseline tests that have diffed.' )
    grp.add_argument( '-B', dest='rebase_all', action='store_true',
        help='Rebaseline all tests regardless of result status.' )

    grp.add_argument( '-g', dest='dash_g', action='store_true',
        help='Scan for tests and populate the test results tree, '
             'but do not run any tests.' )
    grp.add_argument( '--partition', metavar='NUMBATCHES', dest='partition',
        action='append', help='Used with -g, scan for tests, partition into '
             'batches, and write a test list file for each batch.' )

    grp.add_argument( '--extract', metavar='DESTDIR',
        help='Extract test files from their source to the DESTDIR '
             'directory.' )

    grp.add_argument( '--keys', action='store_true',
        help='Gather and print all the keywords in each test, after '
             'filtering.' )
    grp.add_argument( '--files', action='store_true',
        help='Gather and print the file names that would be run, after '
             'filtering.' )
    grp.add_argument( '-t', '--show-times', dest='show_times', action='store_true',
        help='Used with -i, this prints the timeouts for each test.' )

    psr.add_argument( 'directory', nargs='*' )

    return psr


def an_argument_startswith( prefix, argvlist ):
    ""
    for arg in argvlist:
        if arg.startswith( prefix ):
            return True

    return False


##############################################################################

def check_print_version( opts, vvtest_version ):
    ""
    if opts.version:
        print( str(vvtest_version) )
        sys.exit(0)


def check_deprecated_option_use( opts ):
    ""
    # keep this block as an example of a deprecated but functional option
    # if opts.qsub_limit:
    #     # --qsub-limit replaced with --batch-limit
    #     opts.batch_limit = opts.qsub_limit


def check_for_command_line_usage_warnings( opts ):
    ""
    if opts.dash_n is not None and opts.batch:
        print ( '*** Warning: the command line -n option has no effect '
                'when the --batch option is also given' )


def adjust_options_and_create_derived_options( opts ):
    ""
    derived_opts = {}

    try:

        errtype = 'keyword options'
        expr = create_keyword_expression( opts.dash_k, opts.dash_K )
        derived_opts['keyword_expr'] = expr

        errtype = 'parameter options'
        params = create_parameter_expression( opts.dash_p, opts.dash_P )
        derived_opts['param_list'] = params

        errtype = 'setting paramters'
        paramD = create_parameter_settings( opts.dash_S )
        derived_opts['param_dict'] = paramD

        errtype = 'search option'
        rxL = create_search_regex_list( opts.search )
        derived_opts['search_regexes'] = rxL

        errtype = 'platform options'
        expr = create_platform_expression( opts.dash_x, opts.dash_X )
        derived_opts['platform_expr'] = expr

        errtype = 'the sort option'
        letters = clean_sort_options( opts.sort )
        derived_opts['sort_letters'] = letters

        errtype = 'platopt'
        platD = create_platform_options( opts.platopt )
        derived_opts['platopt_dict'] = platD

        errtype = 'partition'
        partD = create_partition_options( opts.partition )
        derived_opts['partition_dict'] = partD

        errtype = 'batch-limit'
        if opts.batch_limit is not None and opts.batch_limit < 0:
            raise Exception( 'limit cannot be negative' )

        errtype = 'batch-length'
        if opts.batch_length is not None:
            nsecs,err = parse_time_span_value( opts.batch_length )
            if err:
                raise Exception( 'invalid specification: '+err )
            if nsecs < 0:
                raise Exception( 'cannot be negative: '+repr(opts.batch_length) )
            opts.batch_length = nsecs

        errtype = 'on/off options'
        onL,offL = clean_on_off_options( opts.dash_o, opts.dash_O )
        derived_opts['onopts'] = onL
        derived_opts['offopts'] = offL

        errtype = '--run-dir'
        if opts.run_dir is not None:
            if not opts.run_dir:
                raise Exception( 'cannot be an empty string' )

        errtype = 'num procs'
        if opts.dash_n is not None and opts.dash_n <= 0:
            raise Exception( 'must be positive' )

        errtype = 'max procs'
        if opts.dash_N is not None and float(opts.dash_N) <= 0:
            raise Exception( 'must be positive' )

        errtype = 'num devices'
        if opts.devices is not None and opts.devices <= 0:
            raise Exception( 'must be positive' )

        errtype = 'max devices'
        if opts.max_devices is not None and float(opts.max_devices) <= 0:
            raise Exception( 'must be positive' )

        errtype = 'tmin/tmax/tsum'
        mn,mx,sm = convert_test_time_options( opts.tmin, opts.tmax, opts.tsum )
        opts.tmin = mn
        opts.tmax = mx
        opts.tsum = sm

        errtype = '--results-date'
        if opts.results_date is not None:
            opts.results_date = check_convert_date_spec( opts.results_date )

        errtype = '--scan-type'
        if opts.scan_type is not None:
            opts.scan_type = check_adjust_scan_type( opts.scan_type )

    except Exception:
        sys.stderr.write( '*** error: command line problem with ' + \
            str(errtype)+': '+str(sys.exc_info()[1]) + '\n' )
        sys.stderr.flush()
        sys.exit(1)

    return derived_opts


def create_search_regex_list( pattern_list ):
    ""
    regexL = None

    if pattern_list is not None:

        regexL = []

        for pat in pattern_list:
            regexL.append( re.compile( pat, re.IGNORECASE | re.MULTILINE ) )

    return regexL


def create_parameter_settings( set_param ):
    """
    most common is
        -S name=value
    but also allowed is
        -S "name=value1 value2"
    which means the parameter will be forced to take on two values
    """
    pD = None

    if set_param:
        pD = {}
        for s in set_param:
            L = s.split( '=', 1 )
            if len(L) < 2 or not L[0].strip() or not L[1].strip():
                raise Exception( 'expected form "param=value"' )

            n,v = [ s.strip() for s in L ]

            if n in pD:
                pD[n].extend( v.split() )
            else:
                pD[n] = v.split()

    return pD


def clean_sort_options( sort ):
    ""
    letters = None

    if sort:

        letters = ''.join( [ s.strip() for s in sort ] )
        for c in letters:
            if c not in 'nxtdsr':
                raise Exception( 'invalid --sort character: ' + c )
    
    return letters


def create_platform_options( platopt ):
    ""
    pD = {}

    if platopt:
        for po in platopt:

            po = po.strip()
            if not po:
                raise Exception( 'value cannot be empty' )

            L = po.split( '=', 1 )
            if len(L) == 1:
                pD[ po ] = ''
            else:
                n = L[0].strip()
                if not n:
                    raise Exception( 'option name cannot be empty: '+po )

                pD[n] = L[1].strip()

    return pD


def create_partition_options( partition_list ):
    ""
    pD = {}

    if partition_list:
        for op in partition_list:
            if '=' not in op:
                pD['n'] = make_int_value( op )
            else:
                L = op.split('=',1)
                if len(L) != 2 or not L[0] or not L[1]:
                    raise Exception( "invalid specification: "+repr(op) )
                name,val = L
                name = name.lower()
                if name == 'n':
                    ival = make_int_value( val )
                    if ival < 1:
                        raise Exception( "num partitions must be positive, not "+repr(val) )
                    pD[name] = ival
                else:
                    raise Exception( "unknown partition option: "+repr(name) )

    return pD


def make_int_value( sval ):
    ""
    try:
        ival = int(sval)
    except Exception:
        raise Exception( "expected an integer, but got "+repr(sval) )

    return ival


def clean_on_off_options( on_options, off_options ):
    ""
    onL = []
    offL = []

    if on_options:
        onL = gather_on_off_values( on_options )
        wordcheck.check_words( onL )

    if off_options:
        offL = gather_on_off_values( off_options )
        wordcheck.check_words( offL )

    return onL, offL


def gather_on_off_values( onoff ):
    ""
    S = set()
    for o1 in onoff:
        for o2 in o1.split( '+' ):
            for o3 in o2.split():
                S.add( o3 )
    L = list( S )
    L.sort()

    return L


def convert_test_time_options( tmin, tmax, tsum ):
    ""
    if tmin is not None:
        tmin = float(tmin)

    if tmax is not None:
        tmax = float(tmax)
        if tmax < 0.0:
            raise Exception( 'tmax cannot be negative' )

    if tsum is not None:
        tsum = float(tsum)

    return tmin, tmax, tsum


def check_convert_date_spec( date_spec ):
    ""
    spec = date_spec.strip()

    if not spec:
        raise Exception( 'cannot be empty' )

    if '_' not in spec:
        try:
            secs = float( spec )
            if secs > 0:
                tup = time.localtime( secs )
                tmstr = time.strftime( "%a %b %d %H:%M:%S %Y", tup )
                spec = secs  # becomes a float right here
        except Exception:
            pass

    return spec


def check_adjust_scan_type( scan_type ):
    ""
    types = set()
    for val1 in scan_type:
        for val2 in val1.split(','):
            val2 = val2.strip()
            if val2:
                if val2 not in ['vvt','xml']:
                    raise Exception( 'unknown scan type: '+repr(val2) )
                types.add( val2 )

    if len(types) > 0:
        return list( types )
    else:
        return None


def parse_time_span_value( value ):
    """
    Parses a time value like "90" or "321.5" or "2h 30m" into seconds.
    Returns (num seconds, error string) where num seconds is a number if no
    error occurred.
    """
    err = ''
    nsecs = None

    try:
        nsecs = parse_num_seconds( value, negatives=True )
    except Exception as e:
        err = str(e)
    else:
        if nsecs is None:
            err = "could not parse time value: "+repr(value)

    return nsecs,err
