#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import shlex
import subprocess


def get_node_size( attrs ):
    ""
    ppn = max( 1, attrs.get( 'ppn', 0 ) )

    dpn = attrs.get( attrs.get( 'dpn', 0 ) )
    if dpn:
        dpn = max( 0, dpn )
    else:
        dpn = 0

    return ppn,dpn


def runcmd( cmdL, chdir=None, echo=False ):
    ""
    cmdstr = ' '.join( cmdL )

    if chdir:
        cmdstr = 'cd "'+chdir+'" && '+cmdstr
        cwd = os.getcwd()
        os.chdir( chdir )

    try:
        if echo:
            print ( cmdstr )
            sys.stdout.flush()
            sys.stderr.flush()
        try:
            sp = subprocess.Popen( cmdL, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT )
        except Exception as e:
            return 1,cmdstr,'subprocess failed: '+str(e)

        out,err = sp.communicate()

    finally:
        if chdir:
            os.chdir( cwd )

    if sys.version_info[0] < 3:
        out = out if out else ''
    else:
        out = out.decode() if out else ''

    return sp.returncode, cmdstr, out


def format_shell_flags( flags ):
    ""
    flaglist = []

    if flags:
        if type(flags) == type(''):
            flaglist = shlex.split(flags)

        elif type(flags) not in [type(()),type([])]:
            extra_flags_type = type(flags).__name__
            errmsg = "Expected extra_flags to be str or list, not {0}"
            raise ValueError(errmsg.format(extra_flags_type))

        else:
            flaglist = list( flags )

    return flaglist
