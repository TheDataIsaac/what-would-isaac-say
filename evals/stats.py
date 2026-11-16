"""How far to trust a pass rate.

Asking 10 questions and getting 9 right gives 90%, but another run might give 7 or 10. The range
below says where the true pass rate most likely sits, given how many answers we have.
"""

import math

Z_95 = 1.96  # 95% of a normal distribution lies within 1.96 standard deviations of its middle


def wilson_range(passes: int, total: int) -> tuple[float, float]:
    """The range the true pass rate sits in with 95% confidence, as two fractions (0.0 to 1.0).

    This is the Wilson interval. The simpler textbook range (rate plus or minus 1.96 standard
    errors) breaks down near 0% and 100% and with few answers, which is where most of these
    rates are: 10 out of 10 would give a range of exactly 100% to 100%.
    """
    if total == 0:
        return 0.0, 1.0  # no answers, so it could be anything
    rate = passes / total
    z2 = Z_95**2
    centre = (rate + z2 / (2 * total)) / (1 + z2 / total)
    spread = Z_95 * math.sqrt(rate * (1 - rate) / total + z2 / (4 * total**2)) / (1 + z2 / total)
    return max(0.0, centre - spread), min(1.0, centre + spread)
