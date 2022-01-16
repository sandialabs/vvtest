#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import fnmatch
import glob
from platform import uname as uname_func

uname = uname_func()
osname,nodename,osrelease,machine = uname[0], uname[1], uname[2], uname[4]

def get_platform():
    ""
    if 'VVTEST_PLATFORM' in os.environ:
        return os.environ['VVTEST_PLATFORM']

    snlsystem  = os.environ.get( 'SNLSYSTEM', '' )
    snlcluster = os.environ.get( 'SNLCLUSTER', '' )

    pbshost = os.environ.get('PBS_O_HOST','')
    lsfhost = os.environ.get('LSB_SUB_HOST','')

    if base_match( [nodename,lsfhost], ['vortex','rzansel','sierra'] ):
        return 'ATS2'

    if shell_match( [nodename,pbshost],
                    ['excalibur[0-9]*','batch[0-9]*','clogin*','nid*'] ):
        # DoD Cray XC 40
        return 'Cray'

    if shell_match( [nodename,pbshost],
                    ['mutrino*','tr-login[0-9]*','mom[0-9]*'] ):
        # the login nodes start with 'tr-login' (or 'mom'?)
        # the front end nodes start with 'mutrino' at Sandia, or ?? on Trinity
        return 'CrayXC'

    if shell_match( [nodename,pbshost], ['hercules[0-9]*'] ):
        # DoD IBM DataPlex ?
        return 'IBMidp'

    if snlsystem == 'cts1':
        # Capacity Technology System, running TOSS
        return 'CTS1'

    if base_match( [nodename,pbshost,snlcluster], ['astra','stria'] ):
        # Vanguard System
        return 'ASTRA'

    if snlsystem in ['tlcc2','uno']:
        # Tri-Lab Computing Cluster, running TOSS
        return 'TLCC2'

    if base_match( [nodename,pbshost,snlcluster], ['godzilla'] ) or \
       shell_match( [nodename], ['gn[0-9]','gn[0-9][0-9]'] ):
        # see Kyle Cochrane; may be decommissioned
        return 'Godzilla'

    if base_match( [osname], ['CYGWIN'] ):
        return 'CYGWIN'

    if osname == "Darwin" and machine in ["i386","i686","x86_64"]:
        return "iDarwin"

    if osname == 'Linux' and machine == 'ia64':
        return 'Altix'

    if osname == 'Linux' and snlsystem == 'cee':
        # Sandia CEE LAN
        return 'ceelan'


#######################################################################

def base_match( namelist, matchlist ):
    """
    Looks for a name in 'namelist' whose first part matches a word in
    'matchlist'.
    """
    for n in namelist:
        for m in matchlist:
            tn = n[:len(m)]  # truncate the actual name to the match name length
            if tn == m:
                return 1
    return 0


def shell_match( namelist, matchlist ):
    """
    Looks for a name in 'namelist' that matches a word in 'matchlist' which
    can contain shell wildcard characters.
    """
    for n in namelist:
        for m in matchlist:
            if fnmatch.fnmatch( n, m ):
                return 1
    return 0


#######################################################################

if __name__ == "__main__":
    """
    Can execute this script as a quick check of the logic and results.
    """
    import getopt
    optL,argL = getopt.getopt( sys.argv[1:], 'o:', [] )
    optD = {}
    for n,v in optL:
        optD[n] = v
    p = platform( optD )
    print ( p )
