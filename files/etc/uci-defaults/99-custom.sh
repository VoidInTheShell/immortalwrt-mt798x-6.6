#!/bin/sh
# 仅在路由器上执行。所有必须步骤成功才返回 0，让 boot 删除此脚本。
[ -r /etc/openwrt_release ] && command -v uci >/dev/null 2>&1 || exit 1
. /etc/openwrt_release
. /etc/portalwrt.conf
. /usr/lib/portalwrt/defaults.sh
LOGFILE=/etc/config/uci-defaults-log.txt
exec >>"$LOGFILE" 2>&1
echo "Starting PortalWRT defaults at $(date)"

# 固件升级时保留用户后续修改的网络、主机名和访问策略。
if [ "$(uci -q get system.portalwrt.initialized)" != 1 ]; then
    interfaces=''
    for iface in /sys/class/net/*; do
        case "${iface##*/}" in eth*|en*)
            [ -e "$iface/device" ] && interfaces="$interfaces ${iface##*/}" ;;
        esac
    done
    board=$(cat /tmp/sysinfo/board_name 2>/dev/null)
    echo "board=$board target=$DISTRIB_TARGET interfaces=$interfaces"
    portal_network "$board" "$DISTRIB_TARGET" "$interfaces" || exit 1
    portal_android_time || exit 1
    portal_access || exit 1
    if command -v dockerd >/dev/null 2>&1; then portal_docker || exit 1; fi
    uci set "system.@system[0].hostname=$PORTAL_HOSTNAME" || exit 1
    uci set 'system.@system[0].timezone=CST-8' || exit 1
    uci set 'system.@system[0].zonename=Asia/Shanghai' || exit 1
    uci set system.portalwrt=portalwrt || exit 1
    uci set system.portalwrt.initialized=1 || exit 1
    uci commit system || exit 1
fi

# 此兼容处理要在每次固件安装时做，避免升级后 advancedplus 再追加 zsh。
if [ -f /etc/init.d/advancedplus ]; then
    sed -i '\|/usr/bin/zsh|d;\|/bin/zsh|d' /etc/init.d/advancedplus || exit 1
    sed -i '\|/usr/bin/zsh|d' /etc/profile || exit 1
fi
echo "PortalWRT defaults completed at $(date)"
exit 0
