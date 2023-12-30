#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time
import shutil
import glob
import fnmatch
from os.path import normpath, dirname
from os.path import join as pjoin

try:
    from shlex import quote
except Exception:
    from pipes import quote

from . import logger
from . import writeutil
from .makecmd import MakeScriptCommand


class ExecutionHandler:

    def __init__(self, perms, rtconfig, platform, usrplugin, loc,
                       symlinks_supported=True,
                       fork_supported=True,
                       shbang_supported=True):
        """
        The 'platform' is a Platform object.  The 'loc' is a Locator object.
        """
        self.perms = perms
        self.rtconfig = rtconfig
        self.platform = platform
        self.plugin = usrplugin
        self.loc = loc

        self.symlinks = symlinks_supported
        self.forkok = fork_supported
        self.shbang = shbang_supported

    def create_execution_directory(self, tcase):
        ""
        tspec = tcase.getSpec()

        xdir = tspec.getExecuteDirectory()
        wdir = pjoin( self.loc.getTestingDirectory(), xdir )

        if not os.path.exists( wdir ):
            os.makedirs( wdir )
            self.perms.apply( xdir )  # magic: examine (it looks wrong)

    def initialize_for_execution(self, texec):
        ""
        tcase = texec.getTestCase()
        tspec = tcase.getSpec()
        tstat = tcase.getStat()

        texec.setExecTimeout( tstat.getAttr( 'timeout', 0 ) )

        xdir = tspec.getExecuteDirectory()
        wdir = pjoin( self.loc.getTestingDirectory(), xdir )
        texec.setRunDirectory( wdir )

    def check_run_preclean(self, tcase, baseline):
        ""
        if self.rtconfig.getAttr('preclean') and \
           not self.rtconfig.getAttr('analyze') and \
           not baseline and \
           tcase.getSpec().isFirstStage():
            self.preclean( tcase )

    def preclean(self, tcase):
        """
        Should only be run just prior to launching the test script.  It
        removes all files in the execute directory except for a few vvtest
        files.
        """
        print( "Cleaning execute directory for execution..." )
        pre_clean_execute_directory()

    def check_set_working_files(self, tcase, baseline):
        """
        establish soft links and make copies of working files
        """
        if not baseline:
            if not self.setWorkingFiles( tcase ):
                sys.stdout.flush()
                sys.stderr.flush()
                raise Exception( 'failed to setup working files' )

    def setWorkingFiles(self, tcase):
        """
        Called before the test script is executed, this sets the link and
        copy files in the test execution directory.  Returns False if certain
        errors are encountered and written to stderr, otherwise True.
        """
        print( "Linking and copying working files..." )

        tspec = tcase.getSpec()

        srcdir = self.loc.path_to_source( tspec.getFilepath(), tspec.getRootpath() )

        if self.symlinks:
            cpL = tspec.getCopyFiles()
            lnL = tspec.getLinkFiles()
        else:
            cpL = tspec.getLinkFiles() + tspec.getCopyFiles()
            lnL = []

        ok = link_and_copy_files( srcdir, lnL, cpL )

        return ok

    def set_timeout_environ_variable(self, timeout):
        """
        add a timeout environ variable so the test can take steps to
        shutdown a running application that is taking too long; the app
        should not die before the timeout, because otherwise vvtest will
        not recognize it as a timeout
        """
        if timeout > 0:
            os.environ['VVTEST_TIMEOUT'] = str( timeout )

    def check_run_postclean(self, tcase, rundir):
        ""
        if self.rtconfig.getAttr('postclean') and \
           tcase.getStat().passed() and \
           not tcase.hasDependent() and \
           tcase.getSpec().isLastStage():
            self.postclean( tcase, rundir )

    def postclean(self, tcase, rundir):
        """
        Should only be run right after the test script finishes.  It removes
        all files in the execute directory except for a few vvtest files.
        """
        post_clean_execute_directory( rundir )

    def copyBaselineFiles(self, tcase):
        ""
        tspec = tcase.getSpec()

        srcdir = self.loc.path_to_source( tspec.getFilepath(), tspec.getRootpath() )

        # TODO: add file globbing for baseline files
        for fromfile,tofile in tspec.getBaselineFiles():
            dst = pjoin( srcdir, tofile )
            logger.info( "baseline: cp -p {0} {1}".format(fromfile, dst) )
            shutil.copy2( fromfile, dst )

    def check_write_mpi_machine_file(self, resourceobj):
        ""
        if hasattr( resourceobj, 'machinefile' ):

            fp = open( "machinefile", "w" )
            try:
                fp.write( resourceobj.machinefile )
            finally:
                fp.close()

            self.perms.apply( os.path.abspath( "machinefile" ) )

    def finishExecution(self, texec):
        ""
        tcase = texec.getTestCase()
        tspec = tcase.getSpec()
        tstat = tcase.getStat()

        exit_status, timedout = texec.getExitInfo()

        if timedout is None:
            tstat.markDone( exit_status, time.time() )
        else:
            tstat.markTimedOut( time.time() )

        rundir = texec.getRunDirectory()
        self.perms.recurse( rundir )

        self.check_run_postclean( tcase, texec.getRunDirectory() )

        self.platform.returnResources( texec.getResourceObject() )

    def make_execute_command(self, texec, baseline, prog):
        ""
        tcase = texec.getTestCase()

        maker = MakeScriptCommand( self.loc, tcase.getSpec(),
                                   program=prog,
                                   shbang_supported=self.shbang )
        cmdL = maker.make_base_execute_command( baseline )

        if cmdL is not None:

            obj = texec.getResourceObject()
            if hasattr( obj, "mpi_opts") and obj.mpi_opts:
                cmdL.extend( ['--mpirun_opts', obj.mpi_opts] )

            if self.rtconfig.getAttr('analyze'):
                cmdL.append('--execute-analysis-sections')

            cmdL.extend( self.rtconfig.getAttr( 'testargs' ) )

        return cmdL

    def prepare_for_launch(self, texec, baseline):
        ""
        tcase = texec.getTestCase()

        rundir = texec.getRunDirectory()
        self.write_script_utils( tcase, rundir, baseline )

        tm = texec.getExecTimeout()
        self.set_timeout_environ_variable( tm )

        self.check_run_preclean( tcase, baseline )
        self.check_write_mpi_machine_file( texec.getResourceObject() )
        self.check_set_working_files( tcase, baseline )

        set_PATH_and_PYTHONPATH( rundir, self.rtconfig )

        prog = self.plugin.testPreload( tcase )

        cmd_list = self.make_execute_command( texec, baseline, prog )

        echo_test_execution_info( tcase.getSpec().getName(), cmd_list, tm )

        print('')

        if baseline:
            self.copyBaselineFiles( tcase )

        return cmd_list

    def write_script_utils(self, tcase, rundir, baseline):
        ""
        for lang in ['py','sh']:

            script_file = pjoin( rundir, 'vvtest_util.'+lang )

            if self.rtconfig.getAttr('preclean') or \
               not os.path.exists( script_file ):

                writeutil.write_util_scripts( tcase,
                                              script_file,
                                              lang,
                                              baseline,
                                              self.rtconfig,
                                              self.platform,
                                              self.loc )

                self.perms.apply( os.path.abspath( script_file ) )


def set_PATH_and_PYTHONPATH( rundir, rtconfig ):
    """
    When running Python in a test, the sys.path must include a few vvtest
    directories as well as the user's config dir.  These paths are passed
    into the test execution using PYTHONPATH.

    This all works fine unless a directory contains a colon, which messes
    up Python's handling of the paths.  To work in this case (an unlikely
    event), an empty path is added to the PYTHONPATH so the test will be
    able to import the vvtest_util.py from the current working directory.
    After that, the test must manage sys.path manually to work in this case.
    """
    configdirs = rtconfig.getAttr( 'configdir' )
    vdir = rtconfig.getAttr( 'vvtestdir' )
    os.environ['PYTHONPATH'] = determine_PYTHONPATH( rundir, configdirs, vdir )
    os.environ['PATH'] = determine_PATH( rundir, configdirs )


def determine_PYTHONPATH( rundir, configdirs, vdir ):
    """
    Add an empty directory, the test execute directory, and the config
    directories to PYTHONPATH.
    """
    val = ':'+rundir

    for cfgd in configdirs:
        if ':' not in cfgd:
            val += ':'+cfgd

    if ':' not in vdir:
        val += ':'+vdir

    if 'PYTHONPATH' in os.environ:
        val += ':'+os.environ['PYTHONPATH']

    return val


def determine_PATH( rundir, configdirs ):
    """
    Add the test execute directory, and the config directories to the PATH.
    """
    val = rundir

    for cfgd in configdirs:
        if ':' not in cfgd:
            val += ':'+cfgd

    if 'PATH' in os.environ:
        val += ':'+os.environ['PATH']

    return val


def echo_test_execution_info( testname, cmd_list, timeout ):
    ""
    print( "Starting test: {0}".format(testname) )
    print( "Directory    : {0}".format(os.getcwd()) )

    if cmd_list != None:
        cmd = ' '.join( [ quote(arg) for arg in cmd_list ] )
        print( "Command      : {0}".format(cmd) )

    print( "Timeout      : {0}".format(timeout) )

    print('')


def pre_clean_execute_directory():
    ""
    excludes = [ 'execute.log',
                 'baseline.log',
                 'vvtest_util.py',
                 'vvtest_util.sh' ]

    for fn in os.listdir('.'):
        if fn not in excludes and not fnmatch.fnmatch( fn, 'execute_*.log' ):
            remove_path( fn )


def post_clean_execute_directory( rundir ):
    ""
    excludes = [ 'execute.log',
                 'baseline.log',
                 'vvtest_util.py',
                 'vvtest_util.sh',
                 'machinefile',
                 'testdata.repr' ]

    for fn in os.listdir( rundir ):
        if fn not in excludes and not fnmatch.fnmatch( fn, 'execute_*.log' ):
            fullpath = pjoin( rundir, fn )
            if not os.path.islink( fullpath ):
                remove_path( fullpath )


def link_and_copy_files( srcdir, linkfiles, copyfiles ):
    ""
    ok = True

    for srcname,destname in linkfiles:

        if os.path.isabs( srcname ):
            srcf = normpath( srcname )
        else:
            srcf = normpath( pjoin( srcdir, srcname ) )

        srcL = get_source_file_names( srcf )

        if check_source_file_list( 'soft link', srcf, srcL, destname ):
            for srcf in srcL:
                force_link_path_to_current_directory( srcf, destname )
        else:
            ok = False

    for srcname,destname in copyfiles:

        if os.path.isabs( srcname ):
            srcf = normpath( srcname )
        else:
            srcf = normpath( pjoin( srcdir, srcname ) )

        srcL = get_source_file_names( srcf )

        if check_source_file_list( 'copy', srcf, srcL, destname ):
            for srcf in srcL:
                force_copy_path_to_current_directory( srcf, destname )
        else:
            ok = False

    return ok


def check_source_file_list( operation_type, srcf, srcL, destname ):
    ""
    ok = True

    if len( srcL ) == 0:
        print( "Error: cannot {0} a non-existent file: {1}".format(operation_type, srcf) )
        ok = False

    elif len( srcL ) > 1 and destname != None:
        print(
            "Error: {0} failed because the source expanded to more than one file but a "
            "destination path was given: {1} {2}".format(operation_type, srcf, destname)
        )
        ok = False

    return ok


def get_source_file_names( srcname ):
    ""
    files = []

    if os.path.exists( srcname ):
        files.append( srcname )
    else:
        files.extend( glob.glob( srcname ) )

    return files


def force_link_path_to_current_directory( srcf, destname ):
    ""
    if destname == None:
        tstf = os.path.basename( srcf )
    else:
        tstf = destname

    if os.path.islink( tstf ):
        lf = os.readlink( tstf )
        if lf != srcf:
            os.remove( tstf )
            print( 'ln -s {0} {1}'.format(srcf, tstf) )
            os.symlink( srcf, tstf )
    else:
        remove_path( tstf )
        print( 'ln -s {0} {1}'.format(srcf, tstf) )
        os.symlink( srcf, tstf )


def force_copy_path_to_current_directory( srcf, destname ):
    ""
    if destname == None:
        tstf = os.path.basename( srcf )
    else:
        tstf = destname

    remove_path( tstf )

    if os.path.isdir( srcf ):
        print( 'cp -rp {0} {1}'.format(srcf, tstf) )
        shutil.copytree( srcf, tstf, symlinks=True )
    else:
        print( 'cp -rp {0} {1}'.format(srcf, tstf) )
        shutil.copy2( srcf, tstf )


def remove_path( path ):
    ""
    if os.path.islink( path ):
        os.remove( path )

    elif os.path.exists( path ):
        if os.path.isdir( path ):
            shutil.rmtree( path )
        else:
            os.remove( path )
