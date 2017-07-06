#!/usr/bin/python3

"""Calculate correlation for parametric maps vs. Gleason scores."""

import argparse
import math
import numpy as np
from scipy import stats

import dwi.patient
import dwi.util
from dwi.compat import read_pmaps


def parse_args():
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('-v', '--verbose', action='count',
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


def correlation(x, y, method='spearman'):
    """Calculate correlation with p-value and confidence interval."""
    assert len(x) == len(y)
    methods = dict(
        pearson=stats.pearsonr,
        spearman=stats.spearmanr,
        kendall=stats.kendalltau,
    )
    if dwi.util.all_equal(x):
        r = p = lower = upper = np.nan
    else:
        f = methods[method]
        r, p = f(x, y)
        n = len(x)
        stderr = 1 / math.sqrt(n-3)
        delta = 1.96 * stderr
        lower = math.tanh(math.atanh(r) - delta)
        upper = math.tanh(math.atanh(r) + delta)
    return dict(r=r, p=p, lower=lower, upper=upper)


def collect_data(patients, pmapdirs, **kwargs):
    """Collect all data (each directory, each pmap, each feature)."""
    X, Y = [], []
    params = []
    scores = None
    for i, pmapdir in enumerate(pmapdirs):
        data = read_pmaps(patients, pmapdir, **kwargs)
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
            params.append('{}:{}'.format(i, param))
    return X, Y, params, scores, groups, group_sizes


def main():
    """Main."""
    args = parse_args()
    d = dict(thresholds=args.thresholds, voxel=args.voxel,
             multiroi=args.multilesion, dropok=args.dropok)
    X, Y, params, scores, groups, group_sizes = collect_data(args.patients,
                                                             args.pmapdir, **d)

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
    params_maxlen = max(len(x) for x in params)
    for x, y, param in zip(X, Y, params):
        d = dict(param=param, l=params_maxlen, f='.3f')
        d.update(correlation(x, y))
        if args.verbose:
            s = '{param:{l}}  {r:+{f}}  {p:{f}}  {lower:+{f}}  {upper:+{f}}'
        else:
            s = '{r:+.3f}'
        print(s.format(**d))


if __name__ == '__main__':
    main()
