#!/bin/sh

set -eu

printf 'ifup %s\n' "$*" >> "$MMUI_TEST_LOG"
