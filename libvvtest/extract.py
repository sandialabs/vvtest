#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import shutil
import glob

from .pathutil import change_directory


def copy_out_test_files( target_dir, testcase_list ):
    ""
    if not os.path.isabs(target_dir):
        target_dir = os.path.abspath(target_dir)
    if not os.path.exists(target_dir):
        os.makedirs( target_dir )
    
    uniqD = {}
    
    def wvisit( arg, dname, dirs, files ):
        """
        copy a directory tree, but leave out version control files
        """
        for n in ['CVS','.cvsignore','.svn','.git','.gitignore']:
            while (n in dirs): dirs.remove(n)
            while (n in files): files.remove(n)
        fd = os.path.normpath( os.path.join( arg[0], dname ) )
        td = os.path.normpath( os.path.join( arg[1], dname ) )
        if not os.path.exists(td):
            os.makedirs(td)
        for f1 in files:
            f2 = os.path.join(fd,f1)
            tf = os.path.join(td,f1)
            shutil.copy2( f2, tf )
    
    for tcase in testcase_list:

        tspec = tcase.getSpec()

        tname = tspec.getName()
        T = (tname, tspec.getFilename())

        from_dir = os.path.dirname( tspec.getFilename() )
        p = os.path.dirname( tspec.getFilepath() )
        if p: to_dir = os.path.normpath( os.path.join( target_dir, p ) )
        else: to_dir = target_dir

        if not os.path.exists( to_dir ):
            os.makedirs( to_dir )
        tof = os.path.join( target_dir, tspec.getFilepath() )

        if tof not in uniqD:
            uniqD[tof] = None
            try: shutil.copy2( tspec.getFilename(), tof )
            except IOError: pass

        for srcf in tspec.getSourceFiles():

            if os.path.exists( os.path.join( from_dir, srcf ) ):
                fL = [ srcf ]
            else:
                with change_directory( from_dir ):
                    fL = glob.glob( srcf )

            for f in fL:
                fromf = os.path.join( from_dir, f )
                tof = os.path.join( to_dir, f )
                tod = os.path.dirname(tof)
                if tof not in uniqD:
                    uniqD[tof] = None
                    if not os.path.exists(tod):
                        os.makedirs(tod)
                    
                    if os.path.isdir(fromf):
                        with change_directory( fromf ):
                            for root,dirs,files in os.walk( '.' ):
                                wvisit( (fromf, tof), root, dirs, files )
                    else:
                        try: shutil.copy2( fromf, tof )
                        except IOError: pass
