#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os
import re

from .errors import TestSpecError
from .wordexpr import WordExpression, create_word_expression
from .wordexpr import WildcardWordExpression
from .paramexpr import ParameterExpression
from .wordcheck import check_expression_words
from .wordcheck import check_wildcard_expression_words

from .teststatus import RESULTS_KEYWORDS


def evaluate_testname_expr( testname, expr ):
    ""
    wx = WildcardWordExpression( expr )
    check_wildcard_expression_words( wx.getWordList() )
    return wx.evaluate( testname )


def evaluate_platform_expr( platname, expr ):
    ""
    wx = WildcardWordExpression( expr )
    check_wildcard_expression_words( wx.getWordList() )
    return wx.evaluate( platname, case_insensitive=True )


def evaluate_option_expr( optlist, expr ):
    ""
    wx = WildcardWordExpression( expr )
    check_wildcard_expression_words( wx.getWordList() )
    return wx.evaluate( optlist )


def evaluate_parameter_expr( paramD, expr ):
    ""
    pf = ParameterExpression( expr )
    return pf.evaluate( paramD )


def variable_expansion( tname, platname, paramD, fL ):
    """
    Replaces shell style variables in the given file list with their values.
    For example $np or ${np} is replaced with 4.  Also replaces NAME and
    PLATFORM with their values.  The 'fL' argument can be a list of strings
    or a list of [string 1, string 2] pairs.  Dollar signs preceeded by a
    backslash are not expanded and the backslash is removed.
    """
    if platname == None: platname = ''
    
    if len(fL) > 0:
      
      # substitute parameter values for $PARAM, ${PARAM}, and {$PARAM} patterns;
      # also replace the special NAME variable with the name of the test and
      # PLATFORM with the name of the current platform
      for n,v in list(paramD.items()) + [('NAME',tname)] + [('PLATFORM',platname)]:
        pat1 = re.compile( '[{](?<![\\\\])[$]' + n + '[}]' )
        pat2 = re.compile( '(?<![\\\\])[$][{]' + n + '[}]' )
        pat3 = re.compile( '(?<![\\\\])[$]' + n + '(?![_a-zA-Z0-9])' )
        if type(fL[0]) == type([]):
          for fpair in fL:
            f,t = fpair
            f,n = pat1.subn( v, f )
            f,n = pat2.subn( v, f )
            f,n = pat3.subn( v, f )
            if t != None:
              t,n = pat1.subn( v, t )
              t,n = pat2.subn( v, t )
              t,n = pat3.subn( v, t )
            fpair[0] = f
            fpair[1] = t
            # TODO: replace escaped $ with a dollar
        else:
          for i in range(len(fL)):
            f = fL[i]
            f,n = pat1.subn( v, f )
            f,n = pat2.subn( v, f )
            f,n = pat3.subn( v, f )
            fL[i] = f
      
      # replace escaped dollar with just a dollar
      patD = re.compile( '[\\\\][$]' )
      if type(fL[0]) == type([]):
        for fpair in fL:
          f,t = fpair
          f,n = patD.subn( '$', f )
          if t != None:
            t,n = patD.subn( '$', t )
          fpair[0] = f
          fpair[1] = t
      else:
        for i in range(len(fL)):
          f = fL[i]
          f,n = patD.subn( '$', f )
          fL[i] = f


def check_forced_group_parameter( force_params, name_list, lineno ):
    ""
    if force_params is not None and len(name_list) > 1:
        for n in name_list:
            if n in force_params:
                raiseError( 'cannot force a grouped parameter name:',
                            repr(n), line=lineno )


def check_for_duplicate_parameter( paramlist, lineno ):
    ""
    for val in paramlist:
        if paramlist.count( val ) > 1:

            if is_list_or_tuple(val):
                dup = ','.join(val)
            else:
                dup = str(val)

            raiseError( 'duplicate parameter value:', repr(dup), line=lineno )


def remove_duplicate_parameter_values( paramlist ):
    ""
    newlist = []

    for val in paramlist:
        if newlist.count( val ) == 0:
            newlist.append( val )

    return newlist


def is_list_or_tuple( obj ):
    ""
    if type(obj) in [ type(()), type([]) ]:
        return True

    return False


def create_dependency_result_expression( attrs, lineno=None ):
    ""
    wx = None

    if attrs is not None and 'result' in attrs:

        result = attrs['result'].strip()

        if result == '*':
            wx = WordExpression()
        else:
            err = ''
            try:
                wx = create_word_expression( [result] )

                for word in wx.getWordList():
                    if word not in RESULTS_KEYWORDS:
                        err = 'non-result word: '+repr(word)
                        break

            except Exception as e:
                err = str(e)

            if err:
                msg = 'invalid results expression: '+repr(result)+' : '+err
                if lineno:
                    msg += ', line '+str(lineno)
                raiseError( msg )

    return wx


def parse_to_word_expression( string_or_list, lineno=None ):
    ""
    wx = None

    if isinstance( string_or_list, str ):
        exprlist = [string_or_list]
    else:
        exprlist = string_or_list

    try:
        wx = create_word_expression( exprlist, allow_wildcards=True )

    except Exception as e:
        msg = 'invalid expression'
        if lineno:
            msg += ' at line '+str(lineno)
        msg += ': '+repr(string_or_list)+', '+str(e)
        raiseError( msg )

    return wx


def raiseError( arg0, *args, **kwargs ):
    ""
    err = ' '.join( [str(arg0)] + [str(arg) for arg in args] )
    if 'line' in kwargs:
        err += ', line '+str(kwargs['line'])

    raise TestSpecError( err )
