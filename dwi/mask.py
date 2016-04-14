"""Image masks.

Classes Mask and Mask3D represent image masks. They can be used to select
regions, or groups of voxels from images. Class Mask3D contains a multi-slice
boolean array that is set to True in those voxels that are selected. Class Mask
contains a single-slice 2D array and a number denoting the slice index. It was
used with older ASCII mask files -- Mask3D is used with new DICOM masks. The
old ASCII mask files had one-based slice indices, that's why they are used
here, too. If possible, use class Mask3D instead of Mask. However, there is no
writing routine for Mask3D yet. One will be implemented for HDF5 format.

Function read_mask() reads a mask file in ASCII or DICOM format and returns
either a Mask or Mask3D object. A Mask object can be converted to a more
functional Mask3D object with function convert_to_3d(), if you know the number
of slices.

Most often used functions are probably selected(), which returns the selected
image voxels as a flat array; apply_mask(), which sets all unselected image
voxels to zero (or other value); and bounding_box() which returns the
coordinates of the minimum bounding box containing all selected voxels.
"""

from __future__ import absolute_import, division, print_function
import os.path
import re

import numpy as np

import dwi.dicomfile
import dwi.files
import dwi.util


class Mask(object):
    """Single-slice mask for a 3D image. Deprecated, use Mask3D instead.

    Variables
    ---------
    slice : integer
        Slice index, one-based.
    array : ndarray, shape = [height, width], dtype = bool
        Two-dimensional array with selected voxels set to True.
    """
    def __init__(self, slice, array):
        if slice < 1:
            raise ValueError('Invalid slice: {}'.format(slice))
        self.slice = slice  # Slice number, one-based indexing
        self.array = array.astype(bool)  # 2D mask of one slice.

    def __repr__(self):
        return repr((self.slice, self.array.shape))

    def __str__(self):
        return repr(self)

    def get_subwindow(self, coordinates, onebased=True):
        """Get a view of a specific subwindow."""
        if onebased:
            coordinates = [i-1 for i in coordinates]  # One-based indexing.
        z0, z1, y0, y1, x0, x1 = coordinates
        assert z0 == z1-1, 'Multi-slice subwindow of single-slice mask.'
        slice = self.slice - z0
        array = self.array[y0:y1, x0:x1]
        return Mask(slice, array)

    def n_selected(self):
        """Return the number of selected voxels."""
        return np.count_nonzero(self.array)

    def selected(self, array):
        """Return selected voxels of an array as a flat array."""
        if array.ndim == self.array.ndim:
            return array[self.array]
        else:
            return array[self.slice-1, self.array]

    def selected_slice(self, a):
        """Return the selected slice of an array."""
        indices = self.selected_slices()
        if len(indices) != 1:
            raise Exception('Exactly one slice not selected.')
        return a[indices[0]]

    def selected_slices(self):
        """Return zero-based slice indices that have voxels selected."""
        return [self.slice - 1]

    def convert_to_3d(self, n_slices):
        """Convert a 2D mask to a 3D mask with given number of slices."""
        a = np.zeros((n_slices,) + self.array.shape)
        a[self.slice-1, :, :] = self.array
        return Mask3D(a)

    def write(self, filename):
        """Write mask as an ASCII file."""
        def line_to_text(line):
            return ''.join(str(x) for x in line)

        def mask_to_text(mask):
            return '\n'.join(line_to_text(x) for x in mask)

        with open(filename, 'w') as f:
            f.write('slice: %s\n' % self.slice)
            f.write(mask_to_text(self.array.astype(int)))


class Mask3D(object):
    """Multi-slice mask for a 3D image.

    Variables
    ---------
    array : ndarray, shape = [depth, height, width], dtype = bool
        Array with selected voxels set to True.
    """
    def __init__(self, a):
        if a.ndim != 3:
            raise ValueError('Invalid mask dimensionality: {}'.format(a.shape))
        self.array = a.astype(bool)

    def __repr__(self):
        return repr(self.array.shape)

    def __str__(self):
        return repr(self)

    def shape(self):
        """Return mask shape."""
        return self.array.shape

    def n_selected(self):
        """Return number of selected voxels."""
        return np.count_nonzero(self.array)

    def selected(self, a):
        """Return the selected voxels of an array as a flat array."""
        return a[self.array]

    def selected_slices(self):
        """Return slice indices that have voxels selected."""
        return np.unique(self.array.nonzero()[0])

    def selected_slice(self, a):
        """Return the selected slice of an array."""
        indices = self.selected_slices()
        if len(indices) != 1:
            raise Exception('Exactly one slice not selected.')
        return a[indices[0]]

    def max_slices(self):
        """Return slices with maximum number of selected voxels."""
        numbers = [np.count_nonzero(a) for a in self.array]
        max_number = max(numbers)
        indices = [i for i, n in enumerate(numbers) if n == max_number]
        return indices

    def get_subwindow(self, coordinates, onebased=True):
        """Get a view of a specific subwindow."""
        if onebased:
            coordinates = [i-1 for i in coordinates]
        z0, z1, y0, y1, x0, x1 = coordinates
        array = self.array[z0:z1, y0:y1, x0:x1]
        return Mask3D(array)

    def apply_mask(self, a, value=0):
        """Cover masked voxels of an array by zero (or other value)."""
        copy = a.copy()
        copy[-self.array, ...] = value
        return copy

    def where(self):
        """Return indices of selected voxels."""
        return np.argwhere(self.array)

    def crop(self, subwindow, onebased=False):
        """Return a copied subwindow."""
        a = dwi.util.crop_image(self.array, subwindow, onebased).copy()
        return Mask3D(a)

    def bounding_box(self, pad=0):
        """Return the minimum bounding box with optional padding.

        Parameter pad can be a tuple of each dimension or a single number. It
        can contain infinity for maximum padding.
        """
        return dwi.util.bounding_box(self.array, pad)

    def mbb_equals_selection(self):
        """Tell whether minimum bounding box equals selected voxels."""
        mbb = self.bounding_box()
        mbb_shape = [b - a for a, b in mbb]
        mbb_size = np.prod(mbb_shape)
        r = (mbb_size == self.n_selected())
        return r


def load_ascii(filename):
    """Read a mask as an ASCII file."""
    p = re.compile(r'(\w+)\s*:\s*(.*)')
    slice = 1
    arrays = []
    for line in dwi.files.valid_lines(filename):
        m = p.match(line)
        if m:
            if m.group(1) == 'slice':
                slice = int(m.group(2))
        elif line[0] == '0' or line[0] == '1':
            a = np.array(list(line), dtype=np.int)
            arrays.append(a)
    if arrays:
        return Mask(slice, np.array(arrays))
    else:
        raise Exception('No mask found in %s' % filename)


def read_mask(path):
    """Read a mask."""
    if path.lower().endswith('.mask') and not os.path.isdir(path):
        return load_ascii(path)  # Old 2D ASCII mask.
    else:
        return Mask3D(dwi.files.read_mask(path))
