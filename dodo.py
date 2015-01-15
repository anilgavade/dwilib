"""PyDoIt file for automating tasks."""

import glob
import os
from os.path import dirname

from doit import get_var
#from doit.tools import Interactive
from doit.tools import create_folder
#from doit.tools import result_dep

import dwi.util

"""
Backends:
dbm: (default) It uses python dbm module.
json: Plain text using a json structure, it is slow but good for debugging.
sqlite3: (experimental) very slow implementation, support concurrent access.
"""

DOIT_CONFIG = {
    'backend': 'sqlite3',
    'default_tasks': [],
    'verbosity': 2,
    }

DWILIB = '~/src/dwilib/tools'
PMAP = DWILIB+'/pmap.py'
ANON = DWILIB+'/anonymize_dicom.py'
FIND_ROI = DWILIB+'/find_roi.py'
COMPARE_MASKS = DWILIB+'/compare_masks.py'
SELECT_VOXELS = DWILIB+'/select_voxels.py'
MODELS = 'Si SiN Mono MonoN Kurt KurtN Stretched StretchedN '\
        'Biexp BiexpN'.split()

SAMPLELIST = get_var('samplelist', 'all') # Sample list (train, test, etc)
SAMPLELIST_FILE = 'samples_%s.txt' % SAMPLELIST
SAMPLES = dwi.util.read_sample_list(SAMPLELIST_FILE)
SUBWINDOWS = dwi.util.read_subwindows('subwindows.txt')

# Common functions

def subwindow_to_str(subwindow):
    return ' '.join(map(str, subwindow))

def fit_cmd(model, subwindow, infiles, outfile):
    d = dict(prg=PMAP,
            m=model,
            sw=subwindow_to_str(subwindow),
            i=' '.join(infiles),
            o=outfile,
            )
    s = '{prg} -m {m} -s {sw} -d {i} -o {o}'.format(**d)
    return s

# Tasks

#def task_anonymize():
#    """Anonymize imaging data."""
#    files = glob.glob('dicoms/*/DICOMDIR') + glob.glob('dicoms/*/DICOM/*')
#    files.sort()
#    for f in files:
#        cmd = '{prg} -v -i {f}'.format(prg=ANON, f=f)
#        yield {
#                'name': f,
#                'actions': [cmd],
#                'file_dep': [f],
#                }

def task_fit():
    """Fit models to imaging data."""
    for case, scan in SUBWINDOWS.keys():
        subwindow = SUBWINDOWS[(case, scan)]
        d = dict(c=case, s=scan)
        infiles = sorted(glob.glob('dicoms/{c}_*_hB_{s}*/DICOM/*'.format(**d)))
        if len(infiles) == 0:
            continue
        for model in MODELS:
            d['m'] = model
            outfile = 'pmaps/pmap_{c}_{s}_{m}.txt'.format(**d)
            cmd = fit_cmd(model, subwindow, infiles, outfile)
            yield {
                    'name': '{c}_{s}_{m}'.format(**d),
                    'actions': [(create_folder, [dirname(outfile)]),
                            cmd],
                    'file_dep': infiles,
                    'targets': [outfile],
                    'clean': True,
                    }

def task_find_roi():
    """Find a cancer ROI automatically."""
    for sample in SAMPLES:
        case = sample['case']
        for scan in sample['scans']:
            d = dict(prg=FIND_ROI, sl=SAMPLELIST_FILE, c=case, s=scan)
            outpath_mask = 'masks_auto/{c}_{s}_auto.mask'.format(**d)
            outpath_fig = 'find_roi_images/{c}_{s}.png'.format(**d)
            file_deps = [SAMPLELIST_FILE]
            file_deps += glob.glob('masks_prostate/{c}_*_{s}_*/*'.format(**d))
            file_deps += glob.glob('masks_rois/{c}_*_{s}_*/*'.format(**d))
            cmd = '{prg} --samplelist {sl} --cases {c} --scans {s}'.format(**d)
            yield {
                    'name': '{c}_{s}'.format(**d),
                    'actions': [(create_folder, [dirname(outpath_mask)]),
                                (create_folder, [dirname(outpath_fig)]),
                            cmd],
                    'file_dep': file_deps,
                    'targets': [outpath_mask, outpath_fig],
                    'clean': True,
                    }

## Deprecated.
#def task_compare_masks():
#    """Compare ROI masks."""
#    for case, scan in SUBWINDOWS.keys():
#        subwindow = SUBWINDOWS[(case, scan)]
#        d = dict(prg=COMPARE_MASKS,
#                c=case,
#                s=scan,
#                w=subwindow_to_str(subwindow),
#                )
#        #file1 = 'masks/{c}_{s}_ca.mask'.format(**d)
#        file1 = glob.glob('masks/{c}_{s}_1_*.mask'.format(**d))[0]
#        file2 = 'masks_auto/{c}_{s}_auto.mask'.format(**d)
#        outfile = 'roi_comparison/{c}_{s}.txt'.format(**d)
#        d['f1'] = file1
#        d['f2'] = file2
#        d['o'] = outfile
#        cmd = '{prg} -s {w} {f1} {f2} > {o}'.format(**d)
#        if not os.path.exists(file1):
#            print 'Missing mask file %s' % file1
#            continue
#        yield {
#                'name': '{c}_{s}'.format(**d),
#                'actions': [(create_folder, [dirname(outfile)]),
#                        cmd],
#                'file_dep': [file1, file2],
#                'targets': [outfile],
#                'clean': True,
#                }

def get_task_select_roi(case, scan, model, param, masktype, subwindow=None):
    d = dict(c=case, s=scan, m=model, p=param, mt=masktype, sw=subwindow)
    maskpath = 'masks_{mt}/{c}_{s}_{mt}.mask'.format(**d)
    s = 'results_{m}_combinedDICOM/{c}_*_{s}/{c}_*_{s}_{p}'.format(**d)
    inpath = glob.glob(s)[0]
    outpath = 'rois_{mt}/{c}_x_x_{s}_{m}_{p}_{mt}.txt'.format(**d)
    args = [SELECT_VOXELS]
    #args += ['-v']
    if subwindow:
        args += ['-s %s' % subwindow_to_str(subwindow)]
    args += ['-m %s' % maskpath]
    args += ['-i "%s"' % inpath]
    args += ['-o "%s"' % outpath]
    cmd = ' '.join(args)
    return {
            'name': '{c}_{s}'.format(**d),
            'actions': [(create_folder, [dirname(outpath)]),
                    cmd],
            'file_dep': [maskpath],
            'targets': [outpath],
            'clean': True,
            }

def task_select_roi_cancer():
    """Select cancer ROIs from the pmap DICOMs."""
    for sample in SAMPLES:
        for scan in sample['scans']:
            case = sample['case']
            masktype = 'cancer'
            yield get_task_select_roi(case, scan, 'Mono', 'ADCm', masktype)

def task_select_roi_auto():
    """Select automatic ROIs from the pmap DICOMs."""
    for sample in SAMPLES:
        for scan in sample['scans']:
            case = sample['case']
            masktype = 'auto'
            yield get_task_select_roi(case, scan, 'Mono', 'ADCm', masktype)
