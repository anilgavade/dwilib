import numpy as np
import dicom

# Support for reading DWI data from DICOM files.

def read_files(filenames):
    """Read a bunch of files, each containing a single slice with one b-value,
    and construct a 4d image array.
    
    The slices are sorted simply by their position as it is, assuming it only
    changes in one dimension. In case there are more than one scan of a position
    and a b-value, the files are averaged by mean.
    """
    patient_id = None
    orientation = None
    shape = None
    positions = set()
    bvalues = set()
    slices = dict() # Lists of single slices indexed by (position, bvalue).
    for f in filenames:
        d = dicom.read_file(f)
        patient_id = patient_id or d.PatientID
        if d.PatientID != patient_id:
            raise Exception("Patient ID mismatch.")
        orientation = orientation or d.ImageOrientationPatient
        if d.ImageOrientationPatient != orientation:
            raise Exception("Orientation mismatch.")
        shape = shape or d.pixel_array.shape
        if d.pixel_array.shape != shape:
            raise Exception("Shape mismatch.")
        position = tuple(map(float, d.ImagePositionPatient))
        bvalue = get_bvalue(d)
        pixels = get_pixels(d)
        positions.add(position)
        bvalues.add(bvalue)
        key = (position, bvalue)
        slices.setdefault(key, []).append(pixels)
    positions = sorted(positions)
    bvalues = sorted(bvalues)
    # If any slices are scanned multiple times, use mean.
    for k, v in slices.iteritems():
        slices[k] = np.mean(v, axis=0)
    image = construct_image(slices, positions, bvalues)
    return bvalues, image

def construct_image(slices, positions, bvalues):
    """Construct uniform image array from slice dictionary."""
    w, h = slices.values()[0].shape
    shape = (len(positions), w, h, len(bvalues))
    image = np.empty(shape)
    image.fill(np.nan)
    for k, v in slices.iteritems():
        i = positions.index(k[0])
        j = bvalues.index(k[1])
        image[i,:,:,j] = v
    if np.isnan(np.min(image)):
        raise Exception("Slices missing.")
    return image

def get_bvalue(d):
    """Return image b-value. It may also be stored as frame second."""
    if 'DiffusionBValue' in d:
        r = d.DiffusionBValue
    elif 'FrameTime' in d:
        r = d.FrameTime / 1000
    elif 'FrameReferenceTime' in d:
        r = d.FrameReferenceTime / 1000
    else:
        raise AttributeError('DICOM file does not contain a b-value')
    return r

def get_pixels(d):
    """Return rescaled and clipped pixel array from DICOM object."""
    pixels = d.pixel_array.astype(float)
    pixels = pixels * d.RescaleSlope + d.RescaleIntercept
    lowest = d.WindowCenter - d.WindowWidth/2
    highest = d.WindowCenter + d.WindowWidth/2
    pixels = pixels.clip(lowest, highest, out=pixels)
    return pixels
