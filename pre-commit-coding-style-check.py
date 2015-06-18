#!/usr/bin/env python

import sys
import subprocess

autopep8_args = [
    "autopep8",
    "--diff",
    "--recursive",
    "--aggressive",
    "."
]
autopep8_output = subprocess.Popen(autopep8_args, stdout=subprocess.PIPE).stdout.read()

autoflake_args = [
    "autoflake",
    "--recursive",
    "--remove-all-unused-imports",
    "--remove-unused-variables",
    "."
]
autoflake_output = subprocess.Popen(autoflake_args, stdout=subprocess.PIPE).stdout.read()

if len(autopep8_output) == 0 or len(autoflake_output) == 0:
    sys.exit(0)
else:
    print autopep8_output
    print autoflake_output
    print ""
    print "ERROR: The coding style check failed!"
    print "  If you want to skip the coding style check please use '-n' or '--no-verify'."
    print "  This option bypasses the pre-commit and commit-msg hooks."
    sys.exit(1)
