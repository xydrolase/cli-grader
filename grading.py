#!/usr/bin/env python

import sys
import os
import re
import curses
import readline
import cPickle as pickle
from math import ceil

MODE_RUBRIC, MODE_NAME, MODE_GRADE, MODE_COMMAND = 1,2,3, 4
COLOR_PAIR_PROMPT, COLOR_PAIR_NAME, COLOR_PAIR_CMD = 1,2,3
ROW_NAME, ROW_RUBRIC, ROW_GRADE, ROW_LIST = 0,1,2,3

BONUS_PENALTY_CMDS = (ord('+'), ord('-'))

REGEX_BNP = re.compile(r'^([+|-])(\d+)(\%?)$')

class Grading:
    def __init__(self, subject):
        self.subject = subject
        self.records = []
        self.buffer = [] 
        self.command = []
        self.rubric = []
        self.name_offset = len('NAME: ') - 1
        self.mode = MODE_RUBRIC
        self.selected_index = -1
        self.bonus_penalty = []

        self.matched_indices = []
        self.load_roster()
        self.load_cache()
        self.start()

    def start(self):
        if not self.rubric:
            self.get_rubric()
        self.init_screen()
        self.show_rubric()
        self.max_score = sum(self.rubric)
        if self.records:
            self.show_status(
                '[CACHE] %d entries recovered from local cache. (!! to swipe)' % \
                        len(self.records))
                
        self.stdscr.addstr(ROW_NAME, 0, "NAME: ", curses.color_pair(1))

    def init_screen(self):
        self.stdscr = curses.initscr()
        curses.start_color()
        curses.init_pair(COLOR_PAIR_PROMPT,
                curses.COLOR_RED, curses.COLOR_WHITE)
        curses.init_pair(COLOR_PAIR_NAME, 
                curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(COLOR_PAIR_CMD, 
                curses.COLOR_GREEN, curses.COLOR_WHITE)
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(1)

        self.ROW_MAX, self.COLUMN_MAX = map(lambda x: x-1,
                list(self.stdscr.getmaxyx()))

    def destroy_screen(self):
        curses.nocbreak()
        self.stdscr.keypad(0)
        curses.echo(0)
        curses.endwin()

    def get_rubric(self):
        while True:
            raw_rubric = raw_input('RUBRIC: ')
            if all(map(lambda x: x.isdigit(),
                    raw_rubric.split(' '))):
                self.rubric = map(int, raw_rubric.split(' '))
                self.num_questions = len(self.rubric)
                self.grade_spaces = map(
                        lambda x: len(str(x)) + 3,
                        self.rubric)
                self.mode = MODE_NAME
                break

    def grade_keypress(self, raw_ch):
        if raw_ch == curses.KEY_BACKSPACE:
            if self.buffer:
                ch = self.buffer.pop()
                if ch == ' ' and self.buffer:
                    while True:
                        self.buffer.pop()
                        if not self.buffer or self.buffer[-1] == ' ':
                            break

        if raw_ch < 256:
            ch = chr(raw_ch)
            if ch.isdigit():
                self.buffer.append(ch)
            elif ch == '.':
                if not self.buffer or \
                        self.buffer[-1] != '.':
                    self.buffer.append(ch)
            elif ch == ' ':
                if self.buffer and self.buffer[-1].isdigit():
                    self.buffer.append(' ')
            elif ch == '\n':
                grades = map(float, 
                        ''.join(self.buffer).strip().split(' '))
                if len(grades) == len(self.rubric):
                    total_grade = self.real_score(self.selected_index, 
                            sum(grades))
                    max_grade = sum(self.rubric)

                    self.show_grade(color=COLOR_PAIR_PROMPT)
                    self.stdscr.addstr("TOTAL: %d/%d" % \
                            (total_grade, max_grade), 
                            curses.color_pair(COLOR_PAIR_PROMPT)
                            )
                    
                    self.record_grade(grades)
                    self.cache()
                    self.set_mode(MODE_NAME)
                    return

        self.parse_grade()
        self.show_grade()

    def show_status(self, status, color=COLOR_PAIR_NAME):
        yx = self.stdscr.getyx()

        self.clear_lines(self.ROW_MAX, 1)
        self.stdscr.addstr(self.ROW_MAX, 0, status,
            curses.color_pair(color))

        self.stdscr.move(*yx)

    def record_grade(self, grades):
        if self.selected_index != -1 and \
                self.selected_index < len(self.namelist):
            self.records.append([self.selected_index] + grades)
            # Remove current index from the remaining search list to gurantee
            # that we only record grades for every student once.
            self.remain_indices.remove(self.selected_index)

            self.show_status("[RECORDED] %s: %d/%d // [%d/%d]" % (
                self.namelist[self.selected_index],
                self.real_score(self.selected_index, sum(grades)), 
                sum(self.rubric),
                len(self.records), len(self.namelist)))

    def name_keypress(self, raw_ch):
        """Handle keypress events under the NAME mode where the user is
        expected to enter the name of students."""
        if raw_ch == curses.KEY_BACKSPACE:
            if self.buffer:
                self.stdscr.delch(0, self.name_offset+len(self.buffer))
                self.buffer.pop()

        if raw_ch < 256:
            ch = chr(raw_ch)

            if ch.isalpha() or ch in ["'", ' ']:
                self.buffer.append(ch)
                self.stdscr.addch(raw_ch)

            elif (ch == '\n' and self.matched_indices) or \
                    (ch.isdigit() and self.matched_indices and \
                    int(ch) <= len(self.matched_indices)):

                # If user presses enter or specify a number,
                # select the student and proceed to SCORE mode.

                if ch == '\n':
                    idx = 0
                else:
                    idx = int(ch) - 1

                self.selected_index = self.matched_indices[idx]
                self.stdscr.addstr(0, 0, 'NAME: %s' % \
                        self.namelist[self.matched_indices[idx]],
                        curses.color_pair(1))

                self.set_mode(MODE_GRADE)

                return

        if len(self.buffer) > 2:
            self.search_name(self.buffer)
        else:
            self.clear_lines(ROW_LIST, len(self.matched_indices),
                    move_back=True)

    def loop(self):
        while True:
            if not self.remain_indices:
                self.destroy_screen()
                self.save()
                return

            raw_ch = self.stdscr.getch()
            if raw_ch == ord('*'):
                self.destroy_screen()
                sys.exit(0)

            if raw_ch == ord(':') and not self.command and \
                    not self.mode == MODE_COMMAND:
                # Push current mode into stack
                self.command.append(self.mode)
                self.mode = MODE_COMMAND
                self.command.append(':')

                self.show_status(''.join(self.command[1:]), 
                        color=COLOR_PAIR_CMD)

                continue

            if self.mode == MODE_COMMAND:
                if raw_ch == curses.KEY_BACKSPACE and \
                        len(self.command) > 1:
                    # [prev_mode, ':']
                    self.command.pop()

                    if len(self.command) == 1:
                        self.exec_command()
                        continue

                if raw_ch == ord('\n'):
                    self.exec_command()
                    continue

                if raw_ch > 31 and raw_ch < 127:
                    self.command.append(chr(raw_ch))

                self.show_status(''.join(self.command[1:]), 
                        color=COLOR_PAIR_CMD)

            if self.mode == MODE_NAME:
                self.name_keypress(raw_ch)
            elif self.mode == MODE_GRADE:
                self.grade_keypress(raw_ch)

    def exec_command(self):
        if not self.command:
            return

        # Recover previous mode
        if len(self.command) == 1:
            self.mode = self.command.pop()

        if len(self.command) == 2:
            # prev_mode, :
            self.mode = self.command[0]
            self.command = []
            self.show_status('')
            return

        if len(self.command) > 2:
            usr_cmd = ''.join(self.command[2:])

        if usr_cmd == '!!':
            self.rubric = []
            self.records = []
            self.remain_indices = range(len(self.namelist))
            self.destroy_screen()
            os.remove('.%s.pickle' % self.subject)
            print '> CACHE SWIPED!! Please start over again!'
            sys.exit(0)

        if REGEX_BNP.match(''.join(usr_cmd)) and \
                self.selected_index != -1 and \
                self.command[0] == MODE_GRADE:
            match = REGEX_BNP.match(usr_cmd)
            sign, num, pct_flag = match.groups()
            if pct_flag == '%':
                self.bonus_penalty[self.selected_index] = 1 + [-1,1][sign=='+'] * float(num)/100
            else:
                self.bonus_penalty[self.selected_index] = [-1,1][sign=='+'] * int(num)

            self.show_status('[%s] %s / %s' % (
                ['PENALTY', 'BONUS'][sign=='+'],
                match.group(),
                self.namelist[self.selected_index]
                ))
            self.mode = self.command[0]
            self.command = []
            return

        # None matches?
        # Invalid command
        self.mode == self.command[0]
        self.command = []
        self.show_status('')

    def show_rubric(self):
        padded_rubric = [str(self.rubric[x]).ljust(self.grade_spaces[x])
                for x in range(len(self.rubric))]

        self.stdscr.addstr(ROW_RUBRIC, 0, 
            'RUBRIC: ' + ''.join(padded_rubric),
            curses.color_pair(COLOR_PAIR_PROMPT))

    def show_grade(self, color=0):
        bp = self.bonus_penalty[self.selected_index]
        bp_disp = ''
        if bp != 0:
            if type(bp) is float:
                bp_disp = str(bp*100) + '%'
            elif type(bp) is int:
                bp_disp = ['','+'][bp>0] + str(bp) 

        grades = ''.join(self.buffer).split(' ')
        if grades:
            padded_grades = [grades[x].ljust(self.grade_spaces[x])
                    for x in range(len(grades)-1)]
            padded_grades.append(grades[-1])

        self.clear_lines(ROW_GRADE, 1)
        self.stdscr.addstr(ROW_GRADE, sum(self.grade_spaces)+8,
                bp_disp)
        self.stdscr.addstr(ROW_GRADE, 0, 
            'GRADE:  ' + ''.join(padded_grades),
            curses.color_pair(color))

    def parse_grade(self):
        raw_grades = ''.join(self.buffer).split(' ')
        if len(raw_grades) > len(self.rubric):
            self.buffer.pop()
            return

        if raw_grades:
            last_raw = raw_grades[-1]
            idx = len(raw_grades) - 1
            max = self.rubric[idx]

            if last_raw.isdigit():
                score = int(last_raw)
                flag = self.check_score(score, max)
                if flag == 1:
                    self.buffer.append(' ')
                elif flag == -1:
                    curses.beep()
                    for x in range(len(last_raw)):
                        self.buffer.pop()
            elif last_raw.startswith('.') and len(last_raw) > 1:
                # pop out the .x form
                score = int(last_raw[1:]) + 0.5
                flag = self.check_score(score, max)
                if flag == 1:
                    for x in range(len(last_raw)):
                        self.buffer.pop()
                    
                    self.buffer.extend(list(str(score)))
                    self.buffer.append(' ')
                elif flag == -1:
                    curses.beep()
                    for x in range(len(last_raw)):
                        self.buffer.pop()
            elif last_raw == '.':
                return
            else:
                for x in range(len(last_raw)):
                    self.buffer.pop()

    def check_score(self, score, max):
        l_max = len(str(max))

        if int(score) < score:
            # float score received
            l_score = len(str(score)) - 2
            if l_score > l_max or score > max:
                return -1
            if l_score == l_max and score < max:
                return 1
            if l_score < l_max and \
                    int(str(score)[:-2])*10 <= max:
                return 0

            return 1
        else:
            l_score = len(str(score)) 
            if l_score > l_max or score > max:
                return -1
            if l_score == l_max and score < max:
                return 1

            if l_score < l_max and \
                    int(str(score)) * 10 <= max:
                # check if the k-prefix is valid
                return 0

            return 1
    
    def set_mode(self, mode):
        self.buffer = []

        if mode == MODE_NAME:
            self.mode = MODE_NAME
            self.clear_lines(ROW_NAME, 1)
            self.stdscr.addstr(ROW_NAME, 0, 'NAME: ', 
                    curses.color_pair(COLOR_PAIR_PROMPT))

        elif mode == MODE_GRADE:
            self.mode = MODE_GRADE
            self.clear_lines(ROW_LIST, len(self.matched_indices),
                    move_back=True)

            self.matched_indices = []
            self.clear_lines(ROW_GRADE, 1)

            self.stdscr.addstr(ROW_GRADE, 0, 
                'GRADE:  ')

    def search_name(self, buffer):
        regexs = [re.compile('(^|\s)%s' % component.upper()) 
                for component in ''.join(buffer).split(' ')]

        matched_indices = [idx for idx in self.remain_indices
                if all(map(lambda x: x.search(self.namelist[idx]),
                    regexs))]

        if matched_indices:
            yx = self.stdscr.getyx()
            self.clear_lines(ROW_LIST, len(self.matched_indices))
            self.stdscr.addstr(ROW_LIST, 0, '\n'.join(
                ["%d. %s" % (idx+1, self.namelist[matched_indices[idx]])
                    for idx in xrange(len(matched_indices))]),
                curses.color_pair(2))

            self.stdscr.move(*yx)
        else:
            self.clear_lines(ROW_LIST, len(self.matched_indices), 
                    move_back=True)

        self.matched_indices = matched_indices

    def clear_lines(self, start, height, move_back=False):
        if move_back:
            yx = self.stdscr.getyx()

        for l in range(start, start+height):
            self.stdscr.move(l, 0)
            self.stdscr.clrtoeol()

        if move_back:
            self.stdscr.move(*yx)

    def erase_lines(self, start, height, move_back=False):
        if move_back:
            yx = self.stdscr.getyx()

        self.stdscr.move(start, 0)
        for l in range(start, start+height):
            self.stdscr.deleteln()

        if move_back:
            self.stdscr.move(*yx)

    def load_cache(self):
        if self.subject and os.path.exists('.%s.pickle' % self.subject):
            fd = open('.%s.pickle' % self.subject, 'r')
            self.rubric, self.remain_indices, \
                self.records, self.bonus_penalty = pickle.load(fd)

            self.grade_spaces = map(
                    lambda x: len(str(x)) + 3,
                    self.rubric)
            self.num_questions = len(self.rubric)

            self.mode = MODE_NAME
            fd.close()

    def cache(self, flush=False):
        if len(self.records) % 2 == 0 or flush:
            fd = open('.%s.pickle' % self.subject, 'w')
            pickle.dump(
                (self.rubric, self.remain_indices, 
                    self.records, self.bonus_penalty),
                fd)
            fd.close()

    def load_roster(self, filename='roster.txt'):
        if os.path.exists(filename):
            entries = open(filename).readlines()
            self.roster = [entry.strip().split('\t') for entry in entries]
            self.namelist = [r[2] for r in self.roster]
            self.remain_indices = set(range(len(self.namelist)))
            self.bonus_penalty = [0] * len(self.namelist)
            self.num_students = len(self.roster)
        else:
            self.roster = None

    def real_score(self, idx, score):
        if idx >= len(self.bonus_penalty):
            return score
        bp = self.bonus_penalty[idx] 
        if type(bp) is float:
            score *= bp
        elif type(bp) is int:
            score += bp

        score = ceil(score)
        score = self.max_score if score > self.max_score else score
        score = 0 if score < 0 else score

        return score

    def save(self):
        raw_data = [self.roster[r[0]] + r[1:] + \
            [self.bonus_penalty[r[0]]] + \
            [sum(r[1:])]
            for r in self.records]

        for d in raw_data:
            d[-1] = self.real_score(int(d[0]), d[-1])

        merged_data = [','.join(map(lambda x: str(x) \
                if type(x) in (float, int) \
                or (type(x) is str and x.isdigit())\
                else '"%s"' % x.strip(), 
                r))
                for r in raw_data]

        q_title = ['"q%d"' % x for x in range(1, self.num_questions+1)] \
                + ['"bop"', '"total"']

        fd = open('%s.csv' % self.subject, 'w+')
        fd.write('"id","section","name","major","comajor","year","credit",')
        fd.write(','.join(q_title) + '\n')
        fd.write('\n'.join(merged_data))
        fd.close()

def main():
    if len(sys.argv) > 1:
        grading = Grading(sys.argv[1])
        try:
            grading.loop()
        except KeyboardInterrupt:
            grading.destroy_screen()
            grading.cache(flush=True)
            grading.save()
            sys.exit(0)
    else:
        print 'Usage: %s [objname]' % sys.argv[0]

if __name__ == "__main__":
    main()
