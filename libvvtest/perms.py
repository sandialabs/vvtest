#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
sys.dont_write_bytecode = True
sys.excepthook = sys.__excepthook__
import os
import stat
import tempfile


class PermissionSpecificationError( Exception ):
    pass


def apply( path, *stringspecs, **kwargs ):
    """
    Parse and apply group and/or file mode specifications to a path. The
    only known keyword argument is 'recurse' which defaults to False.
    Examples:

        apply( 'some/path', '+rX', recurse=True )
        apply( 'some/path', 'some-group-name', 'g=rX', 'o=' )

    The syntax and behavior closely matches UNIX chmod, except that a group
    name or numerial ID can be given. Also, 'g+S' will only apply setgid on
    directories.
    """
    recurse = kwargs.pop( 'recurse', False )
    if len( kwargs ) > 0:
        raise PermissionSpecificationError(
                            'unknown keyword arguments: '+repr(kwargs) )

    specs = PermissionSpecifications( *stringspecs )
    specs.apply( path, recurse=recurse )


def my_user_name():
    """
    Returns the name of the user running this process.
    """
    uid = os.getuid()
    try:
        usr = pwd.getpwuid( uid )[0]
    except Exception:
        import getpass
        usr = getpass.getuser()
    return usr


def get_user_name( path=None ):
    """
    Returns the owner of the given pathname, or the owner of the current
    process if 'path' is not given. If the numeric user id cannot be mapped
    to a user name, the numeric id is returned as a string.
    """
    if path is None:
        return my_user_name()

    uid = os.stat( path ).st_uid

    try:
        import pwd
        name = pwd.getpwuid( uid )[0]
    except Exception:
        name = str(uid)

    return name


def filemode( path ):
    """
    Returns the integer containing the file mode permissions for the
    given pathname.
    """
    return stat.S_IMODE( os.stat(path)[stat.ST_MODE] )


def fileowner( path ):
    """
    Returns the user name of the owner of the given pathname.  If the user
    id of the file is not in the password database (and so a user name
    cannot associated with the user id), then None is returned.
    """
    uid = os.stat( path ).st_uid
    try:
        import pwd
        ent = pwd.getpwuid( uid )
    except Exception:
        return None
    return ent[0]


def filegroup( path ):
    """
    Returns the group name of the given pathname.  If the group id of
    the file is not in the group database (and so a group name cannot
    associated with the group id), then None is returned.
    """
    gid = os.stat( path ).st_gid
    try:
        import grp
        ent = grp.getgrgid( gid )
    except Exception:
        return None
    return ent[0]


class PermissionSpecifications:

    def __init__(self, *stringspecs):
        ""
        self.specs = []
        for sspec in split_specs_by_commas( stringspecs ):
            self.specs.append( parse_string_spec(sspec) )

    def apply(self, path, recurse=False):
        ""
        if not os.path.islink( path ):

            for spec in self.specs:
                spec.apply( path )

            if recurse and os.path.isdir( path ):
                for fn in os.listdir( path ):
                    fp = os.path.join( path, fn )
                    self.apply( fp, recurse )


def split_specs_by_commas( stringspecs ):
    ""
    sL = []

    for sspec in stringspecs:
        for s in sspec.split(','):
            s = s.strip()
            if s:
                sL.append(s)

    return sL


class PermSpec:

    def __init__(self):
        ""
        self.bitsoff = 0
        self.bitson = 0
        self.xbits = 0
        self.dbits = 0

    def apply(self, path):
        ""
        md = os.stat(path)[stat.ST_MODE]

        isdir = stat.S_ISDIR( md )
        fm = stat.S_IMODE( md )
        xval = (fm & (stat.S_IXUSR|stat.S_IXGRP|stat.S_IXOTH) )

        fm &= ( ~(self.bitsoff) )
        fm |= self.bitson
        if xval != 0 or isdir:
            fm |= self.xbits
        if isdir:
            fm |= self.dbits

        os.chmod( path, fm )


class GroupSpec:

    def __init__(self, groupid):
        ""
        self.groupid = groupid

    def apply(self, path):
        ""
        uid = os.stat( path ).st_uid
        os.chown( path, uid, self.groupid )


mask_off = { 'u':stat.S_IRWXU,
             'g':stat.S_IRWXG,
             'o':stat.S_IRWXO }

bit_map = {
    'u': {
        'r':stat.S_IRUSR,
        'w':stat.S_IWUSR,
        'x':stat.S_IXUSR,
        's':stat.S_ISUID,
        't':0,
    },
    'g': {
        'r':stat.S_IRGRP,
        'w':stat.S_IWGRP,
        'x':stat.S_IXGRP,
        's':stat.S_ISGID,
        't':0,
    },
    'o': {
        'r':stat.S_IROTH,
        'w':stat.S_IWOTH,
        'x':stat.S_IXOTH,
        's':0,
        't':stat.S_ISVTX,
    }
}


def parse_string_spec( strspec ):
    ""
    who = ''
    op = ''
    what = ''

    N = len(strspec)
    i = 0
    while i < N:
        c = strspec[i]
        if c in '=+-':
            op = c
            what = strspec[i+1:]
            break
        elif c == 'a':
            who += 'ugo'
        elif c in 'ugo':
            who += c
        else:
            break
        i += 1

    if op and check_bit_letters(what):
        spec = create_change_mode_spec( who, op, what )
    else:
        spec = parse_group_string_spec( strspec )

    return spec


def create_change_mode_spec( who, op, what ):
    ""
    spec = PermSpec()

    if who:
        umask = 0
    else:
        umask = get_umask()
        who = 'ugo'

    for w in who:

        if op == '=':
            spec.bitsoff |= mask_off[w]

        for v in what:
            if op == '-':
                if v == 'X':
                    spec.bitsoff |= bit_map[w]['x']
                else:
                    spec.bitsoff |= bit_map[w][v]
            else:
                if v == 'X':
                    spec.xbits |= bit_map[w]['x']
                elif v == 'S':
                    spec.dbits |= bit_map[w]['s']
                else:
                    spec.bitson |= bit_map[w][v]

    spec.bitson &= ( ~umask )
    spec.xbits &= ( ~umask )

    return spec


def parse_group_string_spec( strspec ):
    ""
    try:
        gid = int( strspec )
    except Exception:
        try:
            import grp
            gid = grp.getgrnam( strspec ).gr_gid
        except Exception:
            raise PermissionSpecificationError(
                    'Invalid specification or group name: "'+strspec+'"' )

    spec = GroupSpec( gid )

    # check that a path can be changed to the given group
    tmpd = tempfile.mkdtemp()
    try:
        try:
            spec.apply( tmpd )
        except Exception:
            raise PermissionSpecificationError(
                    'Invalid specification or group name: "'+strspec+'"' )
    finally:
        os.rmdir( tmpd )

    return spec


def check_bit_letters( what ):
    ""
    for c in what:
        if c not in 'rwxXsSt':
            return False

    return True


def get_umask():
    ""
    msk = os.umask(0)
    os.umask( msk )
    return msk
