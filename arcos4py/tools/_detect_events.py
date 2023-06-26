"""Module to track and detect collective events.

Example:
    >>> from arcos4py.tools import detectCollev
    >>> ts = detectCollev(data)
    >>> events_df = ts.run()
"""
from __future__ import annotations

import functools
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Generator, Union

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from hdbscan import HDBSCAN
from kneed import KneeLocator
from scipy.spatial import KDTree

# from scipy.spatial.distance import cdist
# from scipy.optimize import linear_sum_assignment
from sklearn.cluster import DBSCAN
from tqdm import tqdm

AVAILABLE_CLUSTERING_METHODS = ['dbscan', 'hdbscan']

# implement a new event tracking algorithm that will be able to track events from images directly
# the current implementation in the arcos4py package is only able to track events from dataframes
# the new implementation will be able to track events from both dataframes and images
# by implementing the tracking in a generator style with a linker function
# it should also reduce the memory usage of the algorithm


def _group_data(frame_data):
    unique_frame_vals, unique_frame_indices = np.unique(frame_data, axis=0, return_index=True)
    return unique_frame_vals.astype(np.int32), unique_frame_indices[1:]


def _dbscan(x: np.ndarray, eps: float, minClSz: int, n_jobs: int = 1) -> np.ndarray:
    """Dbscan method to run and merge the cluster id labels to the original dataframe.

    Arguments:
        x (np.ndarray): With unique frame and position columns.

    Returns:
        list[np.ndarray]: list with added collective id column detected by DBSCAN.
    """
    if x.size:
        db_array = DBSCAN(eps=eps, min_samples=minClSz, algorithm="kd_tree", n_jobs=n_jobs).fit(x)
        cluster_labels = db_array.labels_
        cluster_list = np.where(cluster_labels > -1, cluster_labels + 1, np.nan)
        return cluster_list

    return np.empty((0, 0))


def _hdbscan(
    x: np.ndarray, eps: float, minClSz: int, min_samples: int, cluster_selection_method: str, n_jobs: int = 1
) -> np.ndarray:
    """Hdbscan method to run and merge the cluster id labels to the original dataframe.

    Arguments:
        x (np.ndarray): With unique frame and position columns.

    Returns:
        list[np.ndarray]: list with added collective id column detected by HDBSCAN.
    """
    if x.size:
        db_array = HDBSCAN(
            min_cluster_size=minClSz,
            min_samples=min_samples,
            cluster_selection_epsilon=eps,
            cluster_selection_method=cluster_selection_method,
            core_dist_n_jobs=n_jobs,
        ).fit(x)
        cluster_labels = db_array.labels_
        cluster_list = np.where(cluster_labels > -1, cluster_labels + 1, np.nan)
        return cluster_list

    return np.empty((0, 0))


# @profile
def brute_force_linking(
    cluster_labels,
    cluster_coordinates,
    memory_cluster_labels,
    memory_kdtree: KDTree,
    propagation_threshold,
    epsPrev,
    max_cluster_label,
    n_jobs,
):
    # calculate nearest neighbour between previoius and current frame
    nn_dist, nn_indices = memory_kdtree.query(cluster_coordinates, k=1, workers=n_jobs)
    prev_cluster_labels = memory_cluster_labels[nn_indices]
    prev_cluster_labels_eps = prev_cluster_labels[(nn_dist <= epsPrev)]
    # only continue if neighbours
    # were detected within eps distance
    if prev_cluster_labels_eps.size < propagation_threshold:
        max_cluster_label += 1
        return np.repeat(max_cluster_label, cluster_labels.size), max_cluster_label

    prev_clusternbr_eps_unique = np.unique(prev_cluster_labels_eps, return_index=False)

    if prev_clusternbr_eps_unique.size == 0:
        max_cluster_label += 1
        return np.repeat(max_cluster_label, cluster_labels.size), max_cluster_label

    # propagate cluster id from previous frame
    cluster_labels = prev_cluster_labels
    return cluster_labels, max_cluster_label


def linear_assignment_linking(
    cluster_coordinates,
    memory_coordinates,
    memory_cluster_labels,
    max_cluster_label,
    epsPrev,
):
    raise NotImplementedError


@dataclass
class memory:
    n_timepoints: int = 1
    coordinates: list[np.ndarray] = field(default_factory=lambda: [], init=False)
    prev_cluster_ids: list[np.ndarray] = field(default_factory=lambda: [], init=False)
    max_prev_cluster_id: int = 0

    def update(self, new_coordinates, new_cluster_ids):
        if len(self.coordinates) == self.n_timepoints:
            self.coordinates.pop(0)
            self.prev_cluster_ids.pop(0)
        self.coordinates.append(new_coordinates)
        self.prev_cluster_ids.append(new_cluster_ids)

    @property
    def all_coordinates(self):
        if len(self.coordinates) > 1:
            return np.concatenate(self.coordinates)
        return self.coordinates[0]

    @property
    def all_cluster_ids(self):
        if len(self.prev_cluster_ids) > 1:
            return np.concatenate(self.prev_cluster_ids)
        return self.prev_cluster_ids[0]


# this class will act as the linker between frames
# it will store the previous n frames and propagate cluster ids from those to the current frame if they are close enough
# it will also update the memory with the current frame and remove the oldest frame
# memory will be a list of arrays, each array containing the cluster ids for each point in the frame
class Linker:
    def __init__(
        self,
        eps: float = 1,
        epsPrev: int | None = None,
        minClSz: int = 1,
        minSamples: int = 1,
        clusteringMethod: str | Callable = "dbscan",
        propagationThreshold: int = 1,
        nPrev: int = 1,
        nJobs: int = 1,
    ):
        self._memory = memory(n_timepoints=nPrev)
        self._nn_tree: KDTree | None = None
        self.propagation_threshold = propagationThreshold
        if epsPrev is None:
            self.epsPrev = eps
        else:
            self.epsPrev = epsPrev
        self.n_jobs = nJobs
        self._validate_input(eps, epsPrev, minClSz, minSamples, clusteringMethod, propagationThreshold, nPrev, nJobs)

        self.event_ids = np.empty((0, 0))
        self.max_prev_event_id = 0

        if hasattr(clusteringMethod, '__call__'):  # check if it's callable
            self.clustering_function = clusteringMethod
        else:
            if clusteringMethod == "dbscan":
                self.clustering_function = functools.partial(_dbscan, eps=eps, minClSz=minClSz)
            elif clusteringMethod == "hdbscan":
                self.clustering_function = functools.partial(
                    _hdbscan, eps=eps, minClSz=minClSz, min_samples=minSamples, cluster_selection_method='leaf'
                )
            else:
                raise ValueError(
                    f'Clustering method must be either in {AVAILABLE_CLUSTERING_METHODS} or a callable with data as the only argument an argument'  # noqa E501
                )

    def _validate_input(self, eps, epsPrev, minClSz, minSamples, clusteringMethod, propagationThreshold, nPrev, nJobs):
        if not isinstance(eps, (int, float, str)):
            raise ValueError(f"eps must be a number or None, got {eps}")
        if not isinstance(epsPrev, (int, type(None))):
            raise ValueError(f"epsPrev must be a number or None, got {epsPrev}")
        for i in [minClSz, minSamples, propagationThreshold, nPrev, nJobs]:
            if not isinstance(i, int):
                raise ValueError(f"{i} must be an int, got {i}")
        if not isinstance(clusteringMethod, str):
            raise ValueError(f"clusteringMethod must be a string, got {clusteringMethod}")

    # @profile
    def _clustering(self, x):
        if x.size == 0:
            return np.empty((0,), dtype=np.int64), x, np.empty((0, 1), dtype=bool)
        clusters = self.clustering_function(x)
        nanrows = np.isnan(clusters)
        return clusters[~nanrows], x[~nanrows], nanrows

    # @profile
    def _link_next_cluster(self, cluster: np.ndarray, cluster_coordinates: np.ndarray):
        linked_clusters, max_cluster_label = brute_force_linking(
            cluster_labels=cluster,
            cluster_coordinates=cluster_coordinates,
            memory_cluster_labels=self._memory.all_cluster_ids,
            memory_kdtree=self._nn_tree,
            propagation_threshold=self.propagation_threshold,
            epsPrev=self.epsPrev,
            max_cluster_label=self._memory.max_prev_cluster_id,
            n_jobs=self.n_jobs,
        )

        self._memory.max_prev_cluster_id = max_cluster_label

        return linked_clusters

    def _update_tree(self, coords):
        self._nn_tree = KDTree(coords)

    def _group_by_clusterid(self, cluster_ids, coordinates):
        cluster_ids_sort_key = np.argsort(cluster_ids)
        cluster_ids_sorted = cluster_ids[cluster_ids_sort_key]
        coordinates_sorted = coordinates[cluster_ids_sort_key]
        _, group_by_cluster_id = _group_data(cluster_ids_sorted)
        grouped_clusters = np.split(cluster_ids_sorted, group_by_cluster_id)
        grouped_coordinates = np.split(coordinates_sorted, group_by_cluster_id)
        return cluster_ids_sort_key, grouped_clusters, grouped_coordinates

    # @profile
    def link(self, input_coordinates: np.ndarray):
        cluster_ids, coordinates, nanrows = self._clustering(input_coordinates)
        # check if first frame
        if not len(self._memory.prev_cluster_ids):
            linked_cluster_ids = self._update_id_empty(cluster_ids)
        # check if anything was detected in current or previous frame
        elif cluster_ids.size == 0 or self._memory.all_cluster_ids.size == 0:
            linked_cluster_ids = self._update_id_empty(cluster_ids)
        else:
            linked_cluster_ids = self._update_id(cluster_ids, coordinates)

        # update memory
        self._memory.update(new_coordinates=coordinates, new_cluster_ids=linked_cluster_ids)

        event_ids = np.full_like(nanrows, -1, dtype=np.int64)
        event_ids[~nanrows] = linked_cluster_ids
        self.event_ids = event_ids

    # @profile
    def _update_id(self, cluster_ids, coordinates):
        memory_coordinates = self._memory.all_coordinates
        self._update_tree(memory_coordinates)
        # group by cluster id
        cluster_ids_sort_key, grouped_clusters, grouped_coordinates = self._group_by_clusterid(cluster_ids, coordinates)

        # do linking
        linked_cluster_ids = [
            self._link_next_cluster(cluster, cluster_coordinates)
            for cluster, cluster_coordinates in zip(grouped_clusters, grouped_coordinates)
        ]
        # restore original data order
        revers_sort_key = np.argsort(cluster_ids_sort_key)
        linked_cluster_ids = np.concatenate(linked_cluster_ids)[revers_sort_key]
        return linked_cluster_ids

    def _update_id_empty(self, cluster_ids):
        linked_cluster_ids = cluster_ids + self._memory.max_prev_cluster_id
        try:
            self._memory.max_prev_cluster_id = np.nanmax(linked_cluster_ids)
        except ValueError:
            pass
        return linked_cluster_ids


# this class will act as the abstract base class for the event tracker
# it will implement the track method which returns a generator that can be looped over
# the calsses DataFrameEventTracker and ArrayEventTracker will inherit from this class
# and implement the abstract track method
class BaseTracker(ABC):
    def __init__(self, linker: Linker):
        self.linker = linker

    @abstractmethod
    def track_iteration(self, data):
        pass

    @abstractmethod
    def track(self, data: Union[pd.DataFrame, np.ndarray]) -> Generator:
        pass


# this class will implement event tracking for dataframes, this is the current implementatoin in the arcos4py package
# it will also do input validation and filtering of the data
class DataFrameTracker(BaseTracker):
    def __init__(
        self,
        linker: Linker,
        coordinates_column: list[str],
        frame_column: str,
        id_column: str | None = None,
        bin_meas_column: str | None = None,
        collid_column: str = 'clTrackID',
    ):
        super().__init__(linker)
        self.coordinates_column = coordinates_column
        self.frame_column = frame_column
        self.id_column = id_column
        self.bin_meas_column = bin_meas_column
        self.collid_column = collid_column
        self._validate_input(coordinates_column, frame_column, id_column, bin_meas_column, collid_column)

    def _validate_input(
        self,
        coordinates_column: list[str],
        frame_column: str,
        id_column: str | None,
        bin_meas_column: str | None,
        collid_column: str,
    ):
        necessray_cols: list[Any] = [frame_column, collid_column]
        necessray_cols.extend(coordinates_column)
        optional_cols: list[Any] = [id_column, bin_meas_column]

        for col in necessray_cols:
            if not isinstance(col, str):
                raise TypeError(f'Column names must be of type str, {col} given.')

        for col in optional_cols:
            if not isinstance(col, (str, type(None))):
                raise TypeError(f'Column names must be of type str or None, {col} given.')

    def _select_necessary_columns(
        self,
        data: pd.DataFrame,
        pos_col: list[str],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Select necessary input colums from input data and returns them as numpy arrays.

        Arguments:
            data (DataFrame): Containing necessary columns.
            frame_col (str): Name of the frame/timepoint column in the dataframe.
            pos_col (list): string representation of position columns in data.

        Returns:
            np.ndarray, np.ndarray: Filtered columns necessary for calculation.
        """
        pos_columns_np = data[pos_col].to_numpy()
        if pos_columns_np.ndim == 1:
            pos_columns_np = pos_columns_np[:, np.newaxis]
        return pos_columns_np

    def _sort_input(self, x: pd.DataFrame, frame_col: str, object_id_col: str | None) -> pd.DataFrame:
        """Sorts the input dataframe according to the frame column and track id column if available."""
        if object_id_col:
            x = x.sort_values([frame_col, object_id_col]).reset_index(drop=True)
        else:
            x = x.sort_values([frame_col]).reset_index(drop=True)
        return x

    def _filter_active(self, data: pd.DataFrame, bin_meas_col: Union[str, None]) -> pd.DataFrame:
        """Selects rows with binary value of greater than 0.

        Arguments:
            data (DataFrame): Dataframe containing necessary columns.
            bin_meas_col (str|None): Either name of the binary column or None if no such column exists.

        Returns:
            DataFrame: Filtered pandas DataFrame.
        """
        if bin_meas_col is not None:
            data = data[data[bin_meas_col] > 0]
        return data

    # @profile
    def track_iteration(self, x: pd.DataFrame):
        x_filtered = self._filter_active(x, self.bin_meas_column)

        coordinates_data = self._select_necessary_columns(
            x_filtered,
            self.coordinates_column,
        )
        self.linker.link(coordinates_data)

        if self.collid_column in x.columns:
            df_out = x_filtered.drop(columns=[self.collid_column]).copy()
        else:
            df_out = x_filtered.copy()
        event_ids = self.linker.event_ids

        if not event_ids.size:
            df_out[self.collid_column] = 0
            return df_out

        df_out[self.collid_column] = self.linker.event_ids
        return df_out

    def track(self, x: pd.DataFrame) -> Generator:
        if x.empty:
            raise ValueError('Input is empty')
        x_sorted = self._sort_input(x, frame_col=self.frame_column, object_id_col=self.id_column)

        for t in range(x_sorted[self.frame_column].max() + 1):
            x_frame = x_sorted.query(f'{self.frame_column} == {t}')
            x_tracked = self.track_iteration(x_frame)
            yield x_tracked


# this class will implement event tracking for arrays,
# this is the new implementation that will be added to the arcos4py package
# it will also do input validation and filtering of the data
# the purpose of this is to track data directly from images without having to convert them to dataframes first
# it will implement an image_parser method and the track method
class ImageTracker(BaseTracker):
    def __init__(self, linker: Linker):
        super().__init__(linker)

    def _image_to_coordinates(self, image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Converts a 2d image series to input that can be accepted by the ARCOS event detection function
        with columns for x, y, and intensity.
        Arguments:
            image (np.ndarray): Image to convert. Will be coerced to int32.
            dims (str): String of dimensions in order. Default is "TXY". Possible values are "T", "X", "Y", and "Z".
        Returns (tuple[np.ndarray, np.ndarray, np.ndarray]): Tuple of arrays with coordinates, measurements,
            and frame numbers.
        """
        # convert to int16
        image = image.astype(np.uint16)

        coordinates_array = np.moveaxis(np.indices(image.shape), 0, len(image.shape)).reshape((-1, len(image.shape)))
        meas_array = image.flatten()

        return coordinates_array, meas_array

    def _filter_active(self, pos_data: np.ndarray, bin_meas_data: np.ndarray) -> tuple[np.ndarray]:
        """Selects rows with binary value of greater than 0.

        Arguments:
            frame_data (np.ndarray): frame column as a numpy array.
            pos_data (np.ndarray): positions/coordinate columns as a numpy array.
            bin_meas_data (np.ndarray): binary measurement column as a numpy array.

        Returns:
            np.ndarray, np.ndarray, np.ndarray: Filtered numpy arrays.
        """
        if bin_meas_data is not None:
            active = np.argwhere(bin_meas_data > 0).flatten()
            pos_data = pos_data[active]
        return pos_data

    def _coordinates_to_image(self, x, pos_data, tracked_events):
        # create empty image
        out_img = np.zeros_like(x, dtype=np.uint16)
        if tracked_events.size == 0:
            return out_img
        tracked_events_mask = tracked_events > 0

        pos_data = pos_data[tracked_events_mask].astype(np.uint16)
        n_dims = pos_data.shape[1]

        # Raise an error if dimension is zero
        if n_dims == 0:
            raise ValueError("Dimension of input array not supported.")

        # Create an indexing tuple
        indices = tuple(pos_data[:, i] for i in range(n_dims))

        # Index into out_img using the indexing tuple
        out_img[indices] = tracked_events[tracked_events_mask]

        return out_img

    def track_iteration(self, x: np.ndarray):
        coordinates_data, meas_data = self._image_to_coordinates(x)
        coordinates_data_filtered = self._filter_active(coordinates_data, meas_data)

        self.linker.link(coordinates_data_filtered)

        tracked_events = self.linker.event_ids
        out_img = self._coordinates_to_image(x, coordinates_data_filtered, tracked_events)

        return out_img

    def track(self, x: np.ndarray, dims: str = "TXY") -> Generator:
        available_dims = ["T", "X", "Y", "Z"]
        dims_list = list(dims.upper())

        # check input
        for i in dims_list:
            if i not in dims_list:
                raise ValueError(f"Invalid dimension {i}. Must be 'T', 'X', 'Y', or 'Z'.")

        if len(dims_list) > len(set(dims_list)):
            raise ValueError("Duplicate dimensions in dims.")

        if len(dims_list) != x.ndim:
            raise ValueError(
                f"Length of dims must be equal to number of dimensions in image. Image has {x.ndim} dimensions."
            )

        dims_dict = {i: dims_list.index(i) for i in available_dims if i in dims_list}

        # reorder image so T is first dimension
        image_reshaped = np.moveaxis(x, dims_dict["T"], 0)

        for x_frame in image_reshaped:
            x_tracked = self.track_iteration(x_frame)
            yield x_tracked


# this function will be used to track events from dataframes
# it will be the public function that the user will call and produce a progress bar using tqdm
def track_events_dataframe(
    X: pd.DataFrame,
    coordinates_column,
    frame_column,
    id_column,
    bin_meas_colum,
    collid_column,
    eps,
    epsPrev,
    minClSz,
    minSamples,
    clusteringMethod,
    propagationThreshold,
    nPrev,
    nJobs,
):
    linker = Linker(eps, epsPrev, minClSz, minSamples, clusteringMethod, propagationThreshold, nPrev, nJobs)
    tracker = DataFrameTracker(linker, coordinates_column, frame_column, id_column, bin_meas_colum, collid_column)
    return pd.concat([timepoint for timepoint in tqdm(tracker.track(X), total=X[frame_column].nunique())]).reset_index(
        drop=True
    )


# this function will be used to track events from images
# it will be the public function that the user will call and produce a progress bar using tqdm
def track_events_image(
    X: np.ndarray,
    eps=1,
    epsPrev=None,
    minClSz=1,
    minSamples=1,
    clusteringMethod="dbscan",
    propagationThreshold=1,
    nPrev=1,
    dims="TXY",
    nJobs=1,
):
    linker = Linker(eps, epsPrev, minClSz, minSamples, clusteringMethod, propagationThreshold, nPrev, nJobs)
    tracker = ImageTracker(linker)
    # find indices of T in dims
    T_index = dims.upper().index("T")
    return np.stack([timepoint for timepoint in tqdm(tracker.track(X, dims), total=X.shape[T_index])], axis=T_index)


class detectCollev:
    def __init__(
        self,
        input_data: Union[pd.DataFrame, np.ndarray],
        eps: float = 1,
        epsPrev: Union[float, None] = None,
        minClSz: int = 1,
        nPrev: int = 1,
        posCols: list = ["x"],
        frame_column: str = 'time',
        id_column: Union[str, None] = None,
        bin_meas_column: Union[str, None] = 'meas',
        clid_column: str = 'clTrackID',
        dims: str = "TXY",
        method: str = "dbscan",
        min_samples: int = 1,
        cluster_selection_method: str = "leaf",
        n_jobs: int = 1,
        show_progress: bool = True,
    ) -> None:
        self.input_data = input_data
        self.eps = eps
        self.epsPrev = epsPrev
        self.minClSz = minClSz
        self.nPrev = nPrev
        self.posCols = posCols
        self.frame_column = frame_column
        self.id_column = id_column
        self.bin_meas_column = bin_meas_column
        self.clid_column = clid_column
        self.dims = dims
        self.method = method
        self.min_samples = min_samples
        self.cluster_selection_method = cluster_selection_method
        self.n_jobs = n_jobs
        self.show_progress = show_progress
        warnings.warn(
            "This class is deprecated and will be removed a future release, use the track_events_dataframe or track_events_image functions directly.",  # noqa: E501
            DeprecationWarning,
        )

    def run(self, copy: bool = True) -> pd.DataFrame:
        if isinstance(self.input_data, pd.DataFrame):
            if copy:
                self.input_data = self.input_data.copy()
            return track_events_dataframe(
                X=self.input_data,
                coordinates_column=self.posCols,
                frame_column=self.frame_column,
                id_column=self.id_column,
                bin_meas_colum=self.bin_meas_column,
                collid_column=self.clid_column,
                eps=self.eps,
                epsPrev=self.epsPrev,
                minClSz=self.minClSz,
                minSamples=self.min_samples,
                clusteringMethod=self.method,
                propagationThreshold=1,
                nPrev=self.nPrev,
                nJobs=self.n_jobs,
            )
        elif isinstance(self.input_data, np.ndarray):
            if copy:
                self.input_data = np.copy(self.input_data)
            return track_events_image(
                X=self.input_data,
                eps=self.eps,
                epsPrev=self.epsPrev,
                minClSz=self.minClSz,
                minSamples=self.min_samples,
                clusteringMethod=self.method,
                propagationThreshold=1,
                nPrev=self.nPrev,
                dims=self.dims,
                nJobs=self.n_jobs,
            )


def _nearest_neighbour_eps(
    X: np.ndarray,
    nbr_nearest_neighbours: int = 1,
):
    kdB = KDTree(data=X)
    nearest_neighbours, indices = kdB.query(X, k=nbr_nearest_neighbours)
    return nearest_neighbours[:, 1:]


def estimate_eps(
    data: pd.DataFrame,
    method: str = 'kneepoint',
    pos_cols: list[str] = ['x,y'],
    frame_col: str = 't',
    n_neighbors: int = 5,
    plot: bool = True,
    plt_size: tuple[int, int] = (5, 5),
    max_samples=50_000,
    **kwargs: dict,
):
    """Estimates eps parameter in DBSCAN.

    Estimates the eps parameter for the DBSCAN clustering method, as used by ARCOS,
    by calculating the nearest neighbour distances for each point in the data.
    N_neighbours should be chosen to match the minimum point size in DBSCAN
    or the minimum clustersize in detect_events respectively.
    The method argument determines how the eps parameter is estimated.
    'kneepoint' estimates the knee of the nearest neighbour distribution.
    'mean' and 'median' return (by default) 1.5 times
    the mean or median of the nearest neighbour distances respectively.

    Arguments:
        data (pd.DataFrame): DataFrame containing the data.
        method (str, optional): Method to use for estimating eps. Defaults to 'kneepoint'.
            Can be one of ['kneepoint', 'mean', 'median'].'kneepoint' estimates the knee of the nearest neighbour
            distribution to to estimate eps. 'mean' and 'median' use the 1.5 times the mean or median of the
            nearest neighbour distances respectively.
        pos_cols (list[str]): List of column names containing the position data.
        frame_col (str, optional): Name of the column containing the frame number. Defaults to 't'.
        n_neighbors (int, optional): Number of nearest neighbours to consider. Defaults to 5.
        plot (bool, optional): Whether to plot the results. Defaults to True.
        plt_size (tuple[int, int], optional): Size of the plot. Defaults to (5, 5).
        kwargs: Keyword arguments for the method. Modify behaviour of respecitve method.
            For kneepoint: [S online, curve, direction, interp_method,polynomial_degree; For mean: [mean_multiplier]
            For median [median_multiplier]

    Returns:
        Eps (float): eps parameter for DBSCAN.
    """
    subset = [frame_col] + pos_cols
    for i in subset:
        if i not in data.columns:
            raise ValueError(f"Column {i} not in data")
    method_option = ['kneepoint', 'mean', 'median']

    if method not in method_option:
        raise ValueError(f"Method must be one of {method_option}")

    allowedtypes: dict[str, str] = {
        'kneepoint': 'kneepoint_values',
        'mean': 'mean_values',
        'median': 'median_values',
    }

    kwdefaults: dict[str, Any] = {
        'S': 1,
        'online': True,
        'curve': 'convex',
        'direction': 'increasing',
        'interp_method': 'polynomial',
        'mean_multiplier': 1.5,
        'median_multiplier': 1.5,
        'polynomial_degree': 7,
    }

    kwtypes: dict[str, Any] = {
        'S': int,
        'online': bool,
        'curve': str,
        'direction': str,
        'interp_method': str,
        'polynomial_degree': int,
        'mean_multiplier': (float, int),
        'median_multiplier': (float, int),
    }

    allowedkwargs: dict[str, list[str]] = {
        'kneepoint_values': ['S', 'online', 'curve', 'interp_method', 'direction', 'polynomial_degree'],
        'mean_values': ['mean_multiplier'],
        'median_values': ['median_multiplier'],
    }

    for key in kwargs:
        if key not in allowedkwargs[allowedtypes[method]]:
            raise ValueError(f'{key} keyword not in allowed keywords {allowedkwargs[allowedtypes[method]]}')
        if not isinstance(kwargs[key], kwtypes[key]):
            raise ValueError(f'{key} must be of type {kwtypes[key]}')

    # Set kwarg defaults
    for kw in allowedkwargs[allowedtypes[method]]:
        kwargs.setdefault(kw, kwdefaults[kw])

    subset = [frame_col] + pos_cols
    data_np = data[subset].to_numpy(dtype=np.float64)
    # sort by frame
    data_np = data_np[data_np[:, 0].argsort()]
    grouped_array = np.split(data_np[:, 1:], np.unique(data_np[:, 0], axis=0, return_index=True)[1][1:])
    # map nearest_neighbours to grouped_array
    distances = np.concatenate([_nearest_neighbour_eps(i, n_neighbors) for i in grouped_array if i.shape[0] > 1])
    # flatten array
    distances_flat = distances.flatten()
    distances_flat = distances_flat[np.isfinite(distances_flat)]
    distances_flat_selection = np.random.choice(
        distances_flat, min(max_samples, distances_flat.shape[0]), replace=False
    )
    distances_sorted = np.sort(distances_flat_selection)
    if method == 'kneepoint':
        k1 = KneeLocator(
            np.arange(0, distances_sorted.shape[0]),
            distances_sorted,
            S=kwargs['S'],
            online=kwargs['online'],
            curve=kwargs['curve'],
            interp_method=kwargs['interp_method'],
            direction=kwargs['direction'],
            polynomial_degree=kwargs['polynomial_degree'],
        )

        eps = distances_sorted[k1.knee]

    elif method == 'mean':
        eps = np.mean(distances_sorted) * kwargs['mean_multiplier']

    elif method == 'median':
        eps = np.median(distances_sorted) * kwargs['median_multiplier']

    if plot:
        fig, ax = plt.subplots(figsize=plt_size)
        ax.plot(distances_sorted)
        ax.axhline(eps, color='r', linestyle='--')
        ax.set_xlabel('Sorted Distance Index')
        ax.set_ylabel('Nearest Neighbour Distance')
        ax.set_title(f'Estimated eps: {eps:.4f}')
        plt.show()

    return eps
