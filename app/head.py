# Python Import Commands for Alpaca Trading Application
# Run these commands in your terminal to install all required packages

# Set TensorFlow environment variables to suppress messages
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

# Core Data Processing Libraries
# pip install numpy>=1.21.0
# pip install pandas>=1.3.0

# Timezone Handling
# pip install tzlocal>=4.0

# Scientific Computing
# pip install scipy>=1.7.0

# Machine Learning and Deep Learning
# pip install scikit-learn>=1.0.0
# pip install keras>=2.12.0
# pip install tensorflow>=2.12.0

# Financial Calculations (Options Pricing)
# pip install py-vollib>=1.0.0

# Alpaca Trading API
# pip install alpaca-py>=0.13.0

# Optional Packages (uncomment if needed):

# For better performance with pandas
# pip install numba>=0.56.0

# For data visualization
# pip install matplotlib>=3.5.0
# pip install seaborn>=0.11.0

# -------------- Date and Time Handling --------------
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from tzlocal import get_localzone

# -------------- Data Processing and Analysis --------------
import numpy as np
import pandas as pd

from dataclasses import dataclass
from enum import Enum, auto
# -------------- Asynchronous Programming --------------
import asyncio

# -------------- System and File Operations --------------
import gc
import os
import json

# -------------- Type Annotations --------------
from typing import Dict, List, Optional, Union, Callable, Tuple, Any



