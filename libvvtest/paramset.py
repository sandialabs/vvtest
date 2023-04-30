#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.


class ParameterSet:
    """
    A set of parameter names mapped to their values.  Such as

        paramA = [ 'Aval1', 'Aval2', ... ]
        paramB = [ 'Bval1', 'Bval2', ... ]
        ...

    A set of instances is the cartesian product of the values (an instance
    is a dictionary of param_name=param_value).  Such as

        { 'paramA':'Aval1', 'paramB':'Bval1', ... }
        { 'paramA':'Aval1', 'paramB':'Bval2', ... }
        { 'paramA':'Aval2', 'paramB':'Bval1', ... }
        { 'paramA':'Aval2', 'paramB':'Bval2', ... }
        ...

    Parameter names can be grouped, such as

        paramC,paramD = [ ('Cval1','Dval1'), ('Cval2','Dval2'), ... ]

    The cartesian product does NOT apply to values within a group (the values
    are taken verbatim).
    """

    def __init__(self):
        ""
        self.params = {}
        self.type_map = {}
        self.staged = None
        self.instances = []

    def addParameters(self, names, values_list, staged=False):
        """
        Such as
            ['param_name'], [ ['value1'], ['value2'] ]
        or
            ('paramA','paramB'), [ ['A1','B1'], ['A2','B2'] ]
        """
        self.params[ tuple(names) ] = list(values_list)
        if staged:
            self.staged = ( list( names ), list( values_list ) )
        self._constructInstances()

    def addParameter(self, name, values):
        """
        Convenience function for the case of a single parameter name.
        """
        self.addParameters( [name], [ [v] for v in values ] )

    def setParameterTypeMap(self, type_map):
        """
        Such as { 'np': int, 'dx': float }.
        """
        self.type_map = dict( type_map )

    def getParameterTypeMap(self):
        ""
        return self.type_map

    def getStagedGroup(self):
        ""
        if self.staged:
            return self.staged[0], self.staged[1]  # names list, values list
        return None

    def applyParamFilter(self, param_filter_func):
        """
        Filters down the set of parameter instances, which is reflected in
        the getInstances() method afterwards. The param_filter_func() function
        is called with a parameter dict instance, and should return True to
        retain that instance or False to remove it.
        """
        self._constructInstances()

        newL = []
        for instD in self.instances:
            if param_filter_func( instD ):
                newL.append( instD )

        self.instances = newL

    def intersectionFilter(self, params_list):
        """
        Restricts the parameter instances to those that are in 'params_list',
        a list of parameter name to value dictionaries.
        """
        self.applyParamFilter( lambda pD: pD in params_list )

    def getInstances(self):
        """
        Return the list of dictionary instances, which contains all
        combinations of the parameter values (the cartesian product).
        """
        return self.instances

    def getParameters(self, typed=False, serializable=False):
        """
        Returns the filtered parameters in a dictionary, such as
            {
              ('paramA',) : [ ['a1'], ['a2'], ... ] ],
              ('paramB', 'paramC') : [ ['b1','c1'], ['b2','c2'], ... ] ],
            }

        if ``serializable``, then the keys of the returned mappings will be
        strings formed as:
            ('key1', 'key2', ..., 'key3') -> 'key1,key2,...,key3'
        """
        instL = self.getInstances()
        filtered_params = {}

        for nameT,valuesL in self.params.items():

            L = []
            for valL in valuesL:
                if contains_parameter_name_value( instL, nameT, valL ):
                    if typed:
                        valL = apply_value_types( self.type_map, nameT, valL )
                    L.append( valL )

            key = nameT if not serializable else  ",".join([str(_) for _ in nameT])
            filtered_params[ key ] = L

        return filtered_params

    def isEmpty(self):
        """
        Returns True if there are no parameter instances left after filtering.
        """
        return len( self.instances ) == 0

    def _constructInstances(self):
        ""
        if len(self.params) == 0:
            self.instances = []

        else:
            instL = [ {} ]  # a seed for the accumulation algorithm
            for names,values in self.params.items():
                instL = accumulate_parameter_group_list( instL, names, values )
            self.instances = instL


###########################################################################

def apply_value_types( type_map, nameT, valL ):
    ""
    newvalL = []
    for i,name in enumerate(nameT):
        if name in type_map:
            newvalL.append( type_map[name]( valL[i] ) )
        else:
            newvalL.append( valL[i] )

    return newvalL


def contains_parameter_name_value( instances, nameT, valL ):
    """
    Returns true if the given parameter names are equal to the given values
    for at least one instance dictionary in the 'instances' list.
    """
    ok = False
    for D in instances:
        cnt = 0
        for n,v in zip( nameT, valL ):
            if D[n] == v:
                cnt += 1
        if cnt == len(nameT):
            ok = True
            break

    return ok


def accumulate_parameter_group_list( Dlist, names, values_list ):
    """
    Performs a cartesian product with an existing list of dictionaries and a
    new name=value set.  For example, if

        Dlist = [ {'A':'a1'} ]
        names = ('B',)
        values_list = [ ['b1'], ['b2'] ]

    then this list is returned

        [ {'A':'a1', 'B':'b1'},
          {'A':'a1', 'B':'b2'} ]

    An example using a group:

        Dlist = [ {'A':'a1'}, {'A':'a2'} ]
        names = ('B','C')
        values_list = [ ['b1','c1'], ['b2','c2'] ]

    would yield

        [ {'A':'a1', 'B':'b1', 'C':'c1'},
          {'A':'a1', 'B':'b2', 'C':'c2'},
          {'A':'a2', 'B':'b1', 'C':'c1'},
          {'A':'a2', 'B':'b2', 'C':'c2'} ]
    """
    newL = []
    for values in values_list:
        L = add_parameter_group_to_list_of_dicts( Dlist, names, values )
        newL.extend( L )
    return newL


def add_parameter_group_to_list_of_dicts( Dlist, names, values ):
    """
    Copies and returns the given list of dictionaries but with
    names[0]=values[0] and names[1]=values[1] etc added to each.
    """
    assert len(names) == len(values)
    N = len(names)

    new_Dlist = []

    for D in Dlist:
        newD = D.copy()
        for i in range(N):
            newD[ names[i] ] = values[i]
        new_Dlist.append( newD )

    return new_Dlist
