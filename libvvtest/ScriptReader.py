#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
sys.dont_write_bytecode = True
sys.excepthook = sys.__excepthook__
import os
import re
import token
import tokenize

from .errors import TestSpecError


# include directive aliases; the final keyword name is always 'include'
INCLUDE_KEYWORDS = [ 'include', 'insert directive file' ]


class ScriptSpec:

    def __init__(self, lineno, keyword, attrs, attr_names, value):
        ""
        self.keyword = keyword
        self.attrs = attrs
        self.attr_names = attr_names  # retains order, duplicates possible
        self.value = value
        self.lineno = lineno


class ScriptReader:

    def __init__(self, filename):
        """
        """
        self.filename = filename

        self.speclineL = []  # list of [line number, raw spec string]
        self.specL = []  # list of ScriptSpec objects
        self.shbang = None  # None or a string

        self.readfile( filename )

    def basename(self):
        """
        Returns the base name of the source file without the extension.
        """
        return os.path.splitext( os.path.basename( self.filename ) )[0]

    def getSpecList(self):
        """
        Returns a list of ScriptSpec objects whose order is the same as in
        the source script.
        """
        return self.specL

    vvtpat = re.compile( '[ \t]*#[ \t]*VVT[ \t]*:' )

    def readfile(self, filename):
        ""
        lines = read_directive_lines( filename )

        self.spec = None
        for line,lineno in lines:
            info = filename+':'+repr(lineno)
            if lineno == 1 and line[:2] == '#!':
                self.shbang = line[2:].strip()
            else:
                self.parse_line( line, info )

        if self.spec != None:
            self.speclineL.append( self.spec )

        self.process_specs()

        self.filename = filename

    def parse_line(self, line, info):
        ""
        if line:
            char0 = line[0]

            if char0 == '#':
                m = ScriptReader.vvtpat.match( line )
                if m is not None:
                    self.parse_spec( line[m.end():], info )

        elif self.spec != None:
            # an empty line stops any continuation
            self.speclineL.append( self.spec )
            self.spec = None

    def parse_spec(self, line, info):
        """
        Parse the contents of the line after a #VVT: marker.
        """
        line = line.strip()
        if line:
            if line[0] == ':':
                # continuation of previous spec
                if self.spec == None:
                    raise TestSpecError( "A #VVT:: continuation was found" + \
                            " but there is nothing to continue, " + info )
                elif len(line) > 1:
                    self.spec[1] += ' ' + line[1:]
            elif self.spec == None:
                # no existing spec and new spec found
                self.spec = [ info, line ]
            else:
                # spec exists and new spec found
                self.speclineL.append( self.spec )
                self.spec = [ info, line ]
        elif self.spec != None:
            # an empty line stops any continuation
            self.speclineL.append( self.spec )
            self.spec = None

    # the following pattern should match the first paren enclosed stuff,
    # but parens within double quotes are ignored
    #   1. this would match as few chars within parens
    #       [(].*?[)]
    #   2. this would match as few chars within parens unless there is a
    #      double quote in the parens
    #       [(][^"]*?[)]
    #   3. this would match as few chars within double quotes
    #       ["].*?["]
    #   4. this would match as few chars within double quotes possible
    #      chars on either side (but as few of them as well)
    #       .*?["].*?["].*?
    #   5. this will match either number 2 or number 4 above as a regex group
    #       ([^"]*?|.*?["].*?["].*?)
    #   6. this adds back the parens on the outside
    #       [(]([^"]*?|.*?["].*?["].*?)[)]
    ATTRPAT = re.compile( '[(]([^"]*?|.*?["].*?["].*?)[)]' )

    # this pattern matches everything up to the first ':' or '=' or paren
    DEFPAT = re.compile( '.*?[:=(]' )

    def process_specs(self):
        """
        Turns the list of string specifications into keywords with attributes
        and content.
        """
        kpat = ScriptReader.DEFPAT

        for info,line in self.speclineL:
            key = None
            val = None
            attrs = None
            attr_names = None
            m = kpat.match( line )
            if m:
                key = line[:m.end()-1].strip()
                rest = line[m.end()-1:]

                attrs,attr_names,val = check_parse_attributes_section( rest, info )

            else:
                key = line.strip()

            if not key:
                raise TestSpecError(
                        'missing or invalid specification keyword, ' + info )

            if key in INCLUDE_KEYWORDS:
                # an alias is replaced with the primary name
                key = INCLUDE_KEYWORDS[0]
                # replace 'val' with the specs list from the included file
                val = self._parse_insert_file( info, val )

            specobj = ScriptSpec( info, key, attrs, attr_names, val )
            self.specL.append( specobj )

    def _parse_insert_file(self, info, filename):
        ""
        if filename == None or not filename.strip():
            raise TestSpecError(  'missing include file name, ' + info )

        if not os.path.isabs( filename ):
            d = os.path.dirname( os.path.abspath( self.filename ) )
            filename = os.path.normpath( os.path.join( d, filename ) )

        try:
            inclreader = ScriptReader( filename )
        except TestSpecError:
            raise
        except Exception:
            raise TestSpecError( 'at ' + info + ' the include '
                                 'failed: ' + str( sys.exc_info()[1] ) )

        return inclreader.getSpecList()


def read_directive_lines( filename ):
    ""
    lines = []

    skipnl = False
    with open( filename, 'rt' ) as fp:
        for tok_type,tok,beg,end,line in tokenize.generate_tokens( fp.readline ):

            if tok_type == tokenize.COMMENT:
                lines.append( (tok.strip(),end[0]) )
                skipnl = True

            else:
                if tok_type == tokenize.NL:
                    if not skipnl:
                        lines.append( ('',end[0]) )
                elif tok_type == token.STRING:
                    lines.append( ('',end[0]) )
                elif tok_type == token.NEWLINE:
                    pass
                else:
                    break
                skipnl = False

    return lines


def split_attr_match( matchobj, origstr ):
    ""
    attrs = origstr[:matchobj.end()]
    attrs = attrs.lstrip('(').rstrip(')').strip()

    therest = origstr[matchobj.end():].strip()

    return attrs, therest


def parse_attr_string( attrstr, info ):
    ""
    D = {}
    L = []
    for s in attrstr.split(','):
        s = s.strip().strip('"').strip()
        i = s.find( '=' )
        if i == 0:
            raise TestSpecError( \
                    'invalid attribute specification, ' + info )
        elif i > 0:
            n = s[:i].strip()
            v = s[i+1:].strip().strip('"')
            D[n] = v
            L.append(n)
        elif s:
            D[s] = ''
            L.append(s)

    return D,L


def check_parse_attributes_section( a_string, file_and_lineno ):
    ""
    attrD = None
    nameL = None
    tail = None

    attrs = None
    a_string = a_string.strip()

    if a_string and a_string[0] == '(':

        m = ScriptReader.ATTRPAT.match( a_string )
        if m:
            attrs,rest = split_attr_match( m, a_string )

            if rest:
                if rest[0] in ':=':
                    tail = rest[1:].strip()
                elif rest[0] == '#':
                    tail = ''
                else:
                    raise TestSpecError( \
                        'extra text following attributes, ' + file_and_lineno )
            else:
                tail = ''
        else:
            raise TestSpecError( \
                  'malformed attribute specification, ' + file_and_lineno )

    elif a_string and a_string[0] in ':=':
        tail = a_string[1:].strip()
    else:
        tail = a_string.strip()

    if attrs is not None:
        attrD,nameL = parse_attr_string( attrs, file_and_lineno )

    return attrD, nameL, tail
