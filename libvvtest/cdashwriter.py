#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time
from os.path import join as pjoin
from os.path import basename
import stat
import platform

from . import logger
from . import outpututils


class CDashWriter:

    def __init__(self, permsetter, formatter, submitter):
        ""
        self.permsetter = permsetter
        self.fmtr = formatter
        self.subm = submitter

    def initialize(self, rtinfo,
                         destination,
                         project=None,
                         datestamp=None,
                         options=[],
                         tag=None ):
        ""
        self.rtinfo = rtinfo

        self.dspecs,err = construct_destination_specs( destination,
                                                       project=project,
                                                       datestamp=datestamp,
                                                       options=options,
                                                       tag=tag )

        if not err and self.dspecs.url and not self.dspecs.project:
            err = 'The project must be specified when the CDash ' + \
                  'destination is an http URL'

        return err

    def postrun(self, atestlist):
        ""
        self._create_and_fill_formatter( atestlist )
        self._write_data( self.fmtr )

    def info(self, atestlist):
        ""
        self._create_and_fill_formatter( atestlist )
        self._write_data( self.fmtr )

    def _create_and_fill_formatter(self, atestlist):
        ""
        logger.info('\nComposing CDash submission data...')

        set_global_data( self.fmtr, self.dspecs, self.rtinfo, atestlist )
        set_test_list( self.fmtr, self.dspecs, atestlist, self.rtinfo['rundir'] )

    def _write_data(self, fmtr):
        ""
        if self.dspecs.url:

            fname = pjoin( self.rtinfo['rundir'], 'vvtest_cdash_submit.xml' )

            try:
                logger.info('Writing CDash submission file: {0}'.format(fname))
                self._write_file( fmtr, fname )

                assert self.dspecs.project, 'CDash project name not set'
                self.subm.setDestination( self.dspecs.url,
                                          self.dspecs.project,
                                          method=self.dspecs.method )
                logger.info('Sending CDash file to:', self.dspecs.url + ',',
                        'project='+self.dspecs.project )
                self.subm.send( fname )

            except Exception as e:
                logger.warn('error submitting CDash results: {0}'.format(e))

        else:
            logger.info( 'Writing CDash submission file:', self.dspecs.file )
            self._write_file( fmtr, self.dspecs.file )

    def _write_file(self, fmtr, filename):
        ""
        fmtr.writeToFile( filename )
        self.permsetter.apply( filename )


def parse_destination_string( destination ):
    ""
    tokens = destination.split(',')

    if len( tokens ) > 0 and tokens[0].strip():
        dest = tokens[0].strip()
    else:
        dest = None

    err = ''
    if not dest:
        err = 'missing or invalid CDash URL or filename'

    specs = {}

    for tok in tokens[1:]:
        tok = tok.strip()
        if tok:
            nvL = tok.split('=',1)
            if len(nvL) == 2 and nvL[0].strip() and nvL[1].strip():
                specs[ nvL[0].strip() ] = nvL[1].strip()
            else:
                err = 'invalid CDash attribute specification'

    return dest,specs,err


def construct_destination_specs( destination, project=None,
                                              datestamp=None,
                                              options=[],
                                              tag=None ):
    ""
    dspecs = DestinationSpecs()

    dest,specs,err = parse_destination_string( destination )

    if not err:

        if is_http_url( dest ):
            dspecs.url = dest
        else:
            dspecs.file = dest

        dspecs.project = specs.get( 'project', project )

        ds = specs.get( 'date', datestamp )
        dspecs.date = attempt_int_conversion( ds )

        dspecs.group = specs.get( 'group', None )
        dspecs.site  = specs.get( 'site', None )
        dspecs.name  = specs.get( 'name', None )
        dspecs.method = specs.get( 'method', None )

        if not err:
            err = check_fill_files_attr( dspecs, specs.get( 'files', None ) )

        if not err:
            err = check_fill_filemax_attr( dspecs, specs.get( 'filemax', None ) )

    return dspecs,err


def check_fill_files_attr( dspecs, value ):
    ""
    err = ''

    if value:
        if value not in ['nonpass','all']:
            err = "unknown 'files' attribute value: "+repr(value)
        else:
            dspecs.files = value

    return err


def check_fill_filemax_attr( dspecs, value ):
    ""
    err = ''

    if value:
        nval = attempt_parse_number( value )

        if nval == None:
            val = ''.join( value.lower().split() )
            if val.endswith('b'):
                nval = attempt_parse_number( val[:-1], 0.001 )
            if val.endswith('k'):
                nval = attempt_parse_number( val[:-1], 1 )
            elif val.endswith('kb'):
                nval = attempt_parse_number( val[:-2], 1 )
            if val.endswith('m'):
                nval = attempt_parse_number( val[:-1], 1000 )
            elif val.endswith('mb'):
                nval = attempt_parse_number( val[:-2], 1000 )
            if val.endswith('g'):
                nval = attempt_parse_number( val[:-1], 1000000 )
            elif val.endswith('gb'):
                nval = attempt_parse_number( val[:-2], 1000000 )
            if val.endswith('t'):
                nval = attempt_parse_number( val[:-1], 1000000000 )
            elif val.endswith('tb'):
                nval = attempt_parse_number( val[:-2], 1000000000 )

        if nval == None:
            err = "invalid 'filemax' attribute value: "+repr(value)
        else:
            dspecs.filemax = nval

    return err


def attempt_parse_number( astring, multiplier=1 ):
    ""
    try:
        ival = max( 0, int( astring ) ) * multiplier
    except Exception:
        try:
            fval = max( 0.0, float( astring ) ) * multiplier
        except Exception:
            pass
        else:
            return fval
    else:
        return ival

    return None


def attempt_int_conversion( datestring ):
    ""
    if datestring != None:
        try:
            idate = int( datestring )
            return idate
        except Exception:
            pass

        try:
            idate = int( float( datestring ) )
            return idate
        except Exception:
            pass

    return datestring


class DestinationSpecs:
    def __init__(self):
        ""
        self.url = None
        self.file = None
        self.date = None
        self.project = None
        self.group = None
        self.site = None
        self.name = None
        self.files = 'nonpass'
        self.filemax = 100
        self.method = None


def set_global_data( fmtr, dspecs, rtinfo, tlist ):
    ""
    t0 = tlist.getResultsDate()
    if dspecs.date:
        bdate = dspecs.date
        tstart = bdate if t0 is None else t0
    else:
        bdate = time.time() if t0 is None else t0
        tstart = bdate

    if dspecs.group:
        grp = dspecs.group
    else:
        grp = None

    if dspecs.site:
        site = dspecs.site
    else:
        site = platform.uname()[1]

    if dspecs.name:
        bname = dspecs.name
    else:
        rdir = rtinfo.get( 'rundir', None )
        if rdir:
            rdir = basename( rdir )
        bname = rdir

    fmtr.setBuildID( build_date=bdate,
                     build_group=grp,
                     site_name=site,
                     build_name=bname )

    fmtr.setTime( tstart, tlist.getFinishDate() )


def set_test_list( fmtr, dspecs, atestlist, testdir ):
    ""
    fspec = dspecs.files
    max_KB = dspecs.filemax

    for tcase in atestlist.getActiveTests():

        tspec = tcase.getSpec()
        tstat = tcase.getStat()

        vvstat = tstat.getResultStatus()
        log = outpututils.get_log_file_path( testdir, tspec )

        kwargs = {}

        if vvstat == 'notrun':
            kwargs['status']    = 'notrun'

        elif vvstat == 'pass':
            kwargs['status']    = 'passed'
            kwargs['runtime']   = tstat.getRuntime( None )
            kwargs['exitvalue'] = tstat.getAttr( 'xvalue', None )
            kwargs['command']   = outpututils.get_test_command_line( log )
            if fspec == 'all':
                kwargs['output'] = get_test_output( testdir, tspec, max_KB )

        else:
            kwargs['status']    = 'failed'
            kwargs['runtime']   = tstat.getRuntime( None )
            kwargs['detail']    = vvstat
            kwargs['exitvalue'] = tstat.getAttr( 'xvalue', None )
            kwargs['command']   = outpututils.get_test_command_line( log )
            kwargs['output']    = get_test_output( testdir, tspec, max_KB )

        fmtr.addTest( tspec.getDisplayString(), **kwargs )


def is_http_url( destination ):
    ""
    if os.path.exists( destination ):
        return False
    elif destination.startswith( 'http://' ) or \
         destination.startswith( 'https://' ):
        return True
    else:
        return False


def get_test_output( testdir, tspec, file_max_KB ):
    ""
    tdir = pjoin( testdir, tspec.getExecuteDirectory() )
    displ = pjoin( testdir, tspec.getDisplayString() )

    out = '\n'
    out += 'CURTIME : ' + time.ctime() + '\n'
    out += 'HOSTNAME: ' + platform.uname()[1] + '\n'
    out += 'TESTDIR : ' + tdir + '\n'
    out += 'TEST ID : ' + displ + '\n'

    out += '\n$ ls -l '+tdir+'\n'
    out += '\n'.join( list_directory_as_strings( tdir ) ) + '\n'

    pn = outpututils.get_log_file_path( testdir, tspec )

    if os.path.exists( pn ):
        out += '\n' + get_file_contents( pn, file_max_KB ) + '\n'
    else:
        out += '\n*** log file does not exist: '+pn+'\n'

    return out


def get_file_contents( filename, max_KB ):
    ""
    out = '$ cat '+filename+'\n'

    try:
        out += outpututils.file_read_with_limit( filename, max_KB )
    except Exception as e:
        out += '*** failed to cat file: '+str(e)

    if not out.endswith( '\n' ):
        out += '\n'

    return out


def list_directory_as_strings( dirpath ):
    ""
    try:
        fL = os.listdir( dirpath )
        fL.append( '.' )
    except Exception as e:
        return [ '*** failed to list directory "'+dirpath+'": '+str(e) ]

    lines = []
    maxlens = [ 0, 0, 0, 0, 0, 0 ]
    for fn,props in list_file_properties( dirpath, fL ):
        lineL = file_properties_as_strings( fn, props, maxlens )
        lines.append( lineL )

    fmtlines = []
    for lineL in lines:
        fmtL = [ lineL[0],
                 ( "%-"+str(maxlens[1])+"s" ) % ( lineL[1], ),
                 ( "%-"+str(maxlens[2])+"s" ) % ( lineL[2], ),
                 ( "%"+str(maxlens[3])+"s" ) % ( lineL[3], ),
                 lineL[4],
                 lineL[5] ]
        fmtlines.append( ' '.join( fmtL ) )

    return fmtlines


def file_properties_as_strings( fname, props, maxlens ):
    ""
    sL = [ props['type'] + props['mode'],
           props['owner'],
           props['group'],
           str( props['size'] ),
           make_string_time( props['mtime'] ) ]

    if props['type'] == 'l':
        sL.append( fname + ' -> ' + props['link'] )
    else:
        sL.append( fname )

    for i in range( len(sL) ):
        maxlens[i] = max( maxlens[i], len(sL[i]) )

    return sL


def make_string_time( secs ):
    ""
    return time.strftime( "%Y/%m/%d %H:%M:%S", time.localtime(secs) )


def list_file_properties( dirpath, fL ):
    ""
    files = []

    for fn in fL:
        pn = pjoin( dirpath, fn )
        props = read_file_properties( pn )
        files.append( [ props.get('mtime'), fn, props ] )

    files.sort()

    return [ L[1:] for L in files ]


def read_file_properties( path ):
    ""
    pwd, grp = get_pwd_and_grp_modules()

    ftype,statvals = get_stat_values( path )

    props = {}
    props['type'] = ftype

    if ftype == 'l':
        props['link'] = read_symlink( path )

    if statvals != None:
        props['mtime'] = statvals[ stat.ST_MTIME ]
        props['size']  = statvals[ stat.ST_SIZE ]
        props['owner'] = get_path_owner( statvals, pwd )
        props['group'] = get_path_group( statvals, grp )
        props['mode']  = make_mode_string( statvals )
    else:
        props['mtime'] = 0
        props['size']  = 0
        props['owner'] = '?'
        props['group'] = '?'
        props['mode']  = '?????????'

    return props


def get_pwd_and_grp_modules():
    ""
    try:
        import pwd
    except Exception:
        pwd = None

    try:
        import grp
    except Exception:
        grp = None

    return pwd, grp


def make_mode_string( statvals ):
    ""
    try:
        perm = stat.S_IMODE( statvals[ stat.ST_MODE ] )
        s = ''
        s += ( 'r' if perm & stat.S_IRUSR else '-' )
        s += ( 'w' if perm & stat.S_IWUSR else '-' )
        s += ( 'x' if perm & stat.S_IXUSR else '-' )
        s += ( 'r' if perm & stat.S_IRGRP else '-' )
        s += ( 'w' if perm & stat.S_IWGRP else '-' )
        s += ( 'x' if perm & stat.S_IXGRP else '-' )
        s += ( 'r' if perm & stat.S_IROTH else '-' )
        s += ( 'w' if perm & stat.S_IWOTH else '-' )
        s += ( 'x' if perm & stat.S_IXOTH else '-' )
        return s

    except Exception:
        return '?????????'


def get_stat_values( path ):
    ""
    try:
        if os.path.islink( path ):
            return 'l', os.lstat( path )
        else:
            statvals = os.stat( path )
            if os.path.isdir( path ):
                return 'd', statvals
            else:
                return '-', statvals
    except Exception:
        return '?', None


def get_path_owner( statvals, pwdmod ):
    ""
    uid = statvals[ stat.ST_UID ]
    try:
        return pwdmod.getpwuid( uid )[0]
    except Exception:
        return str( uid )


def get_path_group( statvals, grpmod ):
    ""
    gid = statvals[ stat.ST_GID ]
    try:
        return grpmod.getgrgid( gid )[0]
    except Exception:
        return str( gid )


def read_symlink( path ):
    ""
    try:
        if os.path.islink( path ):
            return os.readlink( path )
    except Exception:
        return ''

    return None
