import os
import sys
from pathlib import Path

sys.path.append('/home/djvemo/ultrastar_official')
from ConfigLoader import load_config
import ConvertFiles

cfg = load_config()
ConvertFiles.main(cfg)
print("Rebuild finished!")
