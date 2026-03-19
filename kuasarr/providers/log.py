# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import datetime
import os


def timestamp():
    return datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")


def info(string):
    print(f"{timestamp()} {string}")


def debug(string):
    if os.getenv('DEBUG'):
        info(string)


def error(string):
    info(f"ERROR: {string}")



