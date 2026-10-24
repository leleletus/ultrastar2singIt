import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ConfigLoader import load_config
import ConvertFiles

cfg = load_config()
ConvertFiles.main(cfg)
print("Rebuild finished!")
