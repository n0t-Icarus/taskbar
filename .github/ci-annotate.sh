#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Job logs on GitHub require a signed-in session; annotations do not. A failure
# whose only explanation lives inside the log is therefore invisible to anyone
# reading the run page signed out, so this republishes the interesting lines as
# annotations.
#
# usage: ci-annotate.sh <logfile> [extended-regex]
#
# Deliberately no `set -e`: a log with nothing interesting in it is not an error.
set -uo pipefail

log=${1:?usage: ci-annotate.sh <logfile> [extended-regex]}
pattern=${2:-error[ :]|error C[0-9]|error LNK|error MSB|CMake Error}

# % starts an escape in a workflow command and has to be doubled; CR would break
# the annotation to an empty line on some viewers.
grep -inE "$pattern" "$log" 2>/dev/null \
    | head -25 \
    | tr -d '\r' \
    | sed -e 's/%/%25/g' \
    | while IFS= read -r line; do
        echo "::error::$line"
    done

exit 0
