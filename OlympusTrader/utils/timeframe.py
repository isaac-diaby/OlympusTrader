from datetime import datetime, timedelta
from enum import Enum


"""FROM ALPACA TIMEFRAME.PY """


class TimeFrameUnit(str, Enum):
    """Quantity of time used as unit"""

    Minute: str = "Min"
    Hour: str = "Hour"
    Day: str = "Day"
    Week: str = "Week"
    Month: str = "Month"


class TimeFrame:
    """A time interval specified in multiples of defined units (minute, day, etc)

    Attributes:
        amount_value (int): The number of multiples of the TimeFrameUnit interval
        unit_value (TimeFrameUnit): The base unit of time interval that is used to measure the TimeFrame

    Raises:
        ValueError: Raised if the amount_value and unit_value are not consistent with each other
    """

    amount_value: int
    unit_value: TimeFrameUnit

    def __init__(self, amount, unit) -> None:
        self.validate_timeframe(amount, unit)
        self.amount_value = amount
        self.unit_value = unit

    @property
    def amount(self) -> int:
        """Returns the amount_value field

        Returns:
            int: amount_value field
        """
        return self.amount_value

    @property
    def unit(self) -> TimeFrameUnit:
        """Returns the TimeFrameUnit field value of this TimeFrame object

        Returns:
            TimeFrameUnit: unit_value field
        """
        return self.unit_value

    @property
    def value(self) -> str:
        """Returns a string representation of this TimeFrame object for API consumption

        Returns:
            str: string representation of this timeframe
        """
        return f"{self.amount}{self.unit.value}"

    @staticmethod
    def validate_timeframe(amount: int, unit: TimeFrameUnit):
        """Validates the amount value against the TimeFrameUnit value for consistency

        Args:
            amount (int): The number of multiples of unit
            unit (TimeFrameUnit): The base unit of time interval the TimeFrame is measured by

        Raises:
            ValueError: Raised if the values of amount and unit are not consistent with each other
        """
        if amount <= 0:
            raise ValueError("Amount must be a positive integer value.")

        if unit == TimeFrameUnit.Minute and amount > 59:
            raise ValueError(
                "Second or Minute units can only be "
                + "used with amounts between 1-59."
            )

        if unit == TimeFrameUnit.Hour and amount > 23:
            raise ValueError("Hour units can only be used with amounts 1-23")

        if unit in (TimeFrameUnit.Day, TimeFrameUnit.Week) and amount != 1:
            raise ValueError(
                "Day and Week units can only be used with amount 1")

        if unit == TimeFrameUnit.Month and amount not in (1, 2, 3, 6, 12):
            raise ValueError(
                "Month units can only be used with amount 1, 2, 3, 6 and 12"
            )
        return True
    
    def is_time_increment(self, time: datetime) -> bool:
        """ return true if the current date time is in the frequency of the time of X min increments
        Args:
            time (datetime): current time
            resolution (TimeFrame): TimeFrame object
            frequency (int, optional): frequency of the time. Defaults to 5.

        Returns:
            bool: True if the current date time is in the frequency of the time of X Time Unit increments

        Note: This will just match the Time Unit, not the exact time of the day. so will pass if the time is 12:00:00 or 12:00:59 same with dates and months
        Note: if your using this to execute a trade, you should check if the market is open first before executing a trade
        """
        match self.unit_value:
            case TimeFrameUnit.Minute:
                if time.minute % self.amount_value == 0:
                    return True
                else:
                    return False
            case TimeFrameUnit.Hour:

                if time.hour % self.amount_value == 0:
                    return True
                else:
                    return False
            case TimeFrameUnit.Day:
                if time.day % self.amount_value == 0:
                    return True
                else:
                    return False
            case TimeFrameUnit.Week:
                if time.week % self.amount_value == 0:
                    return True
                else:
                    return False
            case TimeFrameUnit.Month:
                if time.month % self.amount_value == 0:
                    return True
                else:
                    return False
            case _:
                print("resolution Error: TimeFrameUnit not implemented")
                return False
            
    def add_time_increment(self, time: datetime, periods: int) -> datetime:
        """ 
        Add the time increment to the current time
        """
        match self.unit_value:
            case TimeFrameUnit.Minute:
                return time + timedelta(minutes=self.amount_value*periods)
            case TimeFrameUnit.Hour:
                return time + timedelta(hours=self.amount_value*periods)
            case TimeFrameUnit.Day:
                return time + timedelta(days=self.amount_value*periods)
            case TimeFrameUnit.Week:
                return time + timedelta(weeks=self.amount_value*periods)
            case TimeFrameUnit.Month:
                return time + timedelta(months=self.amount_value*periods)
            case _:
                print("resolution Error: TimeFrameUnit not implemented")
                return False

    def __str__(self):
        return self.value



