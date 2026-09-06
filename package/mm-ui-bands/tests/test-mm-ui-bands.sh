#!/bin/sh

set -eu

TEST_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/mm-ui-bands-test.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT HUP INT TERM

export MMUI_TEST_LOG="$TMP_DIR/calls.log"
export MMCLI_BIN="$TEST_ROOT/tests/mock-mmcli.sh"
export JSONFILTER_BIN="$TEST_ROOT/tests/mock-jsonfilter.sh"
export UCI_BIN="$TEST_ROOT/tests/mock-uci.sh"
export IFUP_BIN="$TEST_ROOT/tests/mock-ifup.sh"
export LOGGER_BIN=/bin/true

apply_helper="$TEST_ROOT/root/usr/libexec/mm-ui-bands"

"$apply_helper" apply

grep -F -- '--set-current-bands=eutran-1|ngran-78' "$MMUI_TEST_LOG" >/dev/null
grep -F -- '--set-allowed-modes=4g|3g --set-preferred-mode=4g' "$MMUI_TEST_LOG" >/dev/null
grep -F -- 'ifup cell' "$MMUI_TEST_LOG" >/dev/null

: >"$MMUI_TEST_LOG"
MMUI_TEST_COMMA_CURRENT=1 "$apply_helper" apply
grep -F -- '--set-allowed-modes=4g|3g --set-preferred-mode=4g' "$MMUI_TEST_LOG" >/dev/null

: >"$MMUI_TEST_LOG"
MMUI_TEST_ANY=1 "$apply_helper" apply
grep -F -- '--set-current-bands=any' "$MMUI_TEST_LOG" >/dev/null

: >"$MMUI_TEST_LOG"
MMUI_TEST_EMPTY_BANDS=1 "$apply_helper" apply
if grep -F -- '--set-current-bands=' "$MMUI_TEST_LOG" >/dev/null; then
	echo 'empty band selection unexpectedly changed the modem' >&2
	exit 1
fi

: >"$MMUI_TEST_LOG"
if MMUI_TEST_BAD_BANDS=1 "$apply_helper" apply; then
	echo 'invalid band selection unexpectedly succeeded' >&2
	exit 1
fi
if grep -F -- '--set-current-bands=' "$MMUI_TEST_LOG" >/dev/null; then
	echo 'invalid band selection reached mmcli' >&2
	exit 1
fi

: >"$MMUI_TEST_LOG"
if MMUI_TEST_BAD_MODE=1 "$apply_helper" apply; then
	echo 'unsupported allowed/preferred mode pair unexpectedly succeeded' >&2
	exit 1
fi
if grep -F -- '--set-allowed-modes=' "$MMUI_TEST_LOG" >/dev/null; then
	echo 'unsupported mode pair reached mmcli' >&2
	exit 1
fi
if grep -F -- '--set-current-bands=' "$MMUI_TEST_LOG" >/dev/null; then
	echo 'invalid mode selection partially changed bands' >&2
	exit 1
fi

: >"$MMUI_TEST_LOG"
MMUI_TEST_MODE=discover "$apply_helper" discover
grep -F -- 'uci add mmconfig modem' "$MMUI_TEST_LOG" >/dev/null
grep -F -- 'uci commit mmconfig' "$MMUI_TEST_LOG" >/dev/null

: >"$MMUI_TEST_LOG"
MMUI_TEST_MODE=anonymous "$apply_helper" apply
grep -F -- '--set-current-bands=eutran-1|ngran-78' "$MMUI_TEST_LOG" >/dev/null
grep -F -- 'ifup cell' "$MMUI_TEST_LOG" >/dev/null

: >"$MMUI_TEST_LOG"
MMUI_TEST_BAD_MODE=1 "$apply_helper" prepare /sys/devices/platform/usb1/1-1
grep -F -- '--set-current-bands=eutran-1|ngran-78' "$MMUI_TEST_LOG" >/dev/null
if grep -E -- 'ifup |--set-allowed-modes=' "$MMUI_TEST_LOG" >/dev/null; then
	echo 'netifd prepare recursed into ifup or changed modes' >&2
	exit 1
fi

: >"$MMUI_TEST_LOG"
MMUI_TEST_EMPTY_BANDS=1 "$apply_helper" prepare /sys/devices/platform/usb1/1-1
if grep -F 'mmcli ' "$MMUI_TEST_LOG" >/dev/null; then
	echo 'empty default added an MM operation to netifd' >&2
	exit 1
fi

: >"$MMUI_TEST_LOG"
"$apply_helper" prepare /sys/devices/platform/usb1/1-10
if grep -F 'mmcli ' "$MMUI_TEST_LOG" >/dev/null; then
	echo 'prepare touched a different device through a substring match' >&2
	exit 1
fi

echo 'mm-ui-bands mocked ModemManager checks passed'
