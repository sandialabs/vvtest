#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import shutil
import glob
import fnmatch
from os.path import normpath, dirname
from os.path import join as pjoin

try:
    from shlex import quote
except Exception:
    from pipes import quote

from . import CommonSpec
from . import cshScriptWriter
from . import ScriptWriter
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

        self.commondb = None

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

        if tspec.getSpecificationForm() == 'xml':
            self.loadCommonXMLDB()

        texec.setTimeout( tstat.getAttr( 'timeout', 0 ) )

        xdir = tspec.getExecuteDirectory()
        wdir = pjoin( self.loc.getTestingDirectory(), xdir )
        texec.setRunDirectory( wdir )

    def loadCommonXMLDB(self):
        ""
        if self.commondb is None:
            cfgdirs = self.rtconfig.getAttr('configdir')
            self.commondb = CommonSpec.load_common_xmldb( cfgdirs )

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
        print3( "Cleaning execute directory for execution..." )
        specform = tcase.getSpec().getSpecificationForm()
        pre_clean_execute_directory( specform )

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
        print3( "Linking and copying working files..." )

        tspec = tcase.getSpec()

        sub = dirname( tspec.getFilepath() ) or '.'
        srcdir = self.loc.path_to_source( sub, tspec.getRootpath() )

        if self.symlinks:
            cpL = tspec.getCopyFiles()
            lnL = tspec.getLinkFiles()
        else:
            cpL = tspec.getLinkFiles() + tspec.getCopyFiles()
            lnL = []

        ok = link_and_copy_files( srcdir, lnL, cpL )

        return ok

    def apply_plugin_preload(self, tcase):
        ""
        pyexe = self.plugin.testPreload( tcase )
        if pyexe:
            return pyexe
        else:
            return sys.executable

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
        print3( "Cleaning execute directory after execution..." )

        specform = tcase.getSpec().getSpecificationForm()

        post_clean_execute_directory( rundir, specform )

    def copyBaselineFiles(self, tcase):
        ""
        tspec = tcase.getSpec()

        srcdir = self.loc.path_to_source( tspec.getDirectory(), tspec.getRootpath() )

        # TODO: add file globbing for baseline files
        for fromfile,tofile in tspec.getBaselineFiles():
            dst = pjoin( srcdir, tofile )
            print3( "baseline: cp -p "+fromfile+" "+dst )
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
            tstat.markDone( exit_status )
        else:
            tstat.markTimedOut()

        rundir = texec.getRunDirectory()
        self.perms.recurse( rundir )

        self.check_run_postclean( tcase, texec.getRunDirectory() )

        self.platform.returnResources( texec.getResourceObject() )

    def make_execute_command(self, texec, baseline, pyexe):
        ""
        tcase = texec.getTestCase()

        maker = MakeScriptCommand( tcase.getSpec(),
                                   pythonexe=pyexe,
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

        if tcase.getSpec().getSpecificationForm() == 'xml':
            self.write_xml_run_script( tcase, texec.getRunDirectory() )

        rundir = texec.getRunDirectory()
        resourceobj = texec.getResourceObject()
        self.write_script_utils( tcase, rundir, resourceobj )

        tm = texec.getTimeout()
        self.set_timeout_environ_variable( tm )

        self.check_run_preclean( tcase, baseline )
        self.check_write_mpi_machine_file( texec.getResourceObject() )
        self.check_set_working_files( tcase, baseline )

        set_PYTHONPATH( self.rtconfig.getAttr( 'configdir' ) )

        pyexe = self.apply_plugin_preload( tcase )

        cmd_list = self.make_execute_command( texec, baseline, pyexe )

        echo_test_execution_info( tcase.getSpec().getName(), cmd_list, tm )

        print3()

        if baseline:
            self.copyBaselineFiles( tcase )

        return cmd_list

    def write_xml_run_script(self, tcase, rundir):
        ""
        # no 'form' defaults to the XML test specification format

        tspec = tcase.getSpec()

        script_file = pjoin( rundir, 'runscript' )

        if self.rtconfig.getAttr('preclean') or \
           not os.path.exists( script_file ):

            troot = self.loc.makeAbsPath( tspec.getRootpath() )
            assert os.path.isabs( troot )
            tdir = os.path.dirname( tspec.getFilepath() )
            srcdir = normpath( pjoin( troot, tdir ) )

            # note that this writes a different sequence if the test is an
            # analyze test
            cshScriptWriter.writeScript( tcase,
                                         self.commondb,
                                         self.platform,
                                         self.rtconfig.getAttr('vvtestdir'),
                                         self.rtconfig.getAttr('exepath'),
                                         self.rtconfig.getAttr('configdir'),
                                         srcdir,
                                         self.rtconfig.getAttr('onopts'),
                                         self.rtconfig.getAttr('offopts'),
                                         script_file )

            self.perms.apply( os.path.abspath( script_file ) )

    def write_script_utils(self, tcase, rundir, resourceobj):
        ""
        for lang in ['py','sh']:

            script_file = pjoin( rundir, 'vvtest_util.'+lang )

            if self.rtconfig.getAttr('preclean') or \
               not os.path.exists( script_file ):

                ScriptWriter.writeScript( tcase, resourceobj,
                                          script_file,
                                          lang,
                                          self.rtconfig,
                                          self.platform,
                                          self.loc )

                self.perms.apply( os.path.abspath( script_file ) )


def set_PYTHONPATH( configdirs ):
    """
    When running Python in a test, the sys.path must include a few vvtest
    directories as well as the user's config dir.  This can be done with
    PYTHONPATH *unless* a directory contains a colon, which messes up
    Python's handling of the paths.

    To work in this case, sys.path is set in the vvtest_util.py file.
    The user's test just imports vvtest_util.py first thing.  However,
    importing vvtest_util.py assumes the execute directory is in sys.path
    on startup.  Normally it would be, but this can fail to be the case
    if the script is a soft link (which it is for the test script).

    The solution is to make sure PYTHONPATH contains an empty directory,
    which Python will expand to the current working directory. Note that
    versions of Python before 3.4 would allow the value of PYTHONPATH to
    be an empty string, but for 3.4 and later, it must at least be a single
    colon.

    [July 2019] To preserve backward compatibility for tests that do not
    import vvtest_util.py first thing, the directories are placed in
    PYTHONPATH here too (but only those that do not contain colons).
    """
    os.environ['PYTHONPATH'] = determine_PYTHONPATH( configdirs )


def determine_PYTHONPATH( configdirs ):
    """
    Note: Adding configdirs to PYTHONPATH has been marked deprecated, Dec 2021.
          Tests should instead import vvtest_util.py.  When removed, this
    function must still make sure an empty directory is added to PYTHONPATH in
    the case of the test execution directory containing colons in the path.
    This is so that the test can import the vvtest_util.py file from the test
    directory.
    """
    val = ''

    for cfgd in configdirs:
        if ':' not in cfgd:
            val += ':'+cfgd

    if 'PYTHONPATH' in os.environ:
        val += ':'+os.environ['PYTHONPATH']

    if not val:
        val = ':'

    return val


def echo_test_execution_info( testname, cmd_list, timeout ):
    ""
    print3( "Starting test: "+testname )
    print3( "Directory    : "+os.getcwd() )

    if cmd_list != None:
        cmd = ' '.join( [ quote(arg) for arg in cmd_list ] )
        print3( "Command      : "+cmd )

    print3( "Timeout      : "+str(timeout) )

    print3()


def pre_clean_execute_directory( specform ):
    ""
    excludes = [ 'execute.log',
                 'baseline.log',
                 'vvtest_util.py',
                 'vvtest_util.sh' ]

    if specform == 'xml':
        excludes.append( 'runscript' )

    for fn in os.listdir('.'):
        if fn not in excludes and \
           not fnmatch.fnmatch( fn, 'execute_*.log' ):
            remove_path( fn )


def post_clean_execute_directory( rundir, specform ):
    ""
    excludes = [ 'execute.log',
                 'baseline.log',
                 'vvtest_util.py',
                 'vvtest_util.sh',
                 'machinefile',
                 'testdata.repr' ]

    if specform == 'xml':
        excludes.append( 'runscript' )

    for fn in os.listdir( rundir ):
        if fn not in excludes and \
           not fnmatch.fnmatch( fn, 'execute_*.log' ):
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
        print3( "*** error: cannot", operation_type,
                "a non-existent file:", srcf )
        ok = False

    elif len( srcL ) > 1 and destname != None:
        print3( "*** error:", operation_type, "failed because the source",
                "expanded to more than one file but a destination path",
                "was given:", srcf, destname )
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
            print3( 'ln -s '+srcf+' '+tstf )
            os.symlink( srcf, tstf )
    else:
        remove_path( tstf )
        print3( 'ln -s '+srcf+' '+tstf )
        os.symlink( srcf, tstf )


def force_copy_path_to_current_directory( srcf, destname ):
    ""
    if destname == None:
        tstf = os.path.basename( srcf )
    else:
        tstf = destname

    remove_path( tstf )

    if os.path.isdir( srcf ):
        print3( 'cp -rp '+srcf+' '+tstf )
        shutil.copytree( srcf, tstf, symlinks=True )
    else:
        print3( 'cp -p '+srcf+' '+tstf )
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


def print3( *args ):
    ""
    sys.stdout.write( ' '.join( [ str(x) for x in args ] ) + '\n' )
    sys.stdout.flush()
