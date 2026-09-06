#!/bin/sh

set -eu

if [ -n "${MMUI_TEST_LOG:-}" ]; then
	printf 'mmcli %s\n' "$*" >> "$MMUI_TEST_LOG"
fi

case " $* " in
	*" -L -J "*|*" --list-modems "*)
		printf '%s\n' '{"modem-list":["/org/freedesktop/ModemManager1/Modem/0"]}'
		;;
	*" -J "*)
		printf '%s\n' '{"modem":{"generic":{"device":"/sys/devices/platform/usb1/1-1","supported-bands":["eutran-1","eutran-3","ngran-78"],"current-bands":["eutran-3"],"supported-modes":["allowed: 3g; preferred: none","allowed: 3g, 4g; preferred: 4g","allowed: 2g, 3g, 4g; preferred: none"],"current-modes":"allowed: 3g; preferred: none"},"3gpp":{"operator-name":"Test LTE"}}}'
		;;
	*)
		# The set operations are intentionally successful, as they would be on
		# an MM-capable modem.  The caller verifies the exact arguments.
		exit 0
		;;
esac
