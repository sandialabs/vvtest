#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import basename


class MakeScriptCommand:
    """
    This class is a helper to create the command line for executing the test
    as well as command lines for rebaselining and running analyze tests.

    Back when a second test file format was supported, this class would also
    consider the format to form the command lines.
    """

    def __init__(self, loc, tspec, program=None,
                            shbang_supported=True):
        """
        The 'program' is a path to an executable to execute the test script.
        If None, then
            - if the test file is executable and shbang is supported, then
              the script is executed directly
            - otherwise, Python is used to run the script, sys.executable
        """
        self.loc = loc
        self.tspec = tspec
        self.prog = program
        self.shbang = shbang_supported

    def make_base_execute_command(self, baseline):
        ""
        if baseline:
            cmdL = self.check_make_script_baseline_command()

        elif self.tspec.isAnalyze():
            ascr = self.tspec.getAnalyzeScript()
            cmdL = self.command_from_filename_or_option( ascr )

        else:
            cmdL = self.make_test_script_command()

        return cmdL

    def make_test_script_command(self):
        ""
        srcdir = self.loc.path_to_source( self.tspec.getFilepath(),
                                          self.tspec.getRootpath() )
        fname = basename( self.tspec.getFilename() )
        cmdL = make_file_execute_command( srcdir, fname,
                                          self.prog, self.shbang )

        return cmdL

    def command_from_filename_or_option(self, spec):
        ""
        if spec.startswith('-'):
            cmdL = self.make_test_script_command()
            cmdL.append( spec )
        else:
            srcdir = self.tspec.getDirectory()
            cmdL = make_file_execute_command( srcdir, spec,
                                              self.prog, self.shbang )

        return cmdL

    def make_baseline_analyze_command(self):
        ""
        bscr = self.tspec.getBaselineScript()
        ascr = self.tspec.getAnalyzeScript()

        if bscr.startswith('-'):
            # add the baseline option to the analyze script command
            cmdL = self.command_from_filename_or_option( ascr )
            cmdL.append( bscr )

        else:
            # start with the baseline script command
            cmdL = self.command_from_filename_or_option( bscr )

            # if there is an analyze script AND a baseline script, just use the
            # baseline script; but if there is an analyze option then add it
            if ascr.startswith('-'):
                cmdL.append( ascr )

        return cmdL

    def make_script_baseline_command(self):
        ""
        if self.tspec.isAnalyze():
            cmdL = self.make_baseline_analyze_command()
        else:
            scr = self.tspec.getBaselineScript()
            cmdL = self.command_from_filename_or_option( scr )

        return cmdL

    def check_make_script_baseline_command(self):
        ""
        if self.tspec.getBaselineScript():
            cmdL = self.make_script_baseline_command()
        else:
            cmdL = None

        return cmdL


def make_file_execute_command( srcdir, path,
                               prog=None,
                               shbang=True ):
    ""
    if os.path.isabs( path ):
        if prog:
            return [ prog, path ]
        elif shbang and os.access( path, os.X_OK ):
            return [ path ]
        else:
            return [ sys.executable, path ]

    else:
        srcpath = os.path.join( srcdir, path )
        if prog:
            return [ prog, path ]
        elif shbang and os.access( srcpath, os.X_OK ):
            return [ './'+path ]
        else:
            return [ sys.executable, path ]
