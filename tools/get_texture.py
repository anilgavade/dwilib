#!/usr/bin/env python2

"""Calculate texture properties for a ROI."""

import argparse
import glob
import re
import numpy as np

import dwi.asciifile
import dwi.dataset
import dwi.mask
import dwi.plot
import dwi.texture
import dwi.util

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
    p.add_argument('--methods', metavar='METHOD', nargs='+',
            default=['all'],
            help='methods separated by comma')
    p.add_argument('--output', metavar='FILENAME',
            help='output ASCII file')
    args = p.parse_args()
    return args

def normalize(pmap):
    """Normalize images within given range and convert to byte maps."""
    import skimage
    import skimage.exposure
    in_range = (0, 0.03)
    #in_range = (0, 0.01)
    pmap = skimage.exposure.rescale_intensity(pmap, in_range=in_range)
    pmap = skimage.img_as_ubyte(pmap)
    return pmap


args = parse_args()
print 'Reading data...'
data = dwi.dataset.dataset_read_samples([(args.case, args.scan)])
dwi.dataset.dataset_read_pmaps(data, args.pmapdir, [args.param])
mask = dwi.mask.read_mask(args.mask)

img = data[0]['image']
img = mask.selected(img)
img.shape = dwi.util.make2d(img.size)
if args.verbose > 1:
    print 'Image: %s, ROI: %s' % (data[0]['image'].shape, img.shape)

propnames = []
props = []

if 'basic' in args.methods or 'all' in args.methods:
    d = dwi.texture.stats(img)
    for k, v in d.iteritems():
        propnames.append(k)
        props.append(v)

if 'glcm' in args.methods or 'all' in args.methods:
    img_normalized = normalize(img)
    d = dwi.texture.glcm_props(img_normalized)
    for k, v in d.iteritems():
        propnames.append(k)
        props.append(v)

if 'haralick' in args.methods or 'all' in args.methods:
    img_normalized = normalize(img)
    feats, labels = dwi.texture.haralick(img_normalized)
    for i, (feat, label) in enumerate(zip(feats, labels)):
        if ' ' in label:
            label = ''.join([word[0] for word in label.split()])
        propnames.append('haralick{:d}-{:s}'.format(i+1, label))
        props.append(feat)

if 'lbp' in args.methods or 'all' in args.methods:
    _, lbp_freq_data, n_patterns = dwi.texture.lbp_freqs(img, winsize=5,
            radius=1.5)
    lbp_freq_data = lbp_freq_data.reshape((-1, n_patterns))
    lbp_freq_data = np.mean(lbp_freq_data, axis=0)
    propnames += ['lbpf{:d}'.format(i) for i in range(n_patterns)]
    props += list(lbp_freq_data)

if 'hog' in args.methods or 'all' in args.methods:
    hog = dwi.texture.hog(img)
    propnames += ['hog{:d}'.format(i) for i in range(len(hog))]
    props += list(hog)

if 'gabor' in args.methods or 'all' in args.methods:
    # TODO only for ADCm, clips them
    img = img.copy()
    img.shape += (1,)
    dwi.util.clip_pmap(img, ['ADCm'])
    #img = (img - img.mean()) / img.std()
    d = dwi.texture.gabor(img[...,0], sigmas=[1, 2, 3],
            freqs=[0.1, 0.2, 0.3, 0.4])
    for k, v in d.iteritems():
        propnames.append('gabor{}'.format(str(k)).translate(None, " '"))
        props.append(v)

if 'moment' in args.methods or 'all' in args.methods:
    d = dwi.texture.moments(img.squeeze(), max_order=12)
    for k, v in d.iteritems():
        propnames.append('moment{}'.format(str(k)).translate(None, " '"))
        props.append(v)

if 'haar' in args.methods or 'all' in args.methods:
    l = [0,1,3,4] # Exclude middle row and column.
    win = img.squeeze()[l][:,l]
    d = dwi.texture.haar_features(win)
    for k, v in d.iteritems():
        propnames.append('haar{}'.format(str(k)).translate(None, " '"))
        props.append(v)

if args.verbose:
    print 'Writing %s features to %s' % (len(props), args.output)
dwi.asciifile.write_ascii_file(args.output, [props], propnames)

#img = img[50:150, 50:150]
#lbp_data, lbp_freq_data, patterns = dwi.texture.lbp_freqs(img)
#freqs = np.rollaxis(lbp_freq_data, 2)
#dwi.plot.show_images([[img, lbp_data], freqs[:5], freqs[5:]])
