#!/bin/sh

# Host-side smoke test for the one-shot HQoS helper.  It uses regular files as
# debugfs/sysctl stand-ins, so it verifies the control flow without requiring
# an MT7986 board or a firmware build.
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script="$script_dir/../files/mtkhqos"
test_root=$(mktemp -d "${TMPDIR:-/tmp}/mtkhqos-test.XXXXXX")
trap 'rm -rf "$test_root"' EXIT HUP INT TERM

debugfs="$test_root/hnat"
state="$test_root/state"
bridge="$test_root/bridge"
uci_dir="$test_root/uci"
functions="$test_root/functions.sh"
bin="$test_root/bin"
mkdir -p "$debugfs" "$bridge" "$uci_dir" "$bin"

# Keep service conflict probes deterministic on a host that may have tc/nft or
# uci installed.  The wrappers represent an inactive software shaper stack.
cat > "$bin/uci" <<'EOF'
#!/bin/sh
exit 1
EOF
cat > "$bin/tc" <<'EOF'
#!/bin/sh
exit 0
EOF
cat > "$bin/nft" <<'EOF'
#!/bin/sh
exit 1
EOF
chmod 755 "$bin/uci" "$bin/tc" "$bin/nft"

# Minimal libuci function shim.  The values deliberately include decimal
# zeroes and leading zeroes: the old decimal_value() loop never terminated on
# the literal value 0, while ash arithmetic may treat values such as 08 as
# invalid octal.
cat > "$functions" <<'EOF'
config_load() { :; }

config_foreach() {
	case "$2" in
		global) "$1" global ;;
		queue) "$1" queue0 ;;
	esac
}

config_get() {
	local variable="$1" section="$2" option="$3" value
	value="${4-}"
	case "$section:$option" in
		global:enabled) value="${MTKHQOS_TEST_ENABLED:-1}" ;;
		global:hqos) value="${MTKHQOS_TEST_HQOS:-1}" ;;
		global:txq_num) value=08 ;;
		global:sch0_enable) value=0 ;;
		global:sch0_mode) value=00 ;;
		global:sch0_bw) value=01000000 ;;
		global:sch1_enable) value=1 ;;
		global:sch1_mode) value=1 ;;
		global:sch1_bw) value=00200000 ;;
		queue0:id) value=00 ;;
		queue0:minrate) value=0 ;;
		queue0:maxrate) value=100 ;;
		queue0:weight) value=04 ;;
		queue0:resv) value=04 ;;
	esac
	eval "$variable=\$value"
}
EOF

printf 'enabled\n' > "$debugfs/hook_toggle"
printf 'enabled\n' > "$debugfs/qos_toggle"
printf 'baseline\n' > "$debugfs/qdma_sch0"
printf 'baseline\n' > "$debugfs/qdma_sch1"
i=0
while [ "$i" -lt 64 ]; do
	printf 'baseline\n' > "$debugfs/qdma_txq$i"
	i=$((i + 1))
done
printf '0\n' > "$bridge/bridge-nf-call-iptables"
printf '0\n' > "$bridge/bridge-nf-call-ip6tables"

run_hqos() {
	MTKHQOS_FUNCTIONS="$functions" \
	MTKHQOS_DEBUGFS="$debugfs" \
	MTKHQOS_STATE_DIR="$state" \
	MTKHQOS_BRIDGE_SYSCTL_DIR="$bridge" \
	MTKHQOS_UCI_CONFIG_DIR="$uci_dir" \
	MTKHQOS_TEST_ENABLED="$test_enabled" \
	MTKHQOS_TEST_HQOS="$test_hqos" \
	PATH="$bin:/usr/bin:/bin" \
		sh "$script" "$1" >/dev/null
}

test_enabled=0
test_hqos=1
run_hqos apply
run_hqos stop
[ "$(cat "$debugfs/qos_toggle")" = enabled ]
[ "$(cat "$debugfs/hook_toggle")" = enabled ]
[ "$(cat "$bridge/bridge-nf-call-iptables")" = 0 ]
[ "$(cat "$bridge/bridge-nf-call-ip6tables")" = 0 ]
[ "$(cat "$debugfs/qdma_txq0")" = baseline ]
[ ! -e "$state/active" ]

printf 'disabled\n' > "$debugfs/qos_toggle"
test_enabled=1
run_hqos apply
[ "$(cat "$debugfs/qos_toggle")" = 1 ]
[ "$(cat "$debugfs/hook_toggle")" = enabled ]
[ "$(cat "$bridge/bridge-nf-call-iptables")" = 1 ]
[ "$(cat "$bridge/bridge-nf-call-ip6tables")" = 1 ]
[ "$(cat "$debugfs/qdma_txq0")" = '0 0 0 1 1000000 4 4' ]
[ "$(cat "$debugfs/qdma_txq7")" = '0 0 0 0 0 0 4' ]
[ -f "$state/active" ]

run_hqos stop
[ "$(cat "$debugfs/qos_toggle")" = 0 ]
[ "$(cat "$debugfs/hook_toggle")" = enabled ]
[ "$(cat "$bridge/bridge-nf-call-iptables")" = 0 ]
[ "$(cat "$bridge/bridge-nf-call-ip6tables")" = 0 ]
[ "$(cat "$debugfs/qdma_txq0")" = '0 0 0 0 0 0 4' ]
[ "$(cat "$debugfs/qdma_txq63")" = '1 0 0 0 0 0 4' ]
[ "$(cat "$debugfs/qdma_sch0")" = '0 wrr 0' ]
[ "$(cat "$debugfs/qdma_sch1")" = '0 wrr 0' ]
[ ! -e "$state/active" ]

echo "mtkhqos smoke test: PASS"
