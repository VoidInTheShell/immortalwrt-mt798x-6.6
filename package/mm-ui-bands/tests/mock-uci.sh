#!/bin/sh

set -eu

while [ "${1:-}" = "-q" ]; do
	shift
done

command="${1:-}"
shift || :

if [ -n "${MMUI_TEST_LOG:-}" ]; then
	printf 'uci %s %s\n' "$command" "$*" >> "$MMUI_TEST_LOG"
fi

case "$command" in
	show)
		case "${1:-}" in
			mmconfig)
				case "${MMUI_TEST_MODE:-apply}" in
					discover) ;;
					anonymous) printf '%s\n' 'mmconfig.@modem[0]=modem' ;;
					*) printf '%s\n' 'mmconfig.modem1=modem' ;;
				 esac
				;;
			network)
				printf '%s\n' 'network.cell=interface' 'network.unrelated=interface'
				;;
		esac
		;;
	get)
		case "${1:-}" in
			mmconfig.modem1.device|mmconfig.@modem\[0\].device)
				printf '%s\n' '/sys/devices/platform/usb1/1-1'
				;;
			mmconfig.modem1.bands|mmconfig.@modem\[0\].bands)
				if [ "${MMUI_TEST_BAD_BANDS:-0}" = 1 ]; then
					printf '%s\n' 'eutran-99'
				elif [ "${MMUI_TEST_ANY:-0}" = 1 ]; then
					printf '%s\n' any
				elif [ "${MMUI_TEST_EMPTY_BANDS:-0}" = 1 ]; then
					:
				else
					printf '%s\n' 'eutran-1 ngran-78'
				fi
				;;
			network.cell.proto)
				printf '%s\n' modemmanager
				;;
			network.cell.device)
				printf '%s\n' '/sys/devices/platform/usb1/1-1'
				;;
			network.cell.allowedmode)
				printf '%s\n' '4g|3g'
				;;
			network.cell.preferredmode)
				if [ "${MMUI_TEST_BAD_MODE:-0}" = 1 ]; then
					printf '%s\n' 3g
				else
					printf '%s\n' 4g
				fi
				;;
			network.unrelated.proto)
				printf '%s\n' modemmanager
				;;
			network.unrelated.device)
				printf '%s\n' '/sys/devices/platform/usb1/1-10'
				;;
		esac
		;;
	add)
		printf '%s\n' cfgdiscovered
		;;
	set|commit)
		;;
esac
