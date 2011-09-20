#!/usr/bin/env python

import sys
import readline
import re

def get_index(max_index):
    while True:
        try:
            index = int(raw_input('> COLUMN: ')) - 1
        except ValueError:
            continue

        if index <= 0 or index >= max_index:
            continue

        return index

def select_columns(grade, sheet):
    from_col = 0
    to_col = 0
    print '[SCORE COLUMN TO MERGE FROM]'
    print '\n'.join(map(lambda x: "%d. %s" % (x+1, 
        grade[x].replace('"', '')), range(len(grade))))
    from_col = get_index(len(grade))
    print '> ORIGIN:', grade[from_col].strip(), 'SELECTED.'

    print '[SHEET COLUMN TO MERGE INTO]'
    print '\n'.join(map(lambda x: "%d. %s" % (x+1, 
        sheet[x].replace('"', '')), range(len(sheet))))
    to_col = get_index(len(sheet))
    print '> TARGET:', sheet[to_col].strip(), 'SELECTED.'

    return from_col, to_col

def merge(grade, g_col, sheet, s_col):
    hit_cnt = 0
    miss_cnt = 0
    for x in range(len(sheet)):
        row = sheet[x]
        hit_flag = False
        for record in grade:
            name = record[2].replace('"', '')
            components = re.split('-| ', 
                    row[0].replace('"', '').upper()) + \
                re.split('-| ', row[1].replace('"', '').upper())
            
            if not filter(lambda x: not x, 
                [re.compile(comp).search(name) 
                    for comp in components]):

                print '[HIT]', ' '.join(components), '->', name, ' = ', record[g_col]
                hit_cnt += 1

                row[s_col] = str(int(float(record[g_col])))
                hit_flag = True
                break

        if not hit_flag:
            print '[MISS]', ' '.join(components) 
            miss_cnt += 1
            row[s_col] = '0'

    print 'HIT:', hit_cnt, 'MISS:', miss_cnt

    return sheet

def main():
    if len(sys.argv) != 3:
        print 'Usage: %s score_report grading_sheet' % sys.argv[0]
        sys.exit(1)

    sheet = [x.strip().split(',') 
            for x in open(sys.argv[2]).readlines()]
    grade = [x.strip().split(',') 
            for x in open(sys.argv[1]).readlines()]

    sheet_entries = sheet[0]
    grade_entries = grade[0]

    from_col, to_col = select_columns(grade_entries, sheet_entries)
    merged_sheet = merge(grade[1:], from_col, 
            sheet[1:], to_col)

    fd = open('final_%s' % sys.argv[2], 'w+')
    fd.write(','.join(sheet_entries) + '\n')
    fd.write('\n'.join([','.join(row) for row in merged_sheet]))
    fd.close()

if __name__ == "__main__":
    main()
