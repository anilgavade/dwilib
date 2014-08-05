#!/usr/bin/env python2

"""Find most interesting ROI's in a DWI image."""

import os.path
import sys
import argparse

import numpy as np

from dwi import asciifile
from dwi import fit
from dwi import util

def parse_args():
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description =
            'Find interesting ROI\'s in a DWI image.')
    p.add_argument('--input', '-i', required=True,
            help='input files')
    p.add_argument('--roi', '-r', metavar='i', nargs=6, type=int, default=[],
            help='ROI (6 integers)')
    p.add_argument('--dim', '-d', metavar='i', nargs=3, type=int,
            default=[1,5,5], help='dimensions of wanted ROI (3 integers)')
    p.add_argument('--verbose', '-v', action='count',
            help='be more verbose')
    args = p.parse_args()
    return args

def get_score_param(img, param):
    """Return parameter score of given ROI."""
    if param.startswith('ADC'):
        r = 1-np.mean(img)
    elif param.startswith('K'):
        r = np.mean(img)/1000
    elif param.startswith('score'):
        r = np.mean(img)
    else:
        r = 0 # Unknown parameter
    return r

def get_score(img, params):
    """Return total score of given ROI."""
    scores = [get_score_param(i, p) for i, p in zip(img.T, params)]
    r = sum(scores)
    return r

def get_roi_scores(img, d, params):
    """Return array of all scores for each possible ROI of given dimension."""
    scores_shape = tuple((img.shape[i]-d[i]+1 for i in range(3)))
    scores = np.zeros(scores_shape)
    scores.fill(np.nan)
    for i in range(scores.shape[0]):
        for j in range(scores.shape[1]):
            for k in range(scores.shape[2]):
                z = (i, i+d[0])
                y = (j, j+d[1])
                x = (k, k+d[2])
                roi = img[z[0]:z[1], y[0]:y[1], x[0]:x[1], :]
                scores[i,j,k] = get_score(roi, params)
    return scores

def get_scoremap(img, d, params, n_rois):
    """Return array like original image, with scores of n_rois best ROI's."""
    scores = get_roi_scores(img, d, params)
    #print np.unravel_index(scores.argmax(), scores.shape)
    indices = scores.ravel().argsort()[::-1] # Sort ROI's by descending score.
    indices = indices[0:n_rois] # Select best ones.
    indices = [np.unravel_index(i, scores.shape) for i in indices]
    #scoremap = np.zeros_like(img[...,0])
    scoremap = np.zeros(img.shape[0:-1] + (1,))
    for z, y, x in indices:
        scoremap[z:z+d[0], y:y+d[1], x:x+d[2], 0] += scores[z,y,x]
    return scoremap


args = parse_args()

af = asciifile.AsciiFile(args.input)
img = af.a.view()
params = af.params()
img.shape = af.subwindow_shape() + (img.shape[-1],)
print img.shape
print get_score(img, params)

# Clip outliers.
img[...,1].clip(0, 1, out=img[...,1])

print util.fivenum(img[...,0].ravel())
print util.fivenum(img[...,1].ravel())

dims = [(1,i,i) for i in range(5, 16)]
n_rois = 10
scoremaps = [get_scoremap(img, d, params, n_rois) for d in dims]
scoremaps = [sum(scoremaps)]

roimap = get_scoremap(scoremaps[0], args.dim, ['score'], 1)

##
#for i in range(scoremap.shape[0]):
#    for j in range(scoremap.shape[1]):
#        for k in range(scoremap.shape[2]):
#            scoremap[i,j,k] = get_score(img[i,j,k,:])
#
#for _ in range(5):
#    scoremap2 = scoremap.copy()
#    for i in range(scoremap.shape[0]):
#        for j in range(scoremap.shape[1])[1:-1]:
#            for k in range(scoremap.shape[2])[1:-1]:
#                scoremap2[i,j,k] = scoremap[i,j,k] * np.sqrt(np.mean(scoremap[i,j-1:j+1,k-1:k+1]**2))
#    scoremap = scoremap2
#
#    import matplotlib
#    import matplotlib.pyplot as plt
#    plt.imshow(scoremap[0,1:-1,1:-1], cmap='gray', interpolation='nearest')
#    plt.show()
##

import matplotlib
import matplotlib.pyplot as plt
for pmap in scoremaps + [roimap]:
    plt.imshow(pmap[0,...,0], cmap='gray', interpolation='nearest')
    plt.show()
