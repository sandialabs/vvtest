
# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
import os
from os.path import join as pjoin, normpath, abspath, basename


module_uniq_id = 0

def create_module_from_filename( fname ):
    """
    Import a filename as a module. Returns the module object.

    The name of the module is not just the basename of the file without the
    extension, rather it is that plus a unique integer. This allows multiple
    imports of files with the same basename.
    """
    global module_uniq_id

    fname = normpath( abspath( fname ) )

    modname = os.path.splitext( basename(fname) )[0]+'_'+str(module_uniq_id)
    module_uniq_id += 1

    if sys.version_info[0] < 3 or sys.version_info[1] < 5:
        import imp
        fp = open( fname, 'r' )
        try:
            spec = ('.py','r',imp.PY_SOURCE)
            mod = imp.load_module( modname, fp, fname, spec )
        finally:
            fp.close()
    else:
        import importlib
        import importlib.machinery as impmach
        import importlib.util as imputil
        loader = impmach.SourceFileLoader( modname, fname )
        spec = imputil.spec_from_file_location( modname, fname, loader=loader )
        mod = imputil.module_from_spec(spec)
        spec.loader.exec_module(mod)

    return mod


def import_file_from_sys_path( filename ):
    """
    look for the plugin file name in sys.path
    """
    mod = None

    pn = find_module_file( filename )
    if pn:
        try:
            mod = create_module_from_filename( pn )
        except ImportError:
            mod = None

    return mod


def find_module_file( filename ):
    ""
    for dn in sys.path:
        pn = pjoin( dn, filename )
        if os.path.exists(pn) and os.access( pn, os.R_OK ):
            return pn

    return None


def gather_modules_from_filename( filename ):
    ""
    modlist = []

    for dn in sys.path:
        pn = pjoin( dn, filename )
        if os.path.exists(pn) and os.access( pn, os.R_OK ):
            try:
                mod = create_module_from_filename( pn )
                modlist.append( mod )
            except ImportError:
                pass

    return modlist
