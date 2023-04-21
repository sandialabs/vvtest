#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

'''
  The xmlwrapper module provides a uniform and simplified interface for
XML parsing.  Construct an XmlDocReader class, then call its readDoc() method,
which returns a root XmlNode object.
'''

import sys
sys.dont_write_bytecode = True
sys.excepthook = sys.__excepthook__
import os
import re

# Got the line numbering enhancement to ElementTree from
# https://stackoverflow.com/questions/6949395/
#   is-there-a-way-to-get-a-line-number-from-an-elementtree-element

sys.modules['_elementtree'] = None  # prevent possible C language override
import xml.etree.ElementTree as ET


class XmlError(Exception):
    def __init__(self, msg=""): self.msg = "XML: " + msg
    def __str__(self): return self.msg


class XmlNode:

    def __init__(self, name, line_number, attr_dict):
        self.name = name
        self.line_no = line_number
        self.attrs = attr_dict
        self.content = ''
        self.parent = None
        self.kids = []

    def getName(self):
        "Returns the name of this XML block (the begin and end tag name)."
        return self.name

    def getLineNumber(self):
        "Returns the line number of the start of this XML block."
        return self.line_no

    def getAttrs(self):
        "Returns the dictionary of attribute names to attribute values."
        return self.attrs

    def hasAttr(self, name):
        "Returns true if the XML node has an attribute with the given name."
        return name in self.attrs

    def getAttr(self, name, *args):
        """
        Returns the value of the attribute with the given name.  If the
        attribute does not exist and a default value is not given, a KeyError
        exception is thrown.
        """
        if len(args) > 0:
          return self.attrs.get( name, args[0] )
        return self.attrs[name]

    def getContent(self):
        "Returns the string of accumulated content."
        return self.content

    def getParent(self):
        "Returns the parent XmlNode of this node, or None if this is root."
        return self.parent

    def getSubNodes(self):
        "Returns the list of XmlNode children to this XmlNode."
        return self.kids

    def subNode(self, name):
        """
        Returns the child node with the given name.  Raises a LookupError
        exception if a child with the given name does not exist.
        """
        for nd in self.kids:
          if nd.name == name:
            return nd
        raise LookupError( 'name not found "' + name + '"' )

    def matchNodes(self, node_path_list):
        """
        Search and return all sub nodes which match the node path.
        Each element of the list is matched against sub node names of
        increasing depth.  Regular expression pattern matching is used
        for each name.

        For example, the list ['sub.*', 'level2_name'] will match all
        nodes whose first level child name matches 'sub.*' and whose second
        level child matches 'level2_name'.
        """
        if type(node_path_list) != type([]):
          raise TypeError( 'argument not a list: "'+str(node_path_list)+'"' )

        nodes = [self,]

        for pat in node_path_list:
          cpat = re.compile(pat)
          new_nodes = []
          for nd in nodes:
            for kid in nd.getSubNodes():
              if cpat.match(kid.name):
                new_nodes.append(kid)
          nodes = new_nodes
          if len(nodes) == 0:
            break

        return nodes

    def toString(self, recursive=True, indent=""):
        """
        Writes this XML node into string form.  If the recursive flag is true,
        writes all subnodes recursively too.  The indent string is prepended
        to each line.  Returns the total string.
        """
        s = indent + '<' + self.name
        for (n,v) in self.attrs.items():
          s = s + ' ' + n + '="' + v + '"'
        c = self.content.strip()
        if c or len(self.kids) > 0:
          s = s + '>\n'
          if c: s = s + indent + "  " + c + '\n'
          if recursive:
            for nd in self.kids:
              s = s + nd.toString(recursive,indent=indent+"  ")
          s = s + indent + '</' + self.name + '>\n'
        else:
          s = s + '/>\n'

        return s

    ########### creation methods

    def appendContent(self, more):
        self.content = self.content + more

    def addSubNode(self, nd):
        self.kids.append( nd )


def printXmlNode(nd, indent=''):
    if nd.name != None:
      print( indent + nd.name + str(nd.line_no) + ':' + str(nd.attrs) + nd.content )
      for kid in nd.kids:
        printXmlNode( kid, indent + '  ' )


#############################################################################

class XmlDocReader:
    """
    Construct an XmlDocReader, call its readDoc(filename) method, then
    access the resulting DOM structure using XmlNode methods.  If more than
    one document must be parsed, it is slightly faster to repeatedly call the
    readDoc method rather than constructing a new XmlDocReader each time.
    """
    
    def __init__(self):
        """
        The constructor determines the error class used by ElementTree.parse().
        """
        try:
            # this succeeds with python 2
            import StringIO
            class_StringIO = StringIO.StringIO
        except Exception:
            # this succeeds with python 3
            import io
            class_StringIO = io.StringIO

        # create some XML with an error
        sio = class_StringIO( "<foo> <bar> </foo>\n" )
        try:
            ET.parse( sio )
        except Exception:
            self.ET_exc_class = sys.exc_info()[0]
        else:
            # something is wrong; the drawback to this fallback is that you
            # cannot distinguish an XML error from other errors
            self.ET_exc_class = Exception

    def readDoc(self, filename):
        """
        Open the XML file and read its contents into a tree of XmlNode objects.
        XML errors raise an XmlError exception.
        """
        try:
            doc = ET.parse( filename, parser=LineNumberingParser() )
        except self.ET_exc_class:
            raise XmlError( str(sys.exc_info()[1]) )

        rootnode = recurse_construct_ET_to_XmlNode( None, doc.getroot() )

        return rootnode


class LineNumberingParser(ET.XMLParser):

    # this is for Python 2
    def _start_list(self, *args, **kwargs):
        element = ET.XMLParser._start_list( self, *args, **kwargs )
        if hasattr( self, 'parser' ):
            element._start_line_number = self.parser.CurrentLineNumber
        else:
            element._start_line_number = self._parser.CurrentLineNumber
        return element

    # this is for Python 3
    def _start(self, *args, **kwargs):
        element = ET.XMLParser._start( self, *args, **kwargs )
        element._start_line_number = self.parser.CurrentLineNumber
        return element


def recurse_construct_ET_to_XmlNode( parent_wrapper_node, ET_node ):
    """
    """
    name = ET_node.tag
    lineno = ET_node._start_line_number

    attrs = {}
    for k,v in ET_node.items():
        attrs[k] = v

    newnd = XmlNode( name, lineno, attrs )

    if ET_node.text:
        newnd.appendContent( ET_node.text )

    if parent_wrapper_node != None:
        newnd.parent = parent_wrapper_node

    for ET_subnd in ET_node:
        if ET_subnd.tail:
            newnd.appendContent( ET_subnd.tail )
        subnd = recurse_construct_ET_to_XmlNode( newnd, ET_subnd )
        newnd.addSubNode( subnd )

    return newnd
