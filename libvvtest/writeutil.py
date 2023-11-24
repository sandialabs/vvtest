#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import join as pjoin

try:
    from shlex import quote
except Exception:
    from pipes import quote

from .teststatus import DIFF_EXIT_STATUS, SKIP_EXIT_STATUS


def write_util_scripts( testcase, filename, lang, rtconfig, plat, loc ):
    """
    Writes a helper script for the test.  The script language is based on
    the 'lang' argument.
    """
    tspec = testcase.getSpec()
    tstat = testcase.getStat()
    tname = tspec.getName()

    troot = tspec.getRootpath()
    srcdir = loc.path_to_source( tspec.getFilepath(), tspec.getRootpath() )

    test_dir = loc.getTestingDirectory()

    configdirs = rtconfig.getAttr('configdir')

    tdir = rtconfig.getAttr('vvtestdir')
    assert tdir

    projdir = rtconfig.getAttr('exepath')
    if projdir is None:
        projdir = ''
    else:
        projdir = loc.path_to_file( tspec.getFilepath(), projdir )

    onopts = rtconfig.getAttr('onopts')
    offopts = rtconfig.getAttr('offopts')

    platname = plat.getName()
    cplrname = plat.getCompiler() or ''

    timeout = testcase.getStat().getAttr( 'timeout', -1 )

    dep_list = testcase.getDepDirectories()

    w = LineWriter()

    if lang == 'py':

        w.add( 'import os, sys',
               '',
               'NAME = '+repr(tname),
               'TESTID = '+repr( tspec.getTestID().computeMatchString() ),
               'PLATFORM = '+repr(platname),
               'COMPILER = '+repr(cplrname),
               'VVTESTSRC = '+repr(tdir),
               'TESTROOT = '+repr(test_dir),
               'PROJECT = '+repr(projdir),
               'OPTIONS = '+repr( onopts ),
               'OPTIONS_OFF = '+repr( offopts ),
               'SRCDIR = '+repr(srcdir),
               'TIMEOUT = '+repr(timeout),
               'KEYWORDS = '+repr(tspec.getKeywords(include_implicit=False)) )

        w.add( 'CONFIGDIR = '+repr(configdirs) )

        w.add( '',
               'diff_exit_status = '+str(DIFF_EXIT_STATUS),
               'skip_exit_status = '+str(SKIP_EXIT_STATUS),
               'opt_analyze = "--execute-analysis-sections" in sys.argv[1:]' )

        w.add( '', '# parameters defined by the test' )
        paramD = tspec.getParameters( typed=True )
        w.add( 'PARAM_DICT = '+repr( paramD ) )
        for k,v in paramD.items():
            w.add( k+' = '+repr(v) )

        if tspec.isAnalyze():
            # the parameter names and values of the children tests
            w.add( '', '# parameters comprising the children' )
            psetD = tspec.getParameterSet().getParameters( typed=True )
            for n,L in psetD.items():
                if len(n) == 1:
                    L2 = [ T[0] for T in L ]
                    w.add( 'PARAM_'+n[0]+' = ' + repr(L2) )
                else:
                    n2 = '_'.join( n )
                    w.add( 'PARAM_'+n2+' = ' + repr(L) )

        L = generate_dependency_list( dep_list, test_dir )
        w.add( '', 'DEPDIRS = '+repr(L) )

        D = generate_dependency_map( dep_list, test_dir )
        w.add( '', 'DEPDIRMAP = '+repr(D) )

        w.add( '',
               'RESOURCE_np = '+repr( len(tstat.getAttr('processor ids')) ),
               'RESOURCE_IDS_np = '+repr(tstat.getAttr('processor ids')),
               'RESOURCE_TOTAL_np = '+repr(tstat.getAttr('total processors')) )

        if tstat.getAttr('device ids',None):
            w.add( '',
               'RESOURCE_ndevice = '+repr( len(tstat.getAttr('device ids')) ),
               'RESOURCE_IDS_ndevice = '+repr(tstat.getAttr('device ids')),
               'RESOURCE_TOTAL_ndevice = '+repr(tstat.getAttr('total devices')) )
        else:
            w.add( '',
               'RESOURCE_ndevice = 0',
               'RESOURCE_IDS_ndevice = []',
               'RESOURCE_TOTAL_ndevice = 0' )

        ###################################################################
    
    elif lang in ['sh','bash']:

        w.add( """
            # save the command line arguments into variables
            NUMCMDLINE=0
            CMDLINE_VARS=
            for arg in "$@" ; do
                NUMCMDLINE=$((NUMCMDLINE+1))
                eval CMDLINE_${NUMCMDLINE}='$arg'
                CMDLINE_VARS="$CMDLINE_VARS CMDLINE_${NUMCMDLINE}"
            done

            # this function returns true if the given string was an
            # argument on the command line
            cmdline_option() {
                optname=$1
                for var in $CMDLINE_VARS ; do
                    eval val="\$$var"
                    [ "X$val" = "X$optname" ] && return 0
                done
                return 1
            }

            opt_analyze=0
            cmdline_option --execute-analysis-sections && opt_analyze=1
            """ )

        w.add( '',
               'NAME="'+tname+'"',
               'TESTID="'+tspec.getTestID().computeMatchString()+'"',
               'PLATFORM="'+platname+'"',
               'COMPILER="'+cplrname+'"',
               'VVTESTSRC="'+tdir+'"',
               'TESTROOT="'+test_dir+'"',
               'PROJECT="'+projdir+'"',
               'OPTIONS="'+' '.join( onopts )+'"',
               'OPTIONS_OFF="'+' '.join( offopts )+'"',
               'SRCDIR="'+srcdir+'"',
               'TIMEOUT="'+str(timeout)+'"',
               'PYTHONEXE="'+sys.executable+'"' )

        kwds = ' '.join( tspec.getKeywords(include_implicit=False) )
        w.add( 'KEYWORDS="'+kwds+'"' )

        w.add( 'CONFIGDIR="'+':'.join( configdirs )+'"' )

        w.add( '',
               'diff_exit_status='+str(DIFF_EXIT_STATUS),
               'skip_exit_status='+str(SKIP_EXIT_STATUS) )

        w.add( '', '# parameters defined by the test' )
        paramD = tspec.getParameters()
        s = ' '.join( [ n+'/'+v for n,v in paramD.items() ] )
        w.add( 'PARAM_DICT="'+s+'"' )
        for k,v in paramD.items():
            w.add( k+'="'+v+'"' )

        if tspec.isAnalyze():
            w.add( '', '# parameters comprising the children' )
            psetD = tspec.getParameterSet().getParameters()
            if len(psetD) > 0:
                # the parameter names and values of the children tests
                for n,L in psetD.items():
                    n2 = '_'.join( n )
                    L2 = [ '/'.join( v ) for v in L ]
                    w.add( 'PARAM_'+n2+'="' + ' '.join(L2) + '"' )

        L = generate_dependency_list( dep_list, test_dir )
        w.add( '', 'DEPDIRS="'+' '.join(L)+'"' )

        sprocs = [ str(procid) for procid in tstat.getAttr('processor ids') ]
        w.add( '',
               'RESOURCE_np="'+str( len(sprocs) )+'"',
               'RESOURCE_IDS_np="'+' '.join(sprocs)+'"',
               'RESOURCE_TOTAL_np="'+str(tstat.getAttr('total processors'))+'"' )

        if tstat.getAttr('device ids',None):
            sdevs = [ str(devid) for devid in tstat.getAttr('device ids') ]
            w.add( '',
               'RESOURCE_ndevice="'+str( len(sdevs) )+'"',
               'RESOURCE_IDS_ndevice="'+' '.join(sdevs)+'"',
               'RESOURCE_TOTAL_ndevice="'+str(tstat.getAttr('total devices'))+'"' )
        else:
            w.add( '',
               'RESOURCE_ndevice="0"',
               'RESOURCE_IDS_ndevice=""',
               'RESOURCE_TOTAL_ndevice="0"' )

        for d in configdirs[::-1]:
            for fn in ['script_util.sh']:
                pn = pjoin( d, fn )
                if os.path.isfile(pn):
                    w.add( 'source '+quote(pn) )
    
    w.write( filename )


#########################################################################

class LineWriter:

    def __init__(self):
        self.lineL = []

    def add(self, *args):
        ""
        if len(args) > 0:
            indent = ''
            if type(args[0]) == type(2):
                n = args.pop(0)
                indent = '  '*n
            for line in args:
                if line.startswith('\n'):
                    for line in self._split( line ):
                        self.lineL.append( indent+line )
                else:
                    self.lineL.append( indent+line )

    def _split(self, s):
        ""
        off = None
        lineL = []
        for line in s.split( '\n' ):
            line = line.strip( '\r' )
            lineL.append( line )
            if off == None and line.strip():
                i = 0
                for c in line:
                    if c != ' ':
                        off = i
                        break
                    i += 1
        if off == None:
            return lineL
        return [ line[off:] for line in lineL ]

    def write(self, filename):
        ""
        fp = open( filename, 'w' )
        fp.write( '\n'.join( self.lineL ) + '\n' )
        fp.close()


def generate_dependency_list( dep_list, test_dir ):
    ""
    L = [ pjoin( test_dir, T[1] ) for T in dep_list ]
    L.sort()
    return L


def generate_dependency_map( dep_list, test_dir ):
    ""
    D = {}

    for pat,depdir in dep_list:
        if pat:
            S = D.get( pat, None )
            if S == None:
                S = set()
                D[ pat ] = S
            S.add( pjoin( test_dir, depdir ) )

    for k,S in D.items():
        D[ k ] = list( S )
        D[ k ].sort()

    return D
