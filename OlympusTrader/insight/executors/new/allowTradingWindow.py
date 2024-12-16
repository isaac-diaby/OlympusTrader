from typing import Union
from ..base_executor import BaseExecutor
from ...insight import InsightState

import datetime
import pytz

class AllowedTradingWindow(BaseExecutor):
    """
    ### Executor for Allow Trading Window
    This executor is used to allow trading during a specific date and time window.

    :param strategy (BaseStrategy): The strategy instance
    :param start (str): Start of the trading window in the format "HH:MM"
    :param end (str): End of the trading window in the format "HH:MM"
    :param days (List[str]): List of days to allow trading. Default is all days of the week.

    Author:
        @isaac-diaby
    """

    start: datetime.time
    end: datetime.time
    days: set[str]

    daysOfTheWeek = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6
        }

    def __init__(self, strategy, start: str, end: str, days: list[Union[str, int]] = ["monday", "tuesday", "wednesday", "thursday", 4], **kwargs):
        super().__init__(strategy, InsightState.NEW, "1.0", **kwargs)
        self.start = self.format_time(start)
        self.end = self.format_time(end)
        self.days = self.format_days(days)

    def run(self, insight):
        try:
            if self.is_trading_time(self.start, self.end, self.days):
                return self.returnResults(True, True, "Trading allowed.")
            msg = f"Trading not allowed. Trading window is from {self.start} to {self.end} on {self.days}."
            self.changeState(insight, InsightState.REJECTED, msg)
            return self.returnResults(False, True, msg)
        except Exception as e:
            return self.returnResults(False, False, f"Error allowing trading: {e}")
        
    
    def is_trading_time(self, start: str, end: str, days: list[str]):
        """
        Check if the current time is within the trading window.

        :param start (str): Start of the trading window in the format "HH:MM"
        :param end (str): End of the trading window in the format "HH:MM"
        :param days (List[str]): List of days to allow trading. Default is all days of the week.

        Returns:
            bool: True if trading is allowed, False otherwise
        """
        current_datetime = self.STRATEGY.current_datetime
        current_day = current_datetime.weekday()
        current_time = current_datetime.time().replace(tzinfo=pytz.timezone('UTC'))
        
        if list(self.daysOfTheWeek.keys())[list(self.daysOfTheWeek.values()).index(current_day)] not in days:
            return False
        
        if start <= current_time <= end:
            return True
        
        return False
    
    def format_time(self, time: str) -> datetime.time:

        """
        Format the time string to a time object.

        :param time (str): Time string to format

        Returns:
            time: Formatted time object
        """
        return datetime.time.fromisoformat(time).replace(tzinfo=pytz.timezone('UTC'))

    
    def format_days(self, days: list[Union[str, int]]) -> list[int]:
        """
        Format the list of days to be in lowercase.

        :param days (List[Union[str, int]]): List of days to format

        Returns:
            List[str]: Formatted list of days
        """
        assert isinstance(days, list), "Days must be a list."

        for i, day in enumerate(days):
            if isinstance(day, int):
                days[i] = list(self.daysOfTheWeek.keys())[list(self.daysOfTheWeek.values()).index(day)]
            else:
                days[i] = day.lower()
        
        return set(days)
