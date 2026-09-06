#!/bin/sh

set -eu

expression="${2:-}"
cat >/dev/null

case "$expression" in
	*'modem-list'*)
		printf '%s\n' '/org/freedesktop/ModemManager1/Modem/0'
		;;
	*'supported-bands'*)
		printf '%s\n' 'eutran-1 eutran-3 ngran-78'
		;;
	*'current-bands'*)
		printf '%s\n' 'eutran-3'
		;;
	*'supported-modes'*)
		printf '%s\n' \
			'allowed: 3g; preferred: none' \
			'allowed: 3g, 4g; preferred: none' \
			'allowed: 3g, 4g; preferred: 4g' \
			'allowed: 2g, 3g, 4g; preferred: none'
		;;
	*'current-modes'*)
		if [ "${MMUI_TEST_COMMA_CURRENT:-0}" = 1 ]; then
			printf '%s\n' 'allowed: 3g, 4g; preferred: none'
		else
			printf '%s\n' 'allowed: 3g; preferred: none'
		fi
		;;
	*'device'*)
		printf '%s\n' '/sys/devices/platform/usb1/1-1'
		;;
esac
