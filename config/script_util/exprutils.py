#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.


def platform_expr( expr ):
    '''
    Evaluates the given word expression against the current
    platform name.  For example, the expression could be
    "Linux or Darwin" and would be true if the current platform
    name is "Linux" or if it is "Darwin".
    '''
    import vvtest_util as vvt
    from libvvtest.wordexpr import WildcardWordExpression
    wx = WildcardWordExpression( expr )
    return wx.evaluate( vvt.PLATFORM )

def parameter_expr( expr ):
    '''
    Evaluates the given parameter expression against the parameters
    defined for the current test.  For example, the expression
    could be "dt<0.01 and dh=0.1" where dt and dh are parameters
    defined in the test.
    '''
    import vvtest_util as vvt
    from libvvtest.paramexpr import ParameterExpression
    pf = ParameterExpression( expr )
    return pf.evaluate( vvt.PARAM_DICT )

def option_expr( expr ):
    '''
    Evaluates the given option expression against the options
    given on the vvtest command line.  For example, the expression
    could be "not dbg and not intel", which would be false if
    "-o dbg" or "-o intel" were given on the command line.
    '''
    import vvtest_util as vvt
    from libvvtest.wordexpr import WildcardWordExpression
    wx = WildcardWordExpression( expr )
    return wx.evaluate( vvt.OPTIONS )
