#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os
import platform

from .errors import TestSpecError
from .staging import mark_staged_tests
from .parsevvt import ScriptTestParser, add_generator_dependencies


class TestCreator:

    def __init__(self, idflags={},
                       platname=None,
                       optionlist=[],
                       force_params=None ):
        """
        The 'loc' is a Locator object.
        If 'force_params' is not None, then any parameters in a test that
        are in the 'force_params' dictionary will have their values replaced
        for that parameter name.
        """
        self.idflags = idflags
        self.platname = platname or platform.uname()[0]
        self.optionlist = optionlist
        self.force_params = force_params

    def getValidFileExtensions(self, specform=None):
        """
        Returns the list of test file extensions that this instance of vvtest
        will recognize and parse. If given, the entries in 'specform' narrow
        down the list of extensions.

        The default extension (when no 'specform' is given) is just ".vvt".

        This mechanism was valuable when there was an "xml" test form supported
        in vvtest, but now is a placehholder in the unlikely event that the
        ASC Sierra project decides to adopt vvtest and their existing test
        format must be supported.
        """
        if specform:
            return map_spec_form_to_extensions( specform )
        else:
            return ['.vvt']

    def fromFile(self, relpath, rootpath=None):
        """
        The 'rootpath' is the top directory of the file scan.  The 'relpath' is
        the name of the test file relative to 'rootpath' (it must not be an
        absolute path).  

        Returns a list of TestSpec objects, including a "parent" test if needed.
        """
        assert not os.path.isabs( relpath )

        maker = self.create_test_maker( relpath, rootpath, False )

        tests = maker.createTests()

        return tests

    def reparse(self, tspec):
        """
        Parses the test source file and resets the test specifications. The
        test name is not changed, and the parameters in the test source file
        are not considered.  Instead, the parameters already defined in the
        test object are used.

        A TestSpecError is raised if the file has an invalid specification.
        """
        maker = self.create_test_maker( tspec.getFilepath(),
                                        tspec.getRootpath(),
                                        strict=True )
        maker.reparseTest( tspec )

    def create_test_maker(self, relpath, rootpath, strict):
        """
        When there were two different supported test file formats, this
        function would branch and create an object for parsing each type.
        It would create the point of abstraction for the format parsing.
        """
        form = map_extension_to_spec_form( relpath )

        if form == 'script':
            parser = ScriptTestParser( relpath, rootpath,
                                       self.platname,
                                       self.optionlist,
                                       self.force_params )
        else:
            raise Exception( "Internal error: unknown test file format: "+str(form) )

        maker = TestMaker( parser, self.idflags )

        return maker


def map_spec_form_to_extensions( specforms ):
    """
    This and the function map_extension_to_spec_form() go together.

    This one returns the valid file extension(s) for the spec form names
    in the 'specforms' list.
    """
    ext = set()

    for form in specforms:
        if form == 'vvt':
            ext.add( '.vvt' )

    return list( ext )


def map_extension_to_spec_form( filepath ):
    """
    There used to be two test file formats, and this function mapped the
    file extension to a string called the test "form".
    """
    ext = os.path.splitext( filepath )[1]
    if ext == '.vvt':
        return 'script'


class TestMaker:

    def __init__(self, parser, idflags={}):
        ""
        self.parser = parser
        self.idflags = idflags

    def createTests(self):
        """
        Create the test instances from the test file.

        The parser can indicate that the given file is not a valid file format
        by returning an empty list from parseTestNames().
        """
        nameL = self.parser.parseTestNames()

        self.tests = []
        for tname in nameL:
            L = self.create_test_list( tname )
            self.tests.extend( L )

        return self.tests

    def reparseTest(self, tspec):
        ""
        # run through the test name logic to check validity
        self.parser.parseTestNames()

        tname = tspec.getName()

        old_pset = tspec.getParameterSet()
        new_pset,depmap = self.parser.parseParameterSet( tname )
        new_pset.intersectionFilter( old_pset.getInstances() )
        tspec.setParameterSet( new_pset )

        if new_pset.getStagedGroup():
            mark_staged_tests( new_pset, [ tspec ] )

        if tspec.isAnalyze():
            analyze_spec = self.parser.parseAnalyzeSpec( tname )
            tspec.setAnalyzeScript( analyze_spec )

        self.parser.parseTestInstance( tspec )
        add_generator_dependencies( tspec, depmap )

    def create_test_list(self, tname):
        ""
        pset,depmap = self.parser.parseParameterSet( tname )

        testL = self.generate_test_objects( tname, pset )

        mark_staged_tests( pset, testL )

        analyze_spec = self.parser.parseAnalyzeSpec( tname )
        self.check_add_analyze_test( analyze_spec, tname, pset, testL )

        for t in testL:
            self.parser.parseTestInstance( t )
            add_generator_dependencies( t, depmap )

        return testL

    def check_add_analyze_test(self, analyze_spec, tname, pset, testL):
        ""
        if analyze_spec:
            parent = self.make_analyze_test( analyze_spec, tname, pset )
            testL.append( parent )

    def make_analyze_test(self, analyze_spec, testname, paramset):
        ""
        if len( paramset.getParameters() ) == 0:
            raise TestSpecError( 'an analyze requires at least one ' + \
                                 'parameter to be defined' )

        idt = make_idtraits( self.idflags, [] )
        parent = self.parser.makeTestInstance( testname, idt )

        parent.setIsAnalyze()
        parent.setParameterSet( paramset )
        parent.setAnalyzeScript( analyze_spec )

        return parent

    def generate_test_objects(self, tname, paramset):
        ""
        testL = []

        if len( paramset.getParameters() ) == 0:
            idt = make_idtraits( self.idflags, [] )
            t = self.parser.makeTestInstance( tname, idt )
            testL.append(t)

        else:
            suppress = get_suppressed_parameters( paramset, self.idflags )

            # take a cartesian product of all the parameter values
            for pdict in paramset.getInstances():
                idt = make_idtraits( self.idflags, suppress )
                t = self.parser.makeTestInstance( tname, idt )
                t.setParameters( pdict )
                t.setParameterSet( paramset )
                testL.append(t)

        return testL


def get_suppressed_parameters( paramset, idflags ):
    ""
    if 'minxdirs' in idflags:

        keyvals = {}
        for params in paramset.getInstances():
            for n,v in params.items():
                if n in keyvals:
                    keyvals[n].add( v )
                else:
                    keyvals[n] = set([v])

        staged = paramset.getStagedGroup()
        if staged:
            exclude = staged[0]
        else:
            exclude = []

        suppress = []
        for n,vals in keyvals.items():
            if len(vals) == 1 and n not in exclude:
                suppress.append( n )

        return suppress

    else:
        return []


def make_idtraits( idflags, suppressed ):
    """
    idtraits are almost a copy of the idflags dict, except the minxdirs
    is handled specially
    """
    if 'minxdirs' in idflags:
        idt = dict( idflags )
        idt['minxdirs'] = suppressed or []
        return idt
    else:
        return idflags
