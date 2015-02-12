#!/usr/bin/env python2

"""Calculate texture properties for a ROI."""

import argparse
import glob
import re
import numpy as np
import skimage

import dwi.asciifile
import dwi.texture
import dwi.util

def parse_args():
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description = __doc__)
    p.add_argument('--verbose', '-v', action='count',
            help='increase verbosity')
    p.add_argument('--input', '-i', metavar='FILENAME', required=True,
            nargs='+', default=[], help='input ASCII file')
    args = p.parse_args()
    return args

def normalize(pmap):
    """Normalize images within given range and convert to byte maps."""
    in_range = (0, 0.03)
    pmap = skimage.exposure.rescale_intensity(pmap, in_range=in_range)
    pmap = skimage.img_as_ubyte(pmap)
    return pmap

def plot(img):
    import pylab as pl
    pl.rcParams['image.cmap'] = 'gray'
    pl.rcParams['image.aspect'] = 'equal'
    pl.rcParams['image.interpolation'] = 'none'
    pl.imshow(img)
    pl.show()


args = parse_args()
for infile in args.input:
    af = dwi.asciifile.AsciiFile(infile)
    img = af.a.reshape((5,5))
    if args.verbose:
        print 'Image shape: %s' % (img.shape,)
    
    img = normalize(img)
    props = dwi.texture.get_coprops_img(img)
    
    outfile = 'props_%s' % af.basename
    if args.verbose:
        print 'Writing GLCM (%s) to %s' % (', '.join(dwi.texture.PROPNAMES), outfile)
    with open(outfile, 'w') as f:
        f.write(' '.join(map(str, props)) + '\n')

    import dwi.lbp
    lbp_freq_data, n_patterns = dwi.texture.get_lbp_freqs(img)
    lbp_freq_data.shape = (-1, n_patterns)
    
    outfile = 'lbpf_%s' % af.basename
    if args.verbose:
        print 'Writing LBP frequencies to %s' % outfile
    with open(outfile, 'w') as f:
        for patterns in lbp_freq_data:
            f.write(' '.join(map(str, patterns)) + '\n')
