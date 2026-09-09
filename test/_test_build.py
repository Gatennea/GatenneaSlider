import sys
import os

print("=== SliderGUI Path Test ===")
print(f"sys.frozen = {getattr(sys, 'frozen', False)}")
print(f"sys.executable = {sys.executable}")
print(f"__file__ = {os.path.abspath(__file__)}")

if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname