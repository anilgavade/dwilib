#!/usr/bin/env python2

"""Calculate texture properties for a masked area."""

#TODO pmap normalization for GLCM
#TODO Gabor clips pmap, only suitable for ADCm
#TODO GLCM uses only length 1

import argparse
import collections
import glob
import re
import numpy as np

import dwi.asciifile
import dwi.dataset
import dwi.mask
import dwi.plot
import dwi.texture
import dwi.util

METHODS = collections.OrderedDict([
        ('stats', dwi.texture.stats_map),
        ('glcm', dwi.texture.glcm_map),
        ('haralick', dwi.texture.haralick_map),
        ('lbp', dwi.texture.lbp_freq_map),
        ('hog', dwi.texture.hog_map),
        ('gabor', dwi.texture.gabor_map),
        ('moment', dwi.texture.moment_map),
        ('haar', dwi.texture.haar_map),
        ])

def parse_args():
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verbose', '-v', action='count',
            help='increase verbosity')
    p.add_argument('--pmapdir', default='results_Mono_combinedDICOM',
            help='input parametric map directory')
    p.add_argument('--param', default='ADCm',
            help='image parameter to use')
    p.add_argument('--case', type=int,
            help='case number')
    p.add_argument('--scan',
            help='scan identifier')
    p.add_argument('--mask',
            help='mask file to use')
    p.add_argument('--methods', metavar='METHOD', nargs='*',
            help='methods ({})'.format(', '.join(METHODS.keys())))
    p.add_argument('--winsizes', metavar='I', nargs='*', type=int, default=[5],
            help='window side lengths')
    p.add_argument('--output', metavar='FILENAME',
            help='output ASCII file')
    args = p.parse_args()
    return args


args = parse_args()
if args.verbose:
    print 'Reading data...'
data = dwi.dataset.dataset_read_samples([(args.case, args.scan)])
dwi.dataset.dataset_read_pmaps(data, args.pmapdir, [args.param])
mask = dwi.mask.read_mask(args.mask)

img = data[0]['image']
if isinstance(mask, dwi.mask.Mask):
    mask = mask.convert_to_3d(img.shape[0])

slice_index = mask.max_slices()[0]
img_slice = img[slice_index,:,:,0]
mask_slice = mask.array[slice_index]

if args.verbose > 1:
    d = dict(s=img.shape, i=slice_index, n=np.count_nonzero(mask_slice),
            w=args.winsizes)
    print 'Image: {s}, slice: {i}, voxels: {n}, windows: {w}'.format(**d)

if args.verbose:
    print 'Calculating texture features...'
feats = []
featnames = []
for method, call in METHODS.items():
    if args.methods is None or method in args.methods:
        if args.verbose > 1:
            print method
        for winsize in args.winsizes:
            tmaps, names = call(img_slice, winsize, mask=mask_slice)
            tmaps = tmaps[:,mask_slice]
            feats += map(np.mean, tmaps)
            featnames += names

if args.verbose:
    print 'Writing %s features to %s' % (len(feats), args.output)
dwi.asciifile.write_ascii_file(args.output, [feats], featnames)
