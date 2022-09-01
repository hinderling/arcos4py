"""Tools for detecting collective events."""

__author__ = """Benjamin Graedel"""
__email__ = "benjamin.graedel@unibe.ch"
__version__ = '0.1.5'

from .binarize_detrend import binData
from .cleandata import clipMeas, interpolation
from .detect_events import detectCollev
from .filter_events import filterCollev
from .stats import calcCollevStats

__all__ = [
    "binData",
    "clipMeas",
    "interpolation",
    "detectCollev",
    "filterCollev",
    "calcCollevStats",
]
