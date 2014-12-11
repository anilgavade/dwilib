#!/usr/bin/env python2

"""Find most interesting ROI's in a DWI image."""

import argparse
import glob
import numpy as np

import dwi.dicomfile
import dwi.mask
import dwi.patient
import dwi.util

PARAMS = ['ADCm']

ADCM_MIN = 0.00050680935535585281
ADCM_MAX = 0.0017784125828491648

def parse_args():
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description = __doc__)
    p.add_argument('--verbose', '-v',
            action='count',
            help='increase verbosity')
    p.add_argument('--roidim', metavar='I', nargs=3, type=int, default=[1,5,5],
            help='dimensions of wanted ROI (3 integers; default 1 5 5)')
    p.add_argument('--case', type=int,
            help='case number')
    p.add_argument('--scan',
            help='scan id')
    p.add_argument('--outmask',
            help='output mask file')
    p.add_argument('--outpic',
            help='output graphic file')
    args = p.parse_args()
    return args

def read_subregion(case, scan):
    """Read subregion definition."""
    d = dict(c=case, s=scan)
    s = 'bounding_box_100_10pad/{c}_*_{s}_*.txt'.format(**d)
    paths = glob.glob(s)
    if len(paths) != 1:
        raise Exception('Subregion file confusion: %s' % s)
    subregion = dwi.util.read_subregion_file(paths[0])
    return subregion

def read_dicom_masks(case, scan):
    """Read cancer and normal masks in DICOM format.
    
    Cancer mask path ends with "_ca", normal with "_n". Unless these names
    exist, first two are used. Some cases have a third mask which has cancer,
    they are ignored for now.
    """
    d = dict(c=case, s=scan)
    s = 'dicom_masks/{c}_*_{s}_D_*'.format(**d)
    cancer_path, normal_path, other_paths = None, None, []
    paths = sorted(glob.glob(s), key=str.lower)
    if len(paths) < 2:
        raise Exception('Not all masks were not found: %s' % s)
    for path in paths:
        if not cancer_path and path.lower().endswith('ca'):
            cancer_path = path
        elif not normal_path and path.lower().endswith('n'):
            normal_path = path
        else:
            other_paths.append(path)
    if not cancer_path:
        cancer_path = other_paths.pop(0)
    if not normal_path:
        normal_path = other_paths.pop(0)
    masks = map(dwi.mask.read_dicom_mask, [cancer_path, normal_path])
    return tuple(masks)

def read_image(case, scan, param):
    d = dict(c=case, s=scan, p=param)
    s = 'results_*_combinedDICOM/{c}_*_{s}/{c}_*_{s}_{p}'.format(**d)
    paths = glob.glob(s)
    if len(paths) != 1:
        raise Exception('Image path confusion: %s' % s)
    d = dwi.dicomfile.read_dir(paths[0])
    image = d['image']
    #image = image.squeeze(axis=3) # Remove single subvalue dimension.
    return image

def clip_outliers(img):
    """Clip parameter-specific intensity outliers in-place."""
    for i in range(img.shape[-1]):
        if PARAMS[i].startswith('ADC'):
            img[...,i].clip(0, 0.002, out=img[...,i])
        elif PARAMS[i].startswith('K'):
            img[...,i].clip(0, 2, out=img[...,i])

def read_data():
    samples = dwi.util.read_sample_list('samples_all.txt')
    subwindows = dwi.util.read_subwindows('subwindows.txt')
    patientsinfo = dwi.patient.read_patients_file('patients.txt')
    data = []
    for sample in samples:
        case = sample['case']
        score = dwi.patient.get_patient(patientsinfo, case).score
        for scan in sample['scans']:
            subwindow = subwindows[(case, scan)]
            slice_index = subwindow[0] # Make it zero-based.
            subregion = read_subregion(case, scan)
            cancer_mask, normal_mask = read_dicom_masks(case, scan)
            image = read_image(case, scan, PARAMS[0])
            cropped_cancer_mask = cancer_mask.crop(subregion)
            cropped_normal_mask = normal_mask.crop(subregion)
            cropped_image = dwi.util.crop_image(image, subregion).copy()
            cropped_image = cropped_image[[slice_index],...] # TODO: one slice
            clip_outliers(cropped_image)
            d = dict(case=case, scan=scan, score=score,
                    subwindow=subwindow,
                    slice_index=slice_index,
                    subregion=subregion,
                    cancer_mask=cropped_cancer_mask,
                    normal_mask=cropped_normal_mask,
                    image=cropped_image)
            data.append(d)
    return data

###

def get_score_param(img, param):
    """Return parameter score of given ROI."""
    if param.startswith('ADC'):
        #r = 1-np.mean(img)
        r = 1./(np.mean(img)-0.0008)
        #if np.min(img) < 0.0002:
        #    r = 0
        if (img < ADCM_MIN).any() or (img > ADCM_MAX).any():
            r = 0
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

def find_roi(img, roidim):
    #dims = [(1,1,1)]
    dims = [(1,i,i) for i in range(5, 10)]
    #n_rois = 2000
    n_rois = 70*70/2
    scoremaps = [get_scoremap(img, d, PARAMS, n_rois) for d in dims]
    sum_scoremaps = sum(scoremaps)
    roimap = get_scoremap(sum_scoremaps, roidim, ['score'], 1)
    corner = [axis[0] for axis in roimap[...,0].nonzero()]
    coords = [(x, x+d) for x, d in zip(corner, roidim)]
    d = dict(sum_scoremaps=sum_scoremaps, roi_coords=coords)
    return d

###

def draw_roi(img, pos, color):
    """Draw a rectangle ROI on a layer."""
    y, x = pos
    img[y:y+4:4, x] = color
    img[y:y+4:4, x+4] = color
    img[y, x:x+4:4] = color
    img[y+4, x:x+5:4] = color

def get_roi_layer(img, pos, color):
    """Get a layer with a rectangle ROI for drawing."""
    layer = np.zeros(img.shape + (4,))
    draw_roi(layer, pos, color)
    return layer

def draw(data):
    import matplotlib
    import matplotlib.pyplot as plt
    import pylab as pl

    plt.rcParams['image.cmap'] = 'gray'
    plt.rcParams['image.interpolation'] = 'nearest'
    n_cols, n_rows = 3, 1
    fig = plt.figure(figsize=(n_cols*6, n_rows*6))

    CANCER_COLOR = (1.0, 0.0, 0.0, 1.0)
    NORMAL_COLOR = (0.0, 1.0, 0.0, 1.0)
    AUTO_COLOR = (1.0, 1.0, 0.0, 1.0)

    cancer_pos = (-1, -1)
    normal_pos = (-1, -1)
    distance = -1
    auto_pos = (data['roi_coords'][1][0], data['roi_coords'][2][0])
    if 'cancer_mask' in data:
        cancer_pos = data['cancer_mask'].where()[0][1:3]
        distance = dwi.util.distance(cancer_pos, auto_pos)
    if 'normal_mask' in data:
        normal_pos = data['normal_mask'].where()[0][1:3]

    ax1 = fig.add_subplot(1, n_cols, 1)
    ax1.set_title(PARAMS[0])
    slice_index = 0
    iview = data['image'][slice_index,:,:,0]
    plt.imshow(iview)

    ax2 = fig.add_subplot(1, n_cols, 2)
    ax2.set_title('Calculated score map')
    iview = data['image'][0,...,0]
    pview = data['sum_scoremaps'][0,...,0]
    pview /= pview.max()
    imgray = plt.imshow(iview, alpha=1)
    imjet = plt.imshow(pview, alpha=0.8, cmap='jet')

    ax3 = fig.add_subplot(1, n_cols, 3)
    ax3.set_title('ROIs: %s, %s, distance: %.2f' % (cancer_pos, auto_pos,
            distance))
    iview = data['image'][0,...,0]
    #plt.imshow(iview)
    view = np.zeros(iview.shape + (3,), dtype=float)
    view[...,0] = iview / iview.max()
    view[...,1] = iview / iview.max()
    view[...,2] = iview / iview.max()
    for i, a in enumerate(iview):
        for j, v in enumerate(a):
            if v < ADCM_MIN:
                view[i,j,:] = [0.5, 0, 0]
            elif v > ADCM_MAX:
                view[i,j,:] = [0, 0.5, 0]
    plt.imshow(view)
    if 'cancer_mask' in data:
        plt.imshow(get_roi_layer(iview, cancer_pos, CANCER_COLOR), alpha=0.8)
    if 'normal_mask' in data:
        plt.imshow(get_roi_layer(iview, normal_pos, NORMAL_COLOR), alpha=0.8)
    plt.imshow(get_roi_layer(iview, auto_pos, AUTO_COLOR), alpha=0.8)

    fig.colorbar(imgray, ax=ax1, shrink=0.65)
    fig.colorbar(imjet, ax=ax2, shrink=0.65)
    fig.colorbar(imgray, ax=ax3, shrink=0.65)

    plt.tight_layout()
    filename = 'find_roi2/{case}_{scan}.png'.format(**data)
    plt.savefig(filename, bbox_inches='tight')


args = parse_args()

print 'Reading data...'
data = read_data()

for d in data:
    print
    print d['case'], d['scan'], d['score'], d['subwindow'], d['subregion']
    print d['image'].shape, d['cancer_mask'], d['normal_mask']
    d.update(find_roi(d['image'], args.roidim))
    print 'Optimal ROI: {}'.format(d['roi_coords'])
    draw(d)

#if args.verbose:
#    for i, p in enumerate(params):
#        z, y, x = coords
#        a = img[z[0]:z[1], y[0]:y[1], x[0]:x[1], i]
#        print p, a.min(), a.max(), np.median(a)
#        print dwi.util.fivenum(a.flatten())
#        a = img[..., i]
#        print p, a.min(), a.max(), np.median(a)
#        print dwi.util.fivenum(a.flatten())
