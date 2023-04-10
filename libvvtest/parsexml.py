#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import platform
import re

from .errors import TestSpecError
from . import xmlwrapper
from . import timehandler
from .testspec import TestSpec

from .paramset import ParameterSet

from .wordcheck import allowable_variable, allowable_word

from .parseutil import variable_expansion
from .parseutil import evaluate_testname_expr
from .parseutil import check_for_duplicate_parameter
from .parseutil import parse_to_word_expression
from .parseutil import evaluate_platform_expr
from .parseutil import evaluate_option_expr
from .parseutil import evaluate_parameter_expr


class XMLTestParser:

    def __init__(self, filepath,
                       rootpath=None,
                       platname=None,
                       optionlist=[],
                       force_params=None,
                       strict=False ):
        ""
        self.fpath = filepath

        self.root = rootpath or '.'

        self.platname = platname if platname else platform.uname()[0]
        self.optionlist = optionlist
        self.force = force_params

        fname = os.path.join( self.root, filepath )
        self.xmldoc = read_xml_file( fname, strict )

    def parseTestNames(self):
        ""
        return parse_test_names( self.xmldoc )

    def parseParameterSet(self, testname):
        ""
        return self.parse_parameterize( testname )

    def parseAnalyzeSpec(self, testname):
        ""
        return self.parse_analyze( testname )

    def makeTestInstance(self, testname, idtraits):
        ""
        return TestSpec( testname, self.root, self.fpath, idtraits )

    def parseTestInstance(self, tspec):
        """
        Can use a (nested) rtest element to cause another test to be defined.
            
            <rtest name="mytest">
              <rtest name="mytest_fast"/>
              ...
            </rtest>

        then use the testname="..." attribute to filter XML elements.

            <keywords testname="mytest_fast"> fast </keywords>
            <keywords testname="mytest"> long </keywords>

            <parameters testname="mytest" np="1 2 4 8 16 32 64 128 256 512"/>
            <parameters testname="mytest_fast" np="1 2 4 8"/>
            
            <execute testname="mytest_fast" name="exodiff"> ... </execute>

            <analyze testname="mytest">
              ...
            </analyze>
            <analyze testname="mytest_fast">
              ...
            </analyze>
        """
        self.parse_include_platform ( tspec )
        self.parse_keywords         ( tspec )
        self.parse_working_files    ( tspec )
        self.parse_timeouts         ( tspec )
        self.parse_execute_list     ( tspec )
        self.parse_baseline         ( tspec )

        tspec.setSpecificationForm( 'xml' )

    ############## end public interface #################

    def parse_parameterize(self, testname):
        """
        Parses the parameter settings for a test XML file.

          <parameterize paramname="value1 value2"/>
          <parameterize paramA="A1 A2"
                        paramB="B1 B2"/>
          <parameterize platforms="Linux or SunOS"
                        options="not dbg"
                        paramname="value1 value2"/>

        where paramname can be any string.  The second form creates combined
        parameters where the values are "zipped" together.  That is, paramA=A1
        and paramB=B1 then paramA=A2 and paramB=B2.  A separate test will NOT
        be created for the combination paramA=A1, paramB=B2, for example.
        """
        pset = ParameterSet()

        force_params = self.force or {}

        for nd in self.xmldoc.matchNodes(['parameterize$']):

            attrs = nd.getAttrs()

            pL = []
            skip = 0
            attrL = list( attrs.items() )
            attrL.sort()
            for n,v in attrL:

                if n in ["parameters","parameter"]:
                    raise TestSpecError( n + " attribute not allowed here, " + \
                                         "line " + str(nd.getLineNumber()) )

                isfa, istrue = self.attr_filter( n, v, testname, None,
                                                 str(nd.getLineNumber()) )
                if isfa:
                    if not istrue:
                        skip = 1
                        break
                    continue

                if not allowable_variable(n):
                    raise TestSpecError( 'bad parameter name: "' + n + '", line ' + \
                                         str(nd.getLineNumber()) )

                vals = v.split()
                if len(vals) == 0:
                    raise TestSpecError( "expected one or more values separated by " + \
                                         "spaces, line " + str(nd.getLineNumber()) )

                for val in vals:
                    if not allowable_word(val):
                        raise TestSpecError( 'bad parameter value: "' + val + '", line ' + \
                                             str(nd.getLineNumber()) )

                vals = force_params.get(n,vals)
                L = [ n ]
                L.extend( vals )

                for mL in pL:
                    if len(L) != len(mL):
                        raise TestSpecError( 'combined parameters must have the same ' + \
                                             'number of values, line ' + str(nd.getLineNumber()) )

                pL.append( L )

            if len(pL) > 0 and not skip:
                  # TODO: the parameter names should really be sorted here in order
                  #       to avoid duplicates if another parameterize comes along
                  #       with a different order of the same names
                  # the name(s) and each of the values are tuples
                  if len(pL) == 1:
                      L = pL[0]
                      check_for_duplicate_parameter( L[1:], nd.getLineNumber() )
                      pset.addParameter( L[0], L[1:] )
                  else:
                      L = [ list(T) for T in zip( *pL ) ]
                      check_for_duplicate_parameter( L[1:], nd.getLineNumber() )
                      pset.addParameters( L[0], L[1:] )

        return pset,None

    def parse_analyze(self, testname):
        """
        Parse analyze scripts that get run after all parameterized tests complete.

           <analyze keywords="..." parameters="..." platform="...">
             script contents that post processes test results
           </analyze>

        Returns true if the test specifies an analyze script.
        """
        analyze_spec = None

        ndL = self.xmldoc.matchNodes(['analyze$'])

        for nd in ndL:

            skip = 0
            for n,v in nd.getAttrs().items():

              if n in ["parameter","parameters"]:
                  raise TestSpecError( 'an <analyze> block cannot have a ' + \
                                       '"parameters=..." attribute: ' + \
                                       ', line ' + str(nd.getLineNumber()) )

              isfa, istrue = self.attr_filter( n, v, testname, None,
                                               str(nd.getLineNumber()) )
              if isfa and not istrue:
                  skip = 1
                  break

            if not skip:
                try:
                    content = str( nd.getContent() )
                except Exception:
                    raise TestSpecError( 'the content in an <analyze> block must be ' + \
                                         'ASCII characters, line ' + str(nd.getLineNumber()) )
                if analyze_spec == None:
                    analyze_spec = content.strip()
                else:
                    analyze_spec += os.linesep + content.strip()

        return analyze_spec

    def parse_include_platform(self, tspec):
        """
        Parse syntax that will filter out this test by platform or build option.

        Platform expressions and build options use word expressions.

           <include platforms="not SunOS and not Linux"/>
           <include options="not dbg and ( tridev or tri8 )"/>
           <include platforms="..." options="..."/>

        If both platform and option expressions are given, their results are
        ANDed together.  If more than one <include> block is given, each must
        result in True for the test to be included.

        For backward compatibility, allow the following.

           <include platforms="SunOS Linux"/>
        """
        testname = tspec.getName()

        platexprL = []
        optexprL = []

        for nd in self.xmldoc.matchNodes(['include$']):

            if nd.hasAttr( 'parameters' ) or nd.hasAttr( 'parameter' ):
                raise TestSpecError( 'the "parameters" attribute not allowed '
                                     'here, line ' + str(nd.getLineNumber()) )

            if not testname_ok( nd, testname ):
                # the <include> does not apply to this test name
                continue

            platexpr = nd.getAttr( 'platforms', nd.getAttr( 'platform', None ) )
            if platexpr is not None:
                parse_to_word_expression( platexpr.strip(), nd.getLineNumber() )
                platexprL.append( platexpr.strip() )

            optexpr = nd.getAttr( 'options', nd.getAttr( 'option', None ) )
            if optexpr and optexpr.strip():
                parse_to_word_expression( optexpr.strip(), nd.getLineNumber() )
                optexprL.append( optexpr.strip() )

        wx = parse_to_word_expression( platexprL )
        tspec.setEnablePlatformExpression( wx )

        wx = parse_to_word_expression( optexprL )
        tspec.setEnableOptionExpression( wx )

    def parse_keywords(self, tspec):
        """
        Parse the test keywords for the test XML file.

          <keywords> key1 key2 </keywords>
          <keywords testname="mytest"> key3 </keywords>

        Also includes the name="..." on <execute> blocks and the parameter names
        in <parameterize> blocks.
        """
        testname = tspec.getName()

        keys = []

        for nd in self.xmldoc.matchNodes(['keywords$']):
            if testname_ok( nd, testname ):
                for key in nd.getContent().split():
                    if allowable_word(key):
                        keys.append( key )
                    else:
                        raise TestSpecError( 'invalid keyword: "' + key + \
                                             '", line ' + str(nd.getLineNumber()) )

        tspec.setKeywordList( keys )

    def parse_working_files(self, tspec):
        """
        Parse the files to copy and soft link for the test XML file.

          <link_files> file1.C file2.F </link_files>
          <link_files linkname="f1.C f2.F"> file1.C file2.F </link_files>
          <copy_files platforms="SunOS"> file1.C file2.F </copy_files>
          <copy_files parameters="np=4" copyname="in4.exo"> in.exo </copy_files>

        For backward compatibility, "test_name" is accepted:

          <copy_files test_name="f1.C f2.F"> file1.C file2.F </copy_files>

        Deprecated:
          <glob_link> ${NAME}_data.txt </glob_link>
          <glob_copy> files_to_glob.* </glob_copy>

        Also here is parsing of test source files

          <source_files> file1 ${NAME}_*_globok.baseline <source_files>

        which are just files that are needed by (dependencies of) the test.
        """
        testname = tspec.getName()
        params = tspec.getParameters()

        cpfiles = []
        lnfiles = []

        for nd in self.xmldoc.matchNodes(["copy_files$"]):
            self.collect_filenames( nd, cpfiles, testname, params )

        for nd in self.xmldoc.matchNodes(["link_files$"]):
            self.collect_filenames( nd, lnfiles, testname, params )

        # include mirror_files for backward compatibility
        for nd in self.xmldoc.matchNodes(["mirror_files$"]):
            self.collect_filenames( nd, lnfiles, testname, params )

        for nd in self.xmldoc.matchNodes(["glob_link$"]):
            raise TestSpecError( "'glob_link' has been replaced by 'link_files'"
                                 " , line "+str(nd.getLineNumber()) )

        for nd in self.xmldoc.matchNodes(["glob_copy$"]):
            raise TestSpecError( "'glob_copy' has been replaced by 'copy_files'"
                                 " , line "+str(nd.getLineNumber()) )

        for src,dst in lnfiles:
            tspec.addLinkFile( src, dst )
        for src,dst in cpfiles:
            tspec.addCopyFile( src, dst )

        fL = []
        for nd in self.xmldoc.matchNodes(["source_files$"]):
            self.parse_source_files( nd, fL, testname, params )

        tspec.setSourceFiles( list( T[0] for T in fL ) )

    def parse_timeouts(self, tspec):
        """
        Parse test timeouts for the test XML file.

          <timeout value="120"/>
          <timeout platforms="SunOS" value="240"/>
          <timeout parameters="hsize=0.01" value="320"/>
        """
        testname = tspec.getName()
        params = tspec.getParameters()

        specL = []

        for nd in self.xmldoc.matchNodes(['timeout$']):

            skip = 0
            for n,v in nd.getAttrs().items():
                isfa, istrue = self.attr_filter( n, v, testname, params,
                                                 str(nd.getLineNumber()) )
                if isfa and not istrue:
                    skip = 1
                    break

            if not skip:

                to = None
                if nd.hasAttr('value'):
                    val = nd.getAttr("value").strip()

                    to,err = timehandler.parse_timeout_value( val )

                    if err:
                        raise TestSpecError( 'invalid timeout value: '+err )

                if to != None:
                    tspec.setTimeout( to )

    def parse_execute_list(self, tspec):
        """
        Parse the execute list for the test XML file.

          <execute> script language </execute>
          <execute name="aname"> arguments </execute>
          <execute platforms="SunOS" name="aname"> arguments </execute>
          <execute ifdef="ENVNAME"> arguments </execute>
          <execute expect="fail"> script </execute>

        If a name is given, the content is arguments to the named executable.
        Otherwise, the content is a script fragment.
        """
        testname = tspec.getName()
        params = tspec.getParameters()

        for nd in self.xmldoc.matchNodes(["execute$"]):

            skip = 0
            for n,v in nd.getAttrs().items():
                isfa, istrue = self.attr_filter( n, v, testname, params,
                                                 str(nd.getLineNumber()) )
                if isfa and not istrue:
                    skip = 1
                    break

            if nd.hasAttr('ifdef'):
                L = nd.getAttr('ifdef').split()
                for n in L:
                    if not allowable_variable(n):
                        raise TestSpecError( 'invalid environment variable name: "' + \
                                             n + '"' + ', line ' + str(nd.getLineNumber()) )
                for n in L:
                    if n not in os.environ:
                        skip = 1
                        break

            if not skip:

                xname = nd.getAttr('name', None)

                analyze = False
                if xname == None:
                    if nd.getAttr('analyze','').strip().lower() == 'yes':
                        analyze = True
                else:
                    if not xname or not allowable_word(xname):
                        raise TestSpecError( 'invalid name value: "' + xname + \
                                             '", line ' + str(nd.getLineNumber()) )

                xstatus = nd.getAttr( 'expect', None )

                content = nd.getContent()
                if content == None: content = ''
                else:               content = content.strip()

                if xname == None:
                    tspec.appendExecutionFragment( content, xstatus, analyze )
                else:
                    tspec.appendNamedExecutionFragment( xname, content, xstatus )

    def parse_baseline(self, tspec):
        """
        Parse the baseline files and scripts for the test XML file.

          <baseline file="$NAME.exo"/>
          <baseline file="$NAME.exo" destination="$NAME.base_exo"/>
          <baseline file="$NAME.exo $NAME.his"
                    destination="$NAME.base_exo $NAME.base_his"/>
          <baseline parameters="np=1" file="$NAME.exo"
                                      destination="$NAME.base_exo"/>

          <baseline>
            script language here
          </baseline>
        """
        testname = tspec.getName()
        params = tspec.getParameters()

        scriptfrag = ''

        for nd in self.xmldoc.matchNodes(['baseline$']):

            skip = 0
            for n,v in nd.getAttrs().items():
                isfa, istrue = self.attr_filter( n, v, testname, params,
                                                 str(nd.getLineNumber()) )
                if isfa and not istrue:
                    skip = 1
                    break

            if not skip:

                fL = []

                fname = nd.getAttr('file',None)
                if fname != None:
                    fname = fname.split()
                    fdest = nd.getAttr('destination',None)
                    if fdest == None:
                        for f in fname:
                            f = str(f)
                            fL.append( [f,f] )

                    else:
                        fdest = fdest.split()
                        if len(fname) != len(fdest):
                            raise TestSpecError( 'the number of file names in the ' + \
                             '"file" attribute must equal the number of names in ' + \
                             'the "destination" attribute (' + str(len(fdest)) + ' != ' + \
                             str(len(fname)) + '), line ' + str(nd.getLineNumber()) )

                        for i in range(len(fname)):
                            fL.append( [str(fname[i]), str(fdest[i])] )

                variable_expansion( testname,
                                    self.platname,
                                    params,
                                    fL )

                for f,d in fL:
                    tspec.addBaselineFile( str(f), str(d) )

                script = nd.getContent().strip()
                if script:
                    scriptfrag += '\n' + script

        if scriptfrag:
            tspec.setBaselineScript( scriptfrag )

    def collect_filenames(self, nd, flist, testname, params):
        """
        Helper function that parses file names in content with optional linkname
        attribute:

            <something platforms="SunOS"> file1.C file2.C </something>

        or

            <something linkname="file1_copy.dat file2_copy.dat">
              file1.C file2.C
            </something>

        Returns a list of (source filename, link filename).
        """
        fileL = nd.getContent().split()
        if len(fileL) > 0:

            skip = 0
            for n,v in nd.getAttrs().items():
                isfa, istrue = self.attr_filter( n, v, testname, params,
                                                 str(nd.getLineNumber()) )
                if isfa and not istrue:
                    skip = 1
                    break

            if not skip:

                fL = []
                tnames = nd.getAttr( 'linkname',
                         nd.getAttr('copyname',
                         nd.getAttr('test_name',None) ) )
                if tnames != None:

                    tnames = tnames.split()
                    if len(tnames) != len(fileL):
                        raise TestSpecError( 'the number of file names in the ' + \
                           '"linkname" attribute must equal the number of names in ' + \
                           'the content (' + str(len(tnames)) + ' != ' + str(len(fileL)) + \
                           '), line ' + str(nd.getLineNumber()) )
                    for i in range(len(fileL)):
                        if os.path.isabs(fileL[i]) or os.path.isabs(tnames[i]):
                            raise TestSpecError( 'file names cannot be absolute paths, ' + \
                                                 'line ' + str(nd.getLineNumber()) )
                        fL.append( [str(fileL[i]), str(tnames[i])] )

                else:
                    for f in fileL:
                        if os.path.isabs(f):
                            raise TestSpecError( 'file names cannot be absolute paths, ' + \
                                                 'line ' + str(nd.getLineNumber()) )
                        fL.append( [str(f), None] )

                variable_expansion( testname,
                                    self.platname,
                                    params,
                                    fL )

                flist.extend(fL)

        else:
            raise TestSpecError( 'expected a list of file names as content' + \
                                 ', line ' + str(nd.getLineNumber()) )

    def parse_source_files(self, nd, flist, testname, params):
        """
          <source_files> ${NAME}_*.base_exo </source_files>

        Appends (source filename, None) to the given 'flist'.
        """
        globL = nd.getContent().strip().split()
        if len(globL) > 0:

            for n,v in nd.getAttrs().items():
                isfa, istrue = self.attr_filter( n, v, testname, params,
                                                 str(nd.getLineNumber()) )
                if isfa:
                    raise TestSpecError( 'filter attributes not allowed here' + \
                                         ', line ' + str(nd.getLineNumber()) )

            # first, substitute variables into the file names
            variable_expansion( testname,
                                self.platname,
                                params,
                                globL )

            for fn in globL:
                flist.append( [str(fn),None] )

        else:
            raise TestSpecError( 'expected a list of file names as content' + \
                               '  , line ' + str(nd.getLineNumber()) )

    def attr_filter(self, attrname, attrvalue, testname, paramD, lineno):
        """
        Checks the attribute name for a filtering attributes.  Returns a pair of
        boolean values, (is filter, filter result).  The first is whether the
        attribute name is a filtering attribute, and if so, the second value is
        true/false depending on the result of applying the filter.
        """
        try:

            if attrname == "testname":
                return True, evaluate_testname_expr( testname, attrvalue )

            elif attrname in ["platform","platforms"]:
                return True, evaluate_platform_expr( self.platname, attrvalue )

            elif attrname in ["keyword","keywords","not_keyword","not_keywords"]:
                raise TestSpecError( attrname + " attribute not allowed here, " + \
                                     "line " + str(lineno) )

            elif attrname in ["option","options"]:
                return True, evaluate_option_expr( self.optionlist, attrvalue )

            elif attrname in ["parameter","parameters"]:
                return True, evaluate_parameter_expr( paramD, attrvalue )

        except ValueError as e:
            raise TestSpecError( "bad " + attrname + " expression, line " + \
                                 lineno + ": " + str(e) )

        return False, False


def read_xml_file( filename, strict=False ):
    ""
    docreader = xmlwrapper.XmlDocReader()

    try:
        filedoc = docreader.readDoc( filename )

    except xmlwrapper.XmlError:
        if strict or appears_to_be_a_test_file( filename ):
            raise TestSpecError( str( sys.exc_info()[1] ) )
        return None

    else:
        return filedoc


def appears_to_be_a_test_file( filename ):
    ""
    with open( filename, 'rt' ) as fp:
        top = fp.read( 512 )

    for line in re.split( r'[\n\r]+', top ):
        if line.strip().startswith( '<rtest' ):
            return True

    return False


def testname_ok( xmlnode, tname ):
    ""
    ok = True

    tval = xmlnode.getAttr( 'testname', None )
    if tval is not None:
        try:
            if not evaluate_testname_expr( tname, tval ):
                ok = False
        except Exception as e:
            raise TestSpecError( 'bad testname expression: ' + repr(tval) + \
                                 ', line ' + str(xmlnode.getLineNumber()) + \
                                 ': '+str(e) )

    return ok


def parse_test_names( filedoc ):
    """
    Determine the test name and check for validity.  If this XML file is not
    an "rtest" then returns None.  Otherwise returns a list of test names.
    """
    if filedoc == None or filedoc.getName() != "rtest":
        return []

    # determine the test name

    name = filedoc.getAttr('name', '').strip()
    if not name or not allowable_word(name):
        raise TestSpecError( 'missing or invalid test name attribute, ' + \
                             'line ' + str(filedoc.getLineNumber()) )

    L = [ name ]
    for xnd in filedoc.matchNodes( ['rtest'] ):
        nm = xnd.getAttr('name', '').strip()
        if not nm or not allowable_word(nm):
            raise TestSpecError( 'missing or invalid test name attribute, ' + \
                                 'line ' + str(xnd.getLineNumber()) )
        L.append( nm )

    return L
