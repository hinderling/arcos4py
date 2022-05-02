"""Module to plot different metrics generated by arcos4py functions.

Example:
    >>> from arcos4py.plotting import plotOriginalDetrended
    >>> plot = arcosPlots(data, 'time', 'meas', 'detrended', 'id')
    >>> plot.plot_detrended()
"""

from __future__ import annotations

from typing import Union

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

TAB20 = [
    "#1f77b4",
    "#aec7e8",
    "#ff7f0e",
    "#ffbb78",
    "#2ca02c",
    "#98df8a",
    "#d62728",
    "#ff9896",
    "#9467bd",
    "#c5b0d5",
    "#8c564b",
    "#c49c94",
    "#e377c2",
    "#f7b6d2",
    "#7f7f7f",
    "#c7c7c7",
    "#bcbd22",
    "#dbdb8d",
    "#17becf",
    "#9edae5",
]


class dataPlots:
    """Plot different metrics of input data.

    Attributes:
        data (Dataframe): containing ARCOS data.
        frame (str): name of frame column in data.
        measurement (str): name of measurement column in data.
        id (str): name of track id column.
    """

    def __init__(self, data: pd.DataFrame, frame: str, measurement: str, id: str):
        """Plot different metrics such as histogram, position-t and density.

        Arguments:
            data (Dataframe): containing ARCOS data.
            frame (str): name of frame column in data.
            measurement (str): name of measurement column in data.
            id (str): name of track id column.
        """
        self.data = data
        self.id = id
        self.frame = frame
        self.measurement = measurement

    def position_t_plot(self, posCol: set[str] = {'x'}, n: int = 20):
        """Plots X and Y over T to visualize tracklength.

        Arguments:
            posCol (set): containing names of position columns in data.
            n (int): number of samples to plot.

        Returns (fig, axes):
            FacetGrid of density density plot.
        """
        sample = pd.Series(self.data[self.id].unique()).sample(n)
        pd_from_r_df = self.data.loc[self.data[self.id].isin(sample)]
        fig, axes = plt.subplots(1, len(posCol), figsize=(6, 3))
        for label, df in pd_from_r_df.groupby(self.id):
            for index, value in enumerate(posCol):
                if len(posCol) > 1:
                    df.plot(x=self.frame, y=value, ax=axes[index], legend=None)
                else:
                    df.plot(x=self.frame, y=value, ax=axes, legend=None)
        if len(posCol) > 1:
            for index, value in enumerate(posCol):
                axes[index].set_title(value)
        else:
            axes.set_title(value)
        return fig, axes

    def density_plot(self, *args, **kwargs):
        """Density plot of measurement.

        Uses Seaborn distplot to plot measurement density.

        Arguments:
            measurement_col (str): name of measurement column.
            *args (Any): arguments passed on to seaborn histplot function.
            **kwargs (Any): keyword arguments passed on to seaborn histplot function.

        Returns (FacetGrid):
            FacetGrid of density density plot.
        """
        plot = sns.displot(
            self.data[self.measurement], kind="kde", palette="pastel", label=self.measurement, *args, **kwargs
        )
        # Plot formatting
        plt.legend(prop={'size': 10})
        plt.title('Density Plot of Measurement')
        plt.xlabel('Measurement')
        plt.ylabel('Density')
        return plot

    def histogram(self, bins: str = 'auto', *args, **kwargs):
        """Histogram of tracklenght.

        Uses seaborn histplot function to plot tracklenght histogram.

        Arguments:
            bins (str): number or width of bins in histogram
            *args (Any): arguments passed on to seaborn histplot function.
            **kwargs (Any): keyword arguments passed on to seaborn histplot function.

        Returns (AxesSubplot):
            Matplotlib axes of histogram.
        """
        # Draw histogram
        track_length = self.data.groupby(self.id).size()
        axes = sns.histplot(track_length, label="Track Length", bins=bins, *args, **kwargs)
        # Plot formatting
        plt.title('Track length Histogram')
        axes.set_xlabel('Track Length')
        axes.set_ylabel('Count')
        return axes


class plotOriginalDetrended:
    """Plot different detrended vs original data.

    Attributes:
        data (Dataframe): containing ARCOS data.
        frame (str): name of frame column in data.
        measurement (str): name of measurement column in data.
        detrended (str): name of detrended column with detrended data.
        id (str): name of track id column.
    """

    def __init__(self, data: pd.DataFrame, frame: str, measurement: str, detrended: str, id: str):
        """Plot detrended vs original data.

        Arguments:
            data (Dataframe): containing ARCOS data.
            frame (str): name of frame column in data.
            measurement (str): name of measurement column in data.
            detrended (str): name of detrended column with detrended data.
            id (str): name of track id column.
        """
        self.data = data
        self.measurement = measurement
        self.detrended = detrended
        self.id = id
        self.frame = frame

    def plot_detrended(
        self, n_samples: int = 25, subplots: tuple = (5, 5), plotsize: tuple = (20, 10)
    ) -> matplotlib.axes.Axes:
        """Method to plot detrended vs original data.

        Arguments:
            n_samples (int): Number of tracks to plot.
            subplots (tuple): Number of subplots, should be approx. one per sample.
            plotsize (tuple): Size of generated plot.

        Returns (fig, Axes):
            Matplotlib figure and axes2d of detrended vs original data.
        """
        vals = np.random.choice(self.data[self.id].unique(), n_samples, replace=False)
        self.data = self.data.set_index(self.id).loc[vals].reset_index()
        grouped = self.data.groupby(self.id)

        ncols = subplots[0]
        nrows = subplots[1]

        fig, axes2d = plt.subplots(nrows=nrows, ncols=ncols, figsize=plotsize, sharey=True)

        for (key, ax) in zip(grouped.groups.keys(), axes2d.flatten()):
            grouped.get_group(key).plot(x=self.frame, y=[self.measurement, self.detrended], ax=ax)
            ax.get_legend().remove()

        handles, labels = ax.get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower right")

        return fig, axes2d


class statsPlots:
    """Plot data generated by the stats module.

    Attributes:
        data (DataFrame): containing ARCOS stats data.
    """

    def __init__(self, data: pd.DataFrame):
        """Plot detrended vs original data.

        Arguments:
            data (DataFrame): containing ARCOS stats data.
        """
        self.data = data

    def plot_events_duration(self, total_size: str, duration: str, point_size: int = 40, *args, **kwargs):
        """Scatterplot of collective event duration.

        Arguments:
            total_size (str): name of total size column.
            duration (str):, name of column with collective event duration.
            point_size (int): scatterplot point size.
            *args (Any): Arguments passed on to seaborn scatterplot function.
            **kwargs (Any): Keyword arguments passed on to seaborn scatterplot function.

        Returns (Axes): Axes object of scatterplot
        """
        plot = sns.scatterplot(x=self.data[total_size], y=self.data[duration], s=point_size, *args, **kwargs)
        return plot


class NoodlePlot:
    """Create Noodle Plot of cell tracks, colored by collective event id.

    Attributes:
        df (pd.DataFrame): DataFrame containing collective events from arcos.
        colev (str): Name of the collective event column in df.
        trackid (str): Name of the track column in df.
        frame: (str): Name of the frame column in df.
        posx (str): Name of the X coordinate column in df.
        posy (str): Name of the Y coordinate column in df.
        posz (str): Name of the Z coordinate column in df,
            or None if no z column.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        colev: str,
        trackid: str,
        frame: str,
        posx: str,
        posy: str,
        posz: Union[str, None] = None,
    ):
        """Constructs class with given parameters.

        Arguments:
            df (pd.DataFrame): DataFrame containing collective events from arcos.
            colev (str): Name of the collective event column in df.
            trackid (str): Name of the track column in df.
            frame: (str): Name of the frame column in df.
            posx (str): Name of the X coordinate column in df.
            posy (str): Name of the Y coordinate column in df.
            posz (str | None): Name of the Z coordinate column in df,
                or "None" (str) if no z column.
        """
        self.df = df
        self.colev = colev
        self.trackid = trackid
        self.frame = frame
        self.posx = posx
        self.posy = posy
        self.posz = posz

    def _prepare_data_noodleplot(
        self,
        df: pd.DataFrame,
        color_cylce: list[str],
        colev: str,
        trackid: str,
        frame: str,
        posx: str,
        posy: str,
        posz: Union[str, None] = None,
    ):
        """From arcos collective event data,\
        generates a list of numpy arrays, one for each event.

        Arguments:
            df (pd.DataFrame): DataFrame containing collective events from arcos.
            color_cylce (list[str]): list of colors used to color trackid's
                for individual collective events.
            colev (str): Name of the collective event column in df.
            trackid (str): Name of the track column in df.
            frame: (str): Name of the frame column in df.
            posx (str): Name of the X coordinate column in df.
            posy (str): Name of the Y coordinate column in df.
            posz (str): Name of the Z coordinate column in df,
                or None if no z column.

        Returns (list[np.ndarray], np.ndarray): List of collective events data,
        colors for each collective event.
        """
        # values need to be sorted to group with numpy
        df.sort_values([colev, trackid], inplace=True)
        if posz:
            array = df[[colev, trackid, frame, posx, posy, posz]].to_numpy()
        else:
            array = df[[colev, trackid, frame, posx, posy]].to_numpy()
        # generate goroups for each unique value
        grouped_array = np.split(array, np.unique(array[:, 0], axis=0, return_index=True)[1][1:])
        # make collids sequential
        seq_colids = np.concatenate(
            [np.repeat(i, value.shape[0]) for i, value in enumerate(grouped_array)],
            axis=0,
        )
        array_seq_colids = np.column_stack((array, seq_colids))
        # split sequential collids array by trackid and collid
        grouped_array = np.split(
            array_seq_colids,
            np.unique(array_seq_colids[:, :2], axis=0, return_index=True)[1][1:],
        )
        # generate colors for each collective event, wrap arround the color cycle
        colors = np.take(np.array(color_cylce), [i + 1 for i in np.unique(seq_colids)], mode="wrap")
        return grouped_array, colors

    def _create_noodle_plot(self, grouped_data: np.ndarray, colors: np.ndarray):
        """Plots the noodle plot."""
        fig, ax = plt.subplots()
        ax.set_xlabel("Time Point")
        ax.set_ylabel("Position")
        for dat in grouped_data:
            ax.plot(
                dat[:, 2],
                dat[:, self.projection_index],
                c=colors[int(dat[0, -1])],
            )
        return fig, ax

    def plot(self, projection_axis: str, color_cylce: list[str] = TAB20):
        """Create Noodle Plot of cell tracks, colored by collective event id.

        Arguments:
            projection_axis (str): Specify on which with witch coordinate the noodle
                plot should be drawn. Has to be one of the posx, posy or posz arguments
                passed in during the class instantiation process.
            color_cylce (list[str]): List of hex color values or string names
                (i.e. ['red', 'yellow']) used to color collecitve events.
                cycles through list and assigns

        Returns (fig, axes): Matplotlib figure and axes are returned for the noodle plot.
        """
        if projection_axis not in [self.posx, self.posy, self.posz]:
            raise ValueError(f"projection_axis has to be one of {[self.posx, self.posy, self.posz]}")
        if projection_axis == self.posx:
            self.projection_index = 3
        elif projection_axis == self.posy:
            self.projection_index = 4
        elif projection_axis == self.posz:
            self.projection_index = 5
        grpd_data, colors = self._prepare_data_noodleplot(
            self.df, color_cylce, self.colev, self.trackid, self.frame, self.posx, self.posy, self.posz
        )
        fig, axes = self._create_noodle_plot(grpd_data, colors)
        return fig, axes
