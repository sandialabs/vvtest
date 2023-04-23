#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
import os
import platform
import time


def RuntimeInfo( **kwargs ):
    ""
    D = {}

    D['hostname']      = platform.uname()[1]
    D['curdir']        = os.getcwd()
    D['python']        = sys.executable
    D['PYTHONPATH']    = os.environ.get( 'PYTHONPATH', '' )
    D['PATH']          = os.environ.get( 'PATH', '' )
    D['LOADEDMODULES'] = os.environ.get( 'LOADEDMODULES', '' )

    D.update( kwargs )

    return D
