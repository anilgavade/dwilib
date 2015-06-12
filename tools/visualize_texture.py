#!/usr/bin/env python2

"""Visualize texture map alongside pmap with lesion highlighted."""

import argparse

import numpy as np

import dwi.asciifile
import dwi.dataset
import dwi.patient
import dwi.dwimage
import dwi.mask
import dwi.texture
import dwi.util

def parse_args():
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verbose', '-v', action='count',
            help='increase verbosity')
    p.add_argument('--subregiondir', default='bounding_box_100_10pad',
            help='subregion bounding box directory')
    p.add_argument('--pmapdir', default='dicoms_*',
            help='input parametric map directory')
    p.add_argument('--af',
            help='input parametric map as ASCII file')
    p.add_argument('--params', nargs='+', default=['ADCm'],
            help='image parameter to use')
    p.add_argument('--case', type=int, required=True,
            help='case number')
    p.add_argument('--scan', required=True,
            help='scan identifier')
    p.add_argument('--pmaskdir', default='masks_prostate',
            help='prostate mask directory')
    p.add_argument('--lmaskdir', default='masks_lesion_DWI',
            help='lesion mask directory')
    p.add_argument('--method', default='stats',
            help='texture method')
    p.add_argument('--winsize', type=int, default=5,
            help='window side length')
    args = p.parse_args()
    return args

def plot(pmaps, lmask, tmaps, params, names, filename):
    import matplotlib.pyplot as plt

    assert pmaps[0].shape == lmask.shape
    #plt.rcParams['image.cmap'] = 'coolwarm'
    plt.rcParams['image.cmap'] = 'YlGnBu_r'
    plt.rcParams['image.interpolation'] = 'nearest'
    n_cols, n_rows = len(pmaps)+len(tmaps), 1
    fig = plt.figure(figsize=(n_cols*6, n_rows*6))

    for i, (pmap, param) in enumerate(zip(pmaps, params)):
        ax = fig.add_subplot(n_rows, n_cols, i+1)
        ax.set_title(param)
        impmap = plt.imshow(pmap)
        view = np.zeros(lmask.shape + (4,), dtype=float)
        view[...,0] = view[...,3] = lmask
        plt.imshow(view, alpha=0.6)
        fig.colorbar(impmap, ax=ax, shrink=0.65)

    for i, (tmap, name) in enumerate(zip(tmaps, names)):
        ax = fig.add_subplot(n_rows, n_cols, len(pmaps)+i+1)
        ax.set_title(name)
        plt.imshow(tmap, vmin=0)

    plt.tight_layout()
    print 'Writing figure:', filename
    plt.savefig(filename, bbox_inches='tight')
    plt.close()


args = parse_args()
if args.verbose:
    print 'Reading data...'
data = dwi.dataset.dataset_read_samples([(args.case, args.scan)])
dwi.dataset.dataset_read_subregions(data, args.subregiondir)
if args.af:
    af = dwi.asciifile.AsciiFile(args.af)
    print 'params:', af.params()
    # Fix switched height/width.
    subwindow = af.subwindow()
    subwindow = subwindow[2:] + subwindow[:2]
    assert len(subwindow) == 4
    subwindow_shape = dwi.util.subwindow_shape(subwindow)
    image = af.a
    image.shape = (20,) + subwindow_shape + (len(af.params()),)
    data[0]['subregion'] = (0, 20) + subwindow
    data[0]['image'] = image
    print data[0]['subregion']
else:
    dwi.dataset.dataset_read_pmaps(data, args.pmapdir, args.params)
dwi.dataset.dataset_read_prostate_masks(data, args.pmaskdir)
dwi.dataset.dataset_read_lesion_masks(data, args.lmaskdir)

data = data[0]
print 'image shape:', data['image'].shape
print 'lesion mask sizes:', [m.n_selected() for m in data['lesion_masks']]

# Find maximum lesion and use it.
lesion = max((m.n_selected(), i) for i, m in enumerate(data['lesion_masks']))
print 'max lesion:', lesion
max_lesion = lesion[1]

max_slice = data['lesion_masks'][max_lesion].max_slices()[0]
pmap = data['image'][max_slice]
proste_mask = data['prostate_mask'].array[max_slice]
lesion_mask = data['lesion_masks'][max_lesion].array[max_slice]

pmaps = []
for i, param in enumerate(args.params):
    p = pmap[:,:,i]
    print param, dwi.util.fivenum(p)
    dwi.util.clip_outliers(p, out=p)
    pmaps.append(p)
    tmaps, names = dwi.texture.texture_map(args.method, p, args.winsize,
            mask=proste_mask)

filename = 'texture_{case}_{scan}'.format(**data)
plot(pmaps, lesion_mask, tmaps, args.params, names, filename)
