"""Texture analysis.

Texture methods are of three possible types: 'map' produces a texture map by
using a sliding window, 'mbb' uses selected voxels to produce a single value
for each slice, and 'all' produces a single value for selected voxels from all
slices.

Output type can be one of the following: 'map' just returns the map or spreads
the single values over all selected voxels, 'mean' and 'median' return just the
single values or reduces the map into a single average value.

Scikit-image and Mahotas libraries are used for the calculations.
"""

from __future__ import absolute_import, division, print_function
from collections import OrderedDict

import numpy as np
import scipy as sp
import skimage
import skimage.exposure
import skimage.feature
import skimage.filters

import dwi.hdf5
import dwi.util
from dwi.texture_mahotas import haar_map, zernike_map
# from dwi.texture_jp import lbp_freq_map


DTYPE = np.float32  # Type used for storing texture features.
MODE = None  # For now, set this for normalize(). TODO: Better solution.

def normalize(pmap, levels=128):
    """Normalize images within given range and convert to byte maps with given
    number of graylevels."""
    if MODE in ('DWI-Mono-ADCm', 'DWI-Kurt-ADCk'):
        assert pmap.dtype in [np.float32, np.float64]
        # in_range = (0, 0.03)
        in_range = (0, 0.005)
        # in_range = (0, 0.002)
    elif MODE in ('DWI-Kurt-K', 'T2w'):
        # in_range = (pmap.min(), pmap.max())
        # in_range = (0, np.percentile(pmap, 99.8))
        in_range = tuple(np.percentile(pmap, (0.8, 99.2)))
        # in_range = tuple(np.percentile(pmap, (0, 99.8)))
    elif MODE in ('T2', 'T2-fitted'):
        in_range = (0, 300)
    elif MODE in ('T2w-std',):
        if pmap.dtype == np.int32:
            # The rescaler cannot handle int32.
            pmap = np.asarray(pmap, dtype=np.int16)
        assert pmap.dtype == np.int16
        in_range = (0, 4095)
    else:
        raise ValueError('Invalid mode: {}'.format(MODE))
    # dwi.util.report('Normalizing:', MODE, in_range)
    pmap = skimage.exposure.rescale_intensity(pmap, in_range=in_range)
    pmap = skimage.img_as_ubyte(pmap)
    pmap //= int(round(256 / levels))
    return pmap


def abbrev(name):
    """Abbreviate multiword feature name."""
    if ' ' in name:
        name = ''.join(word[0] for word in name.split())
    return name


# Basic statistical features


def stats(img):
    """Statistical texture features that don't consider spatial relations."""
    img = np.asanyarray(img)
    d = OrderedDict()
    d['mean'] = np.mean(img)
    d['stddev'] = np.std(img)
    d['range'] = np.max(img) - np.min(img)
    d.update(dwi.util.fivenumd(img))
    for i in range(1, 10):
        d['decile%i' % i] = np.percentile(img, i*10)
    d['kurtosis'] = sp.stats.kurtosis(img.ravel())
    d['skewness'] = sp.stats.skew(img.ravel())
    return d


def stats_map(img, winsize, names=None, mask=None, output=None):
    """Statistical texture feature map."""
    for pos, win in dwi.util.sliding_window(img, winsize, mask=mask):
        d = stats(win)
        if names is None:
            names = d.keys()
        if output is None:
            output = np.zeros((len(names),) + img.shape, dtype=DTYPE)
        for i, name in enumerate(names):
            output[(i,) + pos] = d[name]
    names = ['stats({})'.format(n) for n in names]
    return output, names


def stats_mbb(img, mask):
    """Statistical texture features unified over a masked area."""
    # TODO: Add area size?
    voxels = img[mask]
    feats = stats(voxels)
    output = feats.values()
    names = ['stats({})'.format(k) for k in feats.keys()]
    return output, names


# Grey-Level Co-Occurrence Matrix (GLCM) features

PROPNAMES = 'contrast dissimilarity homogeneity energy correlation ASM'.split()


def glcm_props(img, names=PROPNAMES, distances=(1, 2, 3, 4),
               ignore_zeros=False):
    """Grey-level co-occurrence matrix (GLCM) texture features.

    Six features provided by scikit-image. Averaged over 4 directions for
    orientation invariance.
    """
    assert img.ndim == 2
    assert img.dtype == np.ubyte
    # Prune distances too long for the window.
    # Commented out: problems with mbb - sometimes includes, sometimes not.
    # distances = [x for x in distances if x <= min(img.shape)-1]
    angles = (0, np.pi/4, np.pi/2, 3*np.pi/4)
    levels = img.max() + 1
    glcm = skimage.feature.greycomatrix(img, distances, angles, levels,
                                        symmetric=True, normed=True)
    if ignore_zeros and np.min(img) == 0:
        # Drop information on the first grey-level if it's zero (background).
        glcm = glcm[1:, 1:, ...]
    d = OrderedDict()
    for name in names:
        # Returns array (distance, angle).
        feats = skimage.feature.greycoprops(glcm, name)
        feats = np.mean(feats, axis=1)  # Average over angles.
        for dist, feat in zip(distances, feats):
            d[(name, dist)] = feat
        d[(name, 'avg')] = np.mean(feats)
    return d


def glcm_map(img, winsize, names=PROPNAMES, ignore_zeros=False, mask=None,
             output=None):
    """Grey-level co-occurrence matrix (GLCM) texture feature map."""
    img = normalize(img)
    for pos, win in dwi.util.sliding_window(img, winsize, mask=mask):
        feats = glcm_props(win, names, ignore_zeros=ignore_zeros)
        if output is None:
            output = np.zeros((len(feats),) + img.shape, dtype=DTYPE)
        for i, value in enumerate(feats.values()):
            output[(i,) + pos] = value
    names = ['glcm{}'.format(t).translate(None, " '") for t in feats.keys()]
    return output, names


def glcm_mbb(img, mask):
    """Single GLCM features for selected area inside minimum bounding box."""
    img = normalize(img)
    positions = dwi.util.bounding_box(mask)
    slices = [slice(*t) for t in positions]
    img = img[slices]
    mask = mask[slices]
    img[-mask] = 0
    feats = glcm_props(img, ignore_zeros=True)
    output = feats.values()
    names = ['glcm{}'.format(t).translate(None, " '") for t in feats.keys()]
    return output, names


# Local Binary Pattern (LBP) features


def lbp_freq_map(img, winsize, neighbours=8, radius=None, mask=None):
    """Local Binary Pattern (LBP) frequency histogram map."""
    if radius is None:
        radius = winsize // 2
    n = neighbours + 2
    freqs = skimage.feature.local_binary_pattern(img, neighbours, radius,
                                                 method='uniform')
    assert freqs.max() == n - 1, freqs.max()
    output = np.zeros((n,) + img.shape, dtype=np.float16)
    # for i, a in enumerate(output):
    #     a[:, :] = (freqs == i)
    for origin, win in dwi.util.sliding_window(freqs, winsize, mask=mask):
        for i in range(n):
            output[i][origin] = np.count_nonzero(win == i) / win.size
    assert len(output) == n, output.shape
    names = ['lbp({r},{i})'.format(r=radius, i=i) for i in range(n)]
    # if mask is not None:
    #     output[:, -mask] = 0
    return output, names


# Gabor features


def gabor(img, sigmas=None, freqs=None):
    """Gabor features.

    Window size is wavelength 1. Frequency is 1/wavelength; the library uses
    frequency as input parameter. Averaged over 4 directions for orientation
    invariance.
    """
    img = np.asarray(img, dtype=np.double)
    if sigmas is None:
        sigmas = 1, 2, 3
    if freqs is None:
        freqs = 0.1, 0.2, 0.3, 0.4
    thetas = tuple(np.pi/4*i for i in range(4))
    names = 'mean', 'var', 'absmean', 'mag'
    shape = len(thetas), len(sigmas), len(freqs), len(names)
    feats = np.zeros(shape, dtype=DTYPE)
    for i, j, k in np.ndindex(shape[:-1]):
        real, imag = skimage.filters.gabor(img, frequency=freqs[k],
                                           theta=thetas[i],
                                           sigma_x=sigmas[j],
                                           sigma_y=sigmas[j])
        feats[i, j, k, :] = (np.mean(real), np.var(real),
                             np.mean(np.abs(real)),
                             np.mean(np.sqrt(real**2+imag**2)))
    feats = np.mean(feats, axis=0)  # Average over directions.
    d = OrderedDict()
    for (i, j, k), value in np.ndenumerate(feats):
        key = sigmas[i], freqs[j], names[k]
        d[key] = value
    return d


def gabor_map(img, winsize, sigmas=None, freqs=None, mask=None, output=None):
    """Gabor texture feature map."""
    for pos, win in dwi.util.sliding_window(img, winsize, mask=mask):
        feats = gabor(win, sigmas=sigmas, freqs=freqs)
        if output is None:
            output = np.zeros((len(feats),) + img.shape, dtype=DTYPE)
        for i, v in enumerate(feats.values()):
            output[(i,) + pos] = v
    names = ['gabor{}'.format(t).translate(None, " '") for t in feats.keys()]
    # fin = np.isfinite(output)
    # output[-fin] = 0  # Make non-finites zero.
    return output, names


def gabor_map_alt(img, winsize, wavelengths=None, mask=None, output=None):
    """Gabor texture feature map."""
    img = np.asarray(img, dtype=np.double)
    if wavelengths is None:
        wavelengths = [2**i for i in range(1, 6)]
    freqs = [1/i for i in wavelengths]
    thetas = [np.pi/4*i for i in range(4)]
    if output is None:
        output = np.zeros((len(thetas), len(freqs)) + img.shape, dtype=DTYPE)
    img = (img - img.mean()) / img.std()
    for i, theta in enumerate(thetas):
        for j, freq in enumerate(freqs):
            kernel = skimage.filters.gabor_kernel(freq, theta=theta)
            kernel = np.real(kernel)
            dwi.util.report(i, j, theta, freq, kernel.shape)
            a = sp.ndimage.filters.convolve(img[:, :], kernel)
            output[i, j, :, :] = a
    output = np.mean(output, axis=0)  # Average over directions.
    names = ['gabor({})'.format(x) for x in wavelengths]
    return output, names


# Histogram of Oriented Gradients (HOG)


def hog(img):
    """Histogram of oriented gradients (HOG).

    Averaged over directions for orientation invariance.
    """
    # TODO: transform_sqrt=True is here to replicate old behaviour
    # normalise=True, which was removed as incorrect in skimage 0.12. Should
    # this also be removed here? Docs warn against using with negative values.
    kwargs = dict(orientations=8,
                  pixels_per_cell=img.shape,
                  cells_per_block=(1, 1),
                  transform_sqrt=True)
    feats = skimage.feature.hog(img, **kwargs)
    return np.mean(feats)


def hog_map(img, winsize, mask=None, output=None):
    """Histogram of oriented gradients (HOG) texture feature map."""
    for pos, win in dwi.util.sliding_window(img, winsize, mask=mask):
        feats = [hog(win)]
        if output is None:
            output = np.zeros((len(feats),) + img.shape, dtype=DTYPE)
        for i, v in enumerate(feats):
            output[(i,) + pos] = v
    names = ['hog']
    return output, names


# Hu moments.


def hu(img, postproc=True):
    """The seven moments of Hu.

    If postproc is True, return the logarithms of absolute values.

    These are a derivative of the geometric moments, that are invariant under
    translation, scaling, and rotation (and reflection, if absolute taken).
    """
    img = np.asarray(img, dtype=np.double)
    assert img.ndim == 2
    m = skimage.measure.moments_central(img, img.shape[0]/2, img.shape[1]/2)
    m = skimage.measure.moments_normalized(m)
    m = skimage.measure.moments_hu(m)
    if postproc:
        m = abs(m)  # Last one changes sign on reflection.
        m[m == 0] = 1  # Required by log.
        m = np.log(m)  # They are small, usually logarithms are used.
    m = np.nan_to_num(m)  # Not sure why there are sometimes NaN values.
    assert m.shape == (7,)
    return m


def hu_map(img, winsize, mask=None, output=None):
    """Hu moment map."""
    for pos, win in dwi.util.sliding_window(img, winsize, mask=mask):
        feats = hu(win)
        if output is None:
            output = np.zeros((len(feats),) + img.shape, dtype=DTYPE)
        for i, v in enumerate(feats):
            output[(i,) + pos] = v
    names = ['hu({})'.format(i) for i in range(len(feats))]
    return output, names


# Sobel.


def sobel(img, mask=None):
    """Sobel edge descriptor."""
    output = skimage.filters.sobel(img, mask=mask)
    return output


def sobel_map(img, winsize=None, mask=None):
    """Sobel edge descriptor map.

    Parameter winsize is not used, it is there for API compatibility.
    """
    output = np.array([sobel(img), sobel(img, mask=mask)])
    names = ['sobel', 'sobel_mask']
    return output, names


# General API for texture map.


METHODS = OrderedDict([
    # Methods that consider an n*n window.
    ('stats', stats_map),
    ('glcm', glcm_map),
    # ('haralick', haralick_map),
    ('lbp', lbp_freq_map),
    ('hog', hog_map),
    ('gabor', gabor_map),
    ('gaboralt', gabor_map_alt),
    # ('moment', moment_map),
    ('haar', haar_map),
    ('sobel', sobel_map),
    ('hu', hu_map),
    ('zernike', zernike_map),
    ('sobel', sobel_map),
    # Methods that consider a minimum bounding box of selected voxels.
    ('stats_mbb', stats_mbb),
    ('glcm_mbb', glcm_mbb),
    # ('haralick_mbb', haralick_mbb),
    # Methods that consider all selected voxels.
    ('stats_all', stats_mbb),  # Use the same mbb function.
    ])


def get_texture_all(img, call, mask):
    feats, names = call(img, mask=mask)
    tmap = np.empty(img.shape + (len(names),), dtype=DTYPE)
    tmap.fill(np.nan)
    tmap[mask, :] = feats
    return tmap, names


def get_texture_mbb(img, call, mask):
    tmap = None
    for i, (img_slice, mask_slice) in enumerate(zip(img, mask)):
        if np.count_nonzero(mask_slice):
            feats, names = call(img_slice, mask=mask_slice)
            if tmap is None:
                tmap = np.empty(img.shape + (len(names),), dtype=DTYPE)
                tmap.fill(np.nan)
            tmap[i, mask_slice, :] = feats
    return tmap, names


def get_texture_map(img, call, winsize, mask, path=None):
    tmap = None
    for i, (img_slice, mask_slice) in enumerate(zip(img, mask)):
        if np.count_nonzero(mask_slice):
            feats, names = call(img_slice, winsize, mask=mask_slice)
            if tmap is None:
                shape = img.shape + (len(names),)
                if path is None:
                    # tmap = np.zeros(shape, dtype=DTYPE)
                    tmap = np.full(shape, np.nan, dtype=DTYPE)
                else:
                    tmap = dwi.hdf5.create_hdf5(path, shape, DTYPE,
                                                fillvalue=np.nan)
            feats = np.rollaxis(feats, 0, 3)
            feats[-mask_slice, :] = np.nan  # Fill background with NaN.
            tmap[i, :, :, :] = feats
    return tmap, names


def get_texture(img, method, winspec, mask, avg=False, path=None):
    """General texture map layer."""
    assert img.ndim == 3, img.ndim
    if mask is not None:
        assert mask.dtype == bool
        assert img.shape == mask.shape, (img.shape, mask.shape)
    call = METHODS[method]
    if winspec == 'all':
        assert method.endswith('_all')
        tmap, names = get_texture_all(img, call, mask)
        assert tmap.shape[-1] == len(names), (tmap.shape[-1], len(names))
        if avg:
            # It's all the same value.
            # Feeding np.nanmean whole image hogs too much memory, circumvent.
            tmap = np.array([np.nanmean(x) for x in np.rollaxis(tmap, -1)],
                            dtype=DTYPE)
            tmap.shape = 1, 1, 1, len(names)
    elif winspec == 'mbb':
        assert method.endswith('_mbb')
        tmap, names = get_texture_mbb(img, call, mask)
        assert tmap.shape[-1] == len(names), (tmap.shape[-1], len(names))
        if avg:
            # Take average of each slice; slice-wise they are the same value.
            # Feeding np.nanmean whole image hogs too much memory, circumvent.
            a = np.empty((len(tmap), len(names)), dtype=DTYPE)
            for s, p in np.ndindex(a.shape):
                a[s, p] = np.nanmean(tmap[s, :, :, p])
            tmap = a
            tmap = np.nanmean(tmap, axis=0)
            tmap.shape = 1, 1, 1, len(names)
    else:
        tmap, names = get_texture_map(img, call, int(winspec), mask, path=path)
        assert tmap.shape[-1] == len(names), (tmap.shape[-1], len(names))
        if avg:
            # Take average of all selected voxels.
            tmap = tmap[mask, :]
            assert tmap.ndim == 2
            tmap = np.mean(tmap, axis=0)
            tmap.shape = 1, 1, 1, len(names)
    names = ['{w}-{n}'.format(w=winspec, n=n) for n in names]
    return tmap, names
