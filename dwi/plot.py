"""Plotting."""

from __future__ import absolute_import, division, print_function

import matplotlib as mpl
import matplotlib.pyplot as plt
import pylab as pl

import dwi.util


VERBOSE = False


# plt.rcParams['image.aspect'] = 'equal'
plt.rcParams['image.cmap'] = 'viridis'
plt.rcParams['image.interpolation'] = 'none'
plt.rcParams['savefig.dpi'] = '300'


def show_images(Imgs, ylabels=None, xlabels=None, vmin=None, vmax=None,
                outfile=None):
    """Show a grid of images. Imgs is an array of columns of rows of images."""
    pl.rcParams['image.cmap'] = 'gray'
    pl.rcParams['image.aspect'] = 'equal'
    pl.rcParams['image.interpolation'] = 'none'
    ncols, nrows = max(len(imgs) for imgs in Imgs), len(Imgs)
    fig = pl.figure(figsize=(ncols*6, nrows*6))
    for i, imgs in enumerate(Imgs):
        for j, img in enumerate(imgs):
            ax = fig.add_subplot(nrows, ncols, i*ncols+j+1)
            ax.set_title('%i, %i' % (i, j))
            if ylabels:
                ax.set_ylabel(ylabels[i])
            if xlabels:
                ax.set_xlabel(xlabels[j])
            pl.imshow(img, vmin=vmin, vmax=vmax)
    pl.tight_layout()
    if outfile:
        if VERBOSE:
            print('Plotting to', path)
        pl.savefig(outfile, bbox_inches='tight')
    else:
        pl.show()
    pl.close()


def plot_rocs(X, Y, params=None, autoflip=False, outfile=None):
    """Plot multiple ROCs."""
    if params is None:
        params = [str(i) for i in range(len(X))]
    assert len(X) == len(Y) == len(params)
    n_rows, n_cols = len(params), 1
    pl.figure(figsize=(n_cols*6, n_rows*6))
    for x, y, param, row in zip(X, Y, params, range(n_rows)):
        fpr, tpr, auc = dwi.util.calculate_roc_auc(y, x, autoflip=autoflip)
        pl.subplot2grid((n_rows, n_cols), (row, 0))
        pl.plot(fpr, tpr, label='ROC curve (area = %0.2f)' % auc)
        pl.plot([0, 1], [0, 1], 'k--')
        pl.xlim([0.0, 1.0])
        pl.ylim([0.0, 1.0])
        pl.xlabel('False Positive rate')
        pl.ylabel('True Positive rate')
        pl.title('%s' % param)
        pl.legend(loc='lower right')
    pl.tight_layout()
    if outfile:
        if VERBOSE:
            print('Plotting to', path)
        pl.savefig(outfile, bbox_inches='tight')
    else:
        pl.show()
    pl.close()


def generate_plots(nrows=1, ncols=1, titles=None, xlabels=None, ylabels=None,
                   path=None):
    """Generate subfigures, yielding each context for plotting."""
    if titles is None:
        titles = [str(x) for x in range(ncols * nrows)]
    assert len(titles) == nrows * ncols
    fig = plt.figure(figsize=(ncols*6, nrows*6))
    for i, title in enumerate(titles):
        ax = fig.add_subplot(nrows, ncols, i+1)
        if title is not None:
            ax.set_title(title)
        if xlabels is not None:
            ax.set_xlabel(xlabels[i])
        if ylabels is not None:
            ax.set_ylabel(ylabels[i])
        yield plt
    plt.tight_layout()
    if path is not None:
        if VERBOSE:
            print('Plotting to', path)
        plt.savefig(path, bbox_inches='tight')
    else:
        plt.show()
    plt.close()
