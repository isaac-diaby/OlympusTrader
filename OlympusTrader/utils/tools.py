
import numpy


def dynamic_round(price: float) -> float:
    """Round float depending on log10 decimal places"""
    dynamic_precision = -int(numpy.log(price))
    return round(price, dynamic_precision+2)


if __name__ == '__main__':
    print(dynamic_round(0.0045456171111))