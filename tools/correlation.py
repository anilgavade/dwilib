#!/usr/bin/env python2

"""Calculate correlation for parametric maps vs. Gleason scores."""

from __future__ import division, print_function
import argparse
import math
import numpy as np
import scipy.stats

import dwi.patient
import dwi.util

def parse_args():
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verbose', '-v', action='count',
                   help='be more verbose')
    p.add_argument('--patients', default='patients.txt',
                   help='patients file')
    p.add_argument('--pmapdir', nargs='+', required=True,
                   help='input pmap directory')
    p.add_argument('--thresholds', nargs='*', default=[],
                   help='classification thresholds (group maximums)')
    p.add_argument('--voxel', default='all',
                   help='index of voxel to use, or all, sole, mean, median')
    p.add_argument('--multilesion', action='store_true',
                   help='use all lesions, not just first for each')
    p.add_argument('--dropok', action='store_true',
                   help='allow dropping of files not found')
    return p.parse_args()

def correlation(x, y):
    """Calculate correlation with p-value and confidence interval."""
    assert len(x) == len(y)
    if dwi.util.all_equal(x):
        r = p = lower = upper = np.nan
    else:
        #r, p = scipy.stats.pearsonr(x, y)
        #r, p = scipy.stats.kendalltau(x, y)
        r, p = scipy.stats.spearmanr(x, y)
        n = len(x)
        stderr = 1 / math.sqrt(n-3)
        delta = 1.96 * stderr
        lower = math.tanh(math.atanh(r) - delta)
        upper = math.tanh(math.atanh(r) + delta)
    return dict(r=r, p=p, lower=lower, upper=upper)

def main():
    # Collect all parameters.
    args = parse_args()
    X, Y = [], []
    Params = []
    scores = None
    for i, pmapdir in enumerate(args.pmapdir):
        data = dwi.patient.read_pmaps(args.patients, pmapdir, args.thresholds,
                                      voxel=args.voxel,
                                      multiroi=args.multilesion,
                                      dropok=args.dropok)
        if scores is None:
            scores, groups, group_sizes = dwi.patient.grouping(data)
        for j, param in enumerate(data[0]['params']):
            x, y = [], []
            for d in data:
                for v in d['pmap']:
                    x.append(v[j])
                    y.append(d['label'])
            X.append(np.asarray(x))
            Y.append(np.asarray(y))
            Params.append('%i:%s' % (i, param))

    # Print info.
    if args.verbose > 1:
        d = dict(n=len(X[0]),
                 ns=len(scores), s=scores,
                 ng=len(groups), g=' '.join(str(x) for x in groups),
                 gs=', '.join(str(x) for x in group_sizes))
        print('Samples: {n}'.format(**d))
        print('Scores: {ns}: {s}'.format(**d))
        print('Groups: {ng}: {g}'.format(**d))
        print('Group sizes: {gs}'.format(**d))

    # Print correlations.
    if args.verbose > 1:
        print('# param  r  p  lower  upper')
    params_maxlen = max(len(p) for p in Params)
    for x, y, param in zip(X, Y, Params):
        d = dict(param=param)
        d.update(correlation(x, y))
        if args.verbose:
            s = ('{param:%i}  {r:+.3f}  {p:.3f}  {lower:+.3f}  {upper:+.3f}' %
                 params_maxlen)
        else:
            s = '{r:+.3f}'
        print(s.format(**d))

if __name__ == '__main__':
    main()
