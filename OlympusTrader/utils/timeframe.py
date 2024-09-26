from datetime import datetime, timedelta
from enum import Enum


"""FROM ALPACA TIMEFRAME.PY but modified to be used for OlympusTrader framework"""


class ITimeFrameUnit(str, Enum):
    """Quantity of time used as unit"""

    Minute: str = "Min"
    Hour: str = "Hour"
    Day: str = "Day"
    Week: str = "Week"
    Month: str = "Month"


class ITimeFrame:
    """A time interval specified in multiples of defined units (minute, day, etc)

    Attributes:
        amount_value (int): The number of multiples of the ITimeFrameUnit interval
        unit_value (ITimeFrameUnit): The base unit of time interval that is used to measure the TimeFrame

    Raises:
        ValueError: Raised if the amount_value and unit_value are not consistent with each other
    """

    amount_value: int
    unit_value: ITimeFrameUnit

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
    def unit(self) -> ITimeFrameUnit:
        """Returns the ITimeFrameUnit field value of this TimeFrame object

        Returns:
            ITimeFrameUnit: unit_value field
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
    def validate_timeframe(amount: int, unit: ITimeFrameUnit):
        """Validates the amount value against the ITimeFrameUnit value for consistency

        Args:
            amount (int): The number of multiples of unit
            unit (ITimeFrameUnit): The base unit of time interval the TimeFrame is measured by

        Raises:
            ValueError: Raised if the values of amount and unit are not consistent with each other
        """
        if amount <= 0:
            raise ValueError("Amount must be a positive integer value.")

        if unit == ITimeFrameUnit.Minute and amount > 59:
            raise ValueError(
                "Second or Minute units can only be "
                + "used with amounts between 1-59."
            )

        if unit == ITimeFrameUnit.Hour and amount > 23:
            raise ValueError("Hour units can only be used with amounts 1-23")

        if unit in (ITimeFrameUnit.Day, ITimeFrameUnit.Week) and amount != 1:
            raise ValueError(
                "Day and Week units can only be used with amount 1")

        if unit == ITimeFrameUnit.Month and amount not in (1, 2, 3, 6, 12):
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
            case ITimeFrameUnit.Minute:
                if time.minute % self.amount_value == 0:
                    return True
                else:
                    return False
            case ITimeFrameUnit.Hour:

                if time.hour % self.amount_value == 0:
                    return True
                else:
                    return False
            case ITimeFrameUnit.Day:
                if time.day % self.amount_value == 0:
                    return True
                else:
                    return False
            case ITimeFrameUnit.Week:
                if time.week % self.amount_value == 0:
                    return True
                else:
                    return False
            case ITimeFrameUnit.Month:
                if time.month % self.amount_value == 0:
                    return True
                else:
                    return False
            case _:
                print("resolution Error: ITimeFrameUnit not implemented")
                return False
            
    def add_time_increment(self, time: datetime, periods: int) -> datetime:
        """ 
        Add the time increment to the current time
        """
        match self.unit_value:
            case ITimeFrameUnit.Minute:
                return time + timedelta(minutes=self.amount_value*periods, seconds=-time.second, microseconds=-time.microsecond)
            case ITimeFrameUnit.Hour:
                return time + timedelta(hours=self.amount_value*periods, minutes=-time.minute, seconds=-time.second, microseconds=-time.microsecond)
            case ITimeFrameUnit.Day:
                return time + timedelta(days=self.amount_value*periods, hours=-time.hour, minutes=-time.minute, seconds=-time.second, microseconds=-time.microsecond)
            case ITimeFrameUnit.Week:
                return time + timedelta(weeks=self.amount_value*periods, days=-time.day, hours=-time.hour, minutes=-time.minute, seconds=-time.second, microseconds=-time.microsecond)
            case ITimeFrameUnit.Month:
                return time + timedelta(months=self.amount_value*periods, days=-time.day, hours=-time.hour, minutes=-time.minute, seconds=-time.second, microseconds=-time.microsecond)
            case _:
                print("resolution Error: ITimeFrameUnit not implemented")
                return False
            
    def get_time_increment(self, time: datetime) -> datetime:
        """ 
        Get the current time frame 
        """
        match self.unit_value:
            case ITimeFrameUnit.Minute:
                return time - timedelta(minutes=time.minute % self.amount_value, seconds=time.second, microseconds=time.microsecond)
            case ITimeFrameUnit.Hour:
                return time - timedelta(hours=time.hour % self.amount_value, minutes=time.minute, seconds=time.second, microseconds=time.microsecond)
            case ITimeFrameUnit.Day:
                return time - timedelta(days=time.day % self.amount_value, hours=time.hour, minutes=time.minute, seconds=time.second, microseconds=time.microsecond)
            case ITimeFrameUnit.Week:
                return time - timedelta(weeks=time.week % self.amount_value, days=time.day, hours=time.hour, minutes=time.minute, seconds=time.second, microseconds=time.microsecond)
            case ITimeFrameUnit.Month:
                return time - timedelta(months=time.month % self.amount_value, days=time.day, hours=time.hour, minutes=time.minute, seconds=time.second, microseconds=time.microsecond)
            case _:
                print("resolution Error: ITimeFrameUnit not implemented")
                return False
    def get_next_time_increment(self, time: datetime) -> datetime:
        """ 
        Get the next time frame increment
        """
        match self.unit_value:
            case ITimeFrameUnit.Minute:
                return time + timedelta(minutes=self.amount_value - time.minute % self.amount_value, seconds=-time.second, microseconds=-time.microsecond)
            case ITimeFrameUnit.Hour:
                return time + timedelta(hours=self.amount_value - time.hour % self.amount_value, minutes=-time.minute, seconds=-time.second, microseconds=-time.microsecond)
            case ITimeFrameUnit.Day:
                return time + timedelta(days=self.amount_value - time.day % self.amount_value, hours=-time.hour, minutes=-time.minute, seconds=-time.second, microseconds=-time.microsecond)
            case ITimeFrameUnit.Week:
                return time + timedelta(weeks=self.amount_value - time.week % self.amount_value, days=-time.day, hours=-time.hour, minutes=-time.minute, seconds=-time.second, microseconds=-time.microsecond)
            case ITimeFrameUnit.Month:
                return time + timedelta(months=self.amount_value - time.month % self.amount_value, days=-time.day, hours=-time.hour, minutes=-time.minute, seconds=-time.second, microseconds=-time.microsecond)
            case _:
                print("resolution Error: ITimeFrameUnit not implemented")
                return False
    def __int__(self):
        match self.unit_value:
            case ITimeFrameUnit.Minute:
                return self.amount_value
            case ITimeFrameUnit.Hour:
                return self.amount_value * 60
            case ITimeFrameUnit.Day:
                return self.amount_value * (60 * 24)
            case ITimeFrameUnit.Week:
                return self.amount_value * (60 * 24 * 7)
            case ITimeFrameUnit.Month:
                return self.amount_value * (60 * 24 * 7 * 30)
            case _:
                return self.amount_value
    def __str__(self):
        return self.value



