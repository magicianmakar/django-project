import math
from calendar import monthrange


def millify(n):
    if n >= 1100:
        millnames = ['', 'K', 'M', 'B', 'T']
        n = float(n)
        millidx = max(0, min(len(millnames) - 1, int(math.floor(0 if n == 0 else math.log10(abs(n)) / 3))))

        return '{}{}'.format(round((n / 10 ** (3 * millidx)), 2), millnames[millidx])
    else:
        return str(n)


def get_days_in_month(dt):
    return monthrange(dt.year, dt.month)[1]
