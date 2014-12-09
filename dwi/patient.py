import os.path
import re
from functools import total_ordering
import numpy as np

import asciifile
import util

@total_ordering
class GleasonScore(object):
    def __init__(self, score):
        """Intialize with a sequence or a string like '3+4+5' (third digit is
        optional)."""
        s = score.split('+') if isinstance(score, str) else list(score)
        if not 2 <= len(s) <= 3:
            raise Exception('Invalid gleason score: %s', score)
        if len(s) == 2:
            s.append(0)
        self.score = tuple(map(int, s))

    def __repr__(self):
        s = self.score
        if not s[-1]:
            s = s[0:-1] # Drop trailing zero.
        return '+'.join(map(str, s))

    def __hash__(self):
        return hash(self.score)

    def __iter__(self):
        return iter(self.score)

    def __eq__(self, other):
        return self.score == other.score

    def __lt__(self, other):
        return self.score < other.score

    def is_aggressive(self):
        """Is this considered aggressive."""
        return self.score[0] > 3

@total_ordering
class Patient(object):
    def __init__(self, num, name, scans, score):
        self.num = num
        self.name = name
        self.scans = scans
        self.score = score

    def __repr__(self):
        return repr(self.tuple())

    def __hash__(self):
        return hash(self.tuple())

    def __eq__(self, other):
        return self.tuple() == other.tuple()

    def __lt__(self, other):
        return self.tuple() < other.tuple()

    def tuple(self):
        return self.num, self.name, self.scans, self.score

def read_patients_file(filename):
    """Load a list of patients.

    Row format: num name scan,... score1+score2
    """
    patients = []
    #p = re.compile(r'(\d+)\s+(\w+)\s+([\w,]+)\s+(\d\+\d)')
    p = re.compile(r'(\d+)\s+(\w+)\s+([\w,]+)\s+(\d\+\d(\+\d)?)')
    with open(filename, 'rU') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line[0] == '#':
                continue
            m = p.match(line)
            if m:
                num, name, scans, score = m.groups()[0:4]
                num = int(num)
                name = name.lower()
                scans = sorted(scans.lower().split(','))
                score = GleasonScore(score)
                patient = Patient(num, name, scans, score)
                patients.append(patient)
            else:
                raise Exception('Invalid line in patients file: %s', line)
    return sorted(patients)

def scan_in_patients(patients, num, scan):
    """Is this scan listed in the patients sequence?"""
    for p in patients:
        if p.num == num and scan in p.scans:
            return True
    return False

def get_patient(patients, num):
    """Search a patient from sequence by patient number."""
    for p in patients:
        if p.num == num:
            return p
    return None

def get_gleason_scores(patients):
    """Get all separate Gleason scores, sorted."""
    scores = []
    for p in patients:
        if not p.score in scores:
            scores.append(p.score)
    return sorted(scores)

def score_ord(sorted_scores, score):
    """Get Gleason score's ordinal number."""
    return sorted_scores.index(score)

def read_exclude_file(filename):
    """Load a list scans to exclude."""
    exclusions = []
    p = re.compile(r'(\d+)\s+([*\w]+)')
    with open(filename, 'rU') as f:
        for line in f:
            m = p.match(line.strip())
            if m:
                num, scan = m.groups()
                num = int(num)
                scan = scan.lower()
                exclusions.append((num, scan))
    return sorted(list(set(exclusions)))

def scan_excluded(exclusions, num, scan):
    """Tell whether given scan should be excluded."""
    for n, s in exclusions:
        if n == num:
            if s == scan or s == '*':
                return True
    return False

def exclude_files(pmapfiles, patients, exclusions=[]):
    """Return filenames without those that are to be excluded."""
    r = []
    for f in pmapfiles:
        num, name, scan = util.parse_filename(os.path.basename(f))
        p = get_patient(patients, num)
        if not p:
            continue # Patient not mentioned in patients file: exclude.
        if not scan_in_patients(patients, num, scan):
            continue # Scan not mentioned in patients file: exclude.
        if scan_excluded(exclusions, num, scan):
            continue # Scan mentioned in exclude file: exclude.
        r.append(f)
    return r

def load_files(patients, filenames, pairs=False):
    """Load pmap files."""
    pmapfiles = exclude_files(filenames, patients)
    afs = map(asciifile.AsciiFile, pmapfiles)
    if pairs:
        util.scan_pairs(afs)
    ids = [util.parse_num_scan(af.basename) for af in afs]
    pmaps = [af.a for af in afs]
    pmaps = np.array(pmaps)
    params = afs[0].params()
    assert pmaps.shape[-1] == len(params), 'Parameter name mismatch.'
    #print 'Filenames: %i, loaded: %i, lines: %i, columns: %i'\
    #        % (len(filenames), pmaps.shape[0], pmaps.shape[1], pmaps.shape[2])
    return pmaps, ids, params

def load_labels(patients, nums, labeltype='score'):
    """Load labels according to patient numbers."""
    gs = get_gleason_scores(patients)
    scores = [get_patient(patients, n).score for n in nums]
    if labeltype == 'score':
        # Use Gleason score.
        labels = scores
    elif labeltype == 'ord':
        # Use ordinal.
        labels = [score_ord(gs, s) for s in scores]
    elif labeltype == 'bin':
        # Is aggressive? (ROI1.)
        labels = [s.is_aggressive() for s in scores]
    elif labeltype == 'cancer':
        # Is cancer? (ROI1 vs 2, all true for ROI1.)
        labels = [1] * len(scores)
    else:
        raise Exception('Invalid parameter: %s' % labeltype)
    return labels
