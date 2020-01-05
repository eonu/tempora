import numpy as np
from sequentia.preprocessing import standardize

# Create some sample data
X = [np.random.random((10 * i, 3)) for i in range(1, 4)]

# Standardize the data
X = standardize(X)