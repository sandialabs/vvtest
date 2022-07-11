#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import fnmatch

from .wordcheck import check_expression_words
from .wordcheck import check_wildcard_expression_words


def create_word_expression( list_of_string_expr, allow_wildcards=False ):
    ""
    exprL = []

    if list_of_string_expr:
        for expr in list_of_string_expr:
            exprL.append( replace_forward_slashes( expr ) )

    if len( exprL ) > 0:
        expr = join_expressions_with_AND( exprL )
        if allow_wildcards:
            wx = WildcardWordExpression( expr )
            check_wildcard_expression_words( wx.getWordList() )
        else:
            wx = WordExpression( expr )
            check_expression_words( wx.getWordList() )

        return wx

    return None


class WordExpression:
    """
    Takes a string consisting of words, parentheses, and the operators "and",
    "or", and "not".  A word in the expression is any sequence of characters
    not containing a space or a parenthesis (except "and", "or", and "not").
    The initial string is parsed during construction then later evaluated
    with the evaluate() method.

    When no expression is given to the constructor (a None), the evaluate
    method will always return True. While an empty string given as the
    expression will always evaluate to False.
    """

    def __init__(self, expr=None):
        ""
        self.expr = None
        self.evalexpr = None
        self.words = set()   # the words in the expression

        self.append( expr )

    def getExpression(self):
        ""
        return self.expr

    def append(self, expr):
        """
        Extends the given expression string using the AND operator.
        """
        if expr is not None:

            expr = expr.strip()

            if self.expr is not None:
                expr = combine_two_expressions( self.expr, expr )

            self.expr = expr

            self.evalexpr = parse_word_expression( self.expr, self.words )

    def getWordList(self):
        """
        Returns a list containing the words in the current expression.
        """
        return list( self.words )

    def evaluate(self, string_or_list, case_insensitive=False):
        """
        If 'string_or_list' is a string, then each word in the expression
        is True if it equals the string.

        If 'string_or_list' is a list or generator, then each word in the
        expression evaluates to True if the word is a member of the list.
        """
        members = make_list( string_or_list, case_insensitive )
        return self._evaluate( members.count, case_insensitive )

    def _evaluate(self, evaluator_func, case_insensitive=False):
        """
        Evaluates the expression from left to right using the given
        'evaluator_func' to evaluate True/False of each word.  If the original
        expression string is empty, False is returned.  If no expression was
        set in this object (it is None), True is returned.
        """
        if self.evalexpr is None:
            return True

        if case_insensitive:
            def evalfunc(tok):
                if evaluator_func(tok.lower()): return True
                return False
        else:
            def evalfunc(tok):
                if evaluator_func(tok): return True
                return False

        r = eval( self.evalexpr )

        return r

    def __str__(self):
        ""
        if self.evalexpr is None:
            return "<no expression>"
        else:
            return str(self.expr)


class WildcardWordExpression( WordExpression ):
    """
    Recall shell style wildcard matching:

        *       matches everything
        ?       matches any single character
        [seq]   matches any character in seq
        [!seq]  matches any char not in seq
    """

    def evaluate(self, string_or_list, case_insensitive=False):
        ""
        words = make_list( string_or_list, case_insensitive )
        matcher = WildcardMatcher( words, case_insensitive )
        return self._evaluate( matcher.match )


class WildcardMatcher:

    def __init__(self, word_list, case_insensitive):
        self.words = word_list
        self.case = ( not case_insensitive )

    def match(self, word):
        if self.case:
            return len( fnmatch.filter( self.words, word ) ) > 0
        else:
            return len( fnmatch.filter( self.words, word.lower() ) ) > 0


def make_list( string_or_list, case_insensitive ):
    ""
    if isinstance( string_or_list, str ):
        words = [string_or_list]
    else:
        words = list( string_or_list )

    if case_insensitive:
        words = [ word.lower() for word in words ]

    return words


def parse_word_expression( expr, wordset ):
    """
    Throws a ValueError if the string is an invalid expression.
    Returns the final expression string (which may be modified from the
    original).
    """
    if wordset != None:
        wordset.clear()

    toklist = separate_expression_into_tokens( expr )
    evalexpr = convert_token_list_into_eval_string( toklist )

    add_words_to_set( toklist, wordset )

    def evalfunc(tok):
        return True
    try:
        # evaluate the expression to test validity
        v = eval( evalexpr )
        assert type(v) == type(False)
    except Exception:
        raise ValueError( 'invalid option expression: "' + expr + '"' )

    return evalexpr


def combine_two_expressions( expr1, expr2 ):
    ""
    if expr1 and expr2:
        expr = expr1 + ' and ' + conditional_paren_wrap( expr2 )
    else:
        # one expression is empty, which is always false,
        # so replace the whole thing with an empty expr
        expr = ''

    return expr


def conditional_paren_wrap( expr ):
    ""
    if expr and expr.strip():
        tree = parenthetical_tokenize( expr )
        if tree.numTokens() > 1:
            if not ( tree.numTokens() == 2 and tree.getToken(0) == 'not' ):
                return '( '+expr+' )'

    return expr


class TokenTree:

    def __init__(self):
        ""
        self.toks = []

    def parse(self, toklist, tok_idx):
        ""
        while tok_idx < len(toklist):
            tok = toklist[tok_idx]
            tok_idx += 1

            if tok == '(':
                sub = TokenTree()
                self.toks.append( sub )
                tok_idx = sub.parse( toklist, tok_idx )
            elif tok == ')':
                break
            else:
                self.toks.append( tok )

        return tok_idx

    def setTokens(self, toks):
        ""
        del self.toks[:]
        self.toks.extend( toks )

    def numTokens(self): return len( self.toks )
    def getToken(self, idx): return self.toks[idx]
    def getTokens(self): return self.toks


def collect_token_list_from_tree( tree, toks ):
    ""
    for tok in tree.getTokens():
        if isinstance( tok, TokenTree ):
            if tok.numTokens() > 1:
                toks.append( '(' )
                collect_token_list_from_tree( tok, toks )
                toks.append( ')' )
            else:
                collect_token_list_from_tree( tok, toks )
        else:
            toks.append( tok )


def parenthetical_tokenize( expr ):
    """
    Parse the given expression into a single TokenTree object. Each TokenTree
    contains a list of string tokens and/or TokenTree objects. TokenTree
    objects are created when a left paren is encountered.
    """
    assert expr and expr.strip()

    toklist = separate_expression_into_tokens( expr )
    tree = TokenTree()
    tree.parse( toklist, 0 )

    return tree


def prune_token_tree( tree, prune_token ):
    """
    The 'prune_token' must be a function which takes a token as its only
    argument, and returns True if the given token should be pruned. Returns
    the number of modifications made to the tree.
    """
    cnt = 0

    # collapse repeated sub-expressions, such as "( ( foo ) )"
    if tree.numTokens() == 1 and isinstance( tree.getToken(0), TokenTree ):
        cnt += 1
        toks = list( tree.getToken(0).getTokens() )
        tree.setTokens( toks )

    toks = []
    ops = []

    for tok in tree.getTokens():
        if tok in _OPERATOR_LIST:
            ops.append( tok )
        else:
            if prune_token( tok ):
                cnt += 1
            else:
                toks.extend( ops )
                toks.append( tok )

                if isinstance( tok, TokenTree ):
                    cnt += prune_token_tree( tok, prune_token )

            del ops[:]

    trim_leading_binary_operator( toks )

    tree.setTokens( toks )

    return cnt


def trim_leading_binary_operator( toklist ):
    ""
    if toklist:
        if toklist[0] == 'and' or toklist[0] == 'or':
            toklist.pop( 0 )


_OPERATOR_LIST = ['(',')','not','and','or']

def convert_token_list_into_eval_string( toklist ):
    ""
    modified_toklist = []

    for tok in toklist:
        if tok in _OPERATOR_LIST:
            modified_toklist.append( tok )
        elif tok:
            modified_toklist.append( '(evalfunc("'+tok+'")==True)' )
        else:
            modified_toklist.append( 'False' )

    return ' '.join( modified_toklist )


def add_words_to_set( toklist, wordset ):
    ""
    if wordset != None:
        for tok in toklist:
            if tok and tok not in _OPERATOR_LIST:
                wordset.add( tok )


def separate_expression_into_tokens( expr ):
    ""
    toklist = []

    if expr.strip():

        for whitetok in expr.strip().split():
            for lptok in split_but_retain_separator( whitetok, '(' ):
                for rptok in split_but_retain_separator( lptok, ')' ):
                    rptok = rptok.strip()
                    if rptok == '!':
                        toklist.append( 'not' )
                    elif rptok:
                        if rptok.startswith('!'):
                            toklist.append( 'not' )
                            toklist.append( rptok[1:] )
                        else:
                            toklist.append( rptok )

    else:
        toklist.append( '' )

    return toklist


def split_but_retain_separator( expr, separator ):
    ""
    seplist = []

    splitlist = list( expr.split( separator ) )
    last_token = len(splitlist) - 1

    for i,tok in enumerate( splitlist ):
        seplist.append( tok )
        if i < last_token:
            seplist.append( separator )

    return seplist


def replace_forward_slashes( expr, negate=False ):
    """
    Convert a simple expression with forward slashes '/' to one with
    operator "or"s instead.

        "A/B" -> "A or B"
        "A/B/!C" -> "A or B or !C"
        "A/B" with negate=True -> "not A or not B"

    A ValueError is raised if both '/' and a paren is in the expression, or
    if '/' and the operators "and" or "or" are in the expression.
    """
    if '/' in expr:
        if '(' in expr or ')' in expr:
            raise ValueError( 'a "/" and parenthesis cannot be in the '
                              'same expression: '+repr(expr) )

        rtnL = []
        for tok in expr.strip().split('/'):
            tok = tok.strip()
            if tok:

                sL = tok.split()
                if 'and' in sL or 'or' in sL:
                    raise ValueError( 'a "/" and a boolean operator '
                                      '("and", "or") cannot be in the '
                                      'same expression: '+repr(expr) )

                if negate:
                    rtnL.append( 'not '+tok )
                else:
                    rtnL.append( tok )

        return ' or '.join( rtnL )

    elif negate:
        return 'not '+conditional_paren_wrap( expr )

    else:
        return expr


def join_expressions_with_AND( expr_list ):
    ""
    final = None

    for expr in expr_list:
        expr = expr.strip()

        if expr:
            if len(expr_list) > 1:
                expr = conditional_paren_wrap( expr )

            if final is None:
                final = expr
            else:
                final = final + ' and ' + expr

        else:
            # because empty expressions evaluate to False, the entire
            # expression will always evaluate to False
            return ''

    return final


def clean_up_word_expression( expr, negate=False ):
    ""
    ex = replace_forward_slashes( expr, negate )

    wx = WordExpression( ex )
    check_expression_words( wx.getWordList() )

    return ex


def clean_up_wildcard_expression( expr, negate=False ):
    ""
    ex = replace_forward_slashes( expr, negate )

    wx = WordExpression( ex )
    check_wildcard_expression_words( wx.getWordList() )

    return ex
