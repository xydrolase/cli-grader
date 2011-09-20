#!/usr/bin/env python

import sys

roster = sys.argv[1]
scores = sys.argv[2]

records = set([x.split(',')[0] for x in open(scores).readlines()[1:]])
stu_ids = set([x.split('\t')[0] for x in open(roster).readlines()])

students = open(roster).readlines()

missing = [students[int(id)-1] for id in stu_ids - records]

print 'Student who didn\'t turn in homework/exam papers:'
print '\n'.join(missing)
