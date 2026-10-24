"""Isolate tests even when running a single test file."""
import os
os.environ['AIRCONTROL_DB'] = ':memory:'
