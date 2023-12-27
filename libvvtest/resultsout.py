#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.


class ResultsWriters:

    def __init__(self):
        ""
        self.writers = []

    def addWriter(self, writer):
        ""
        self.writers.append( writer )

    def prerun(self, verbosity):
        ""
        for wr in self.writers:
            if hasattr( wr, 'prerun' ):
                wr.prerun( verbosity )

    def midrun(self):
        ""
        for wr in self.writers:
            if hasattr( wr, 'midrun' ):
                wr.midrun()

    def postrun(self):
        ""
        for wr in self.writers:
            if hasattr( wr, 'postrun' ):
                wr.postrun()

    def info(self):
        ""
        for wr in self.writers:
            if hasattr( wr, 'info' ):
                wr.info()
