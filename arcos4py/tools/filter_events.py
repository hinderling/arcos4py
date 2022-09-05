"""Module to filter collective events.

Example:
    >>> from arcos4py.tools import filterCollev
    >>> f = filterCollev(data, 'time', 'collid')
    >>> df = f.filter(coll_duration = 9, coll_total_size = 10)
"""
import pandas as pd

from .stats import calcCollevStats


class filterCollev:
    """Select Collective events that last longer than coll_duration\
    and have a larger total size than coll_total_size.

    Attributes:
        data (Dataframe): With detected collective events.
        frame_column (str): Indicating the frame column in data.
        collid_column (str): Indicating the collective event id column in data.
        obj_id_column (str): Inidicating the object identifier column such as cell track id.
    """

    def __init__(
        self,
        data: pd.DataFrame,
        frame_column: str = "time",
        collid_column: str = "collid",
        obj_id_column: str = "trackID",
    ):
        """Constructs filterCollev class with Parameters.

        Arguments:
            data (Dataframe): With detected collective events.
            frame_column (str): Indicating the frame column in data.
            collid_column (str): Indicating the collective event id column in data.
            obj_id_column (str): Inidicating the object identifier column such as cell track id.
        """
        self.data = data
        self.frame_column = frame_column
        self.collid_column = collid_column
        self.obj_id_column = obj_id_column

    def _filter_collev(
        self,
        data: pd.DataFrame,
        collev_stats: pd.DataFrame,
        collev_id: str,
        min_duration: int,
        min_size: int,
    ):
        """Uses the dataframe generated by self._get_collev_duration()\
        to filter collective events that last longer than\
        min_duration and are larger than min_size.

        Arguments:
            data (DataFrame): Containing unfiltered collective events.
            collev_stats (DataFrame): Containing stats of collective events.
            collev_id (str): Indicating the contained collective id column.
            min_duration (str): minimal duration of a collective event for it to be returned.
            min_size (int): minimal size for a collective event to be returned.

        Returns:
            DataFrame (DataFrame): Dataframe containing filtered collective events.

        """
        collev_stats = collev_stats[
            (collev_stats["duration"] >= min_duration) & (collev_stats["total_size"] >= min_size)
        ]
        data = data[data[collev_id].isin(collev_stats[collev_id])]
        return data

    def filter(self, coll_duration: int = 9, coll_total_size: int = 10) -> pd.DataFrame:
        """Filter collective events.

        Method to filter collective events according to the
        parameters specified in the object instance.

        Arguments:
            coll_duration (int): Minimal duration of collective events to be selected.
            coll_total_size (int): Minimal total size of collective events to be selected.

        Returns:
             Returns pandas dataframe containing filtered collective events
        """
        if self.data.empty:
            return self.data
        stats = calcCollevStats()
        colev_duration = stats.calculate(self.data, self.frame_column, self.collid_column, self.obj_id_column)

        filtered_df = self._filter_collev(
            self.data,
            colev_duration,
            self.collid_column,
            coll_duration,
            coll_total_size,
        )
        return filtered_df
