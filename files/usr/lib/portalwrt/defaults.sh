#!/bin/sh
# 只定义 UCI 操作；由 uci-defaults 调用，也可在隔离的 UCI 目录中测试。

portal_section() {
    local config="$1" type="$2" key="$3" value="$4" section
    for section in $(uci -q show "$config" | sed -n "s/^$config\.\([^.=]*\)=$type$/\1/p"); do
        if [ "$(uci -q get "$config.$section.$key")" = "$value" ]; then
            printf '%s\n' "$section"
            return 0
        fi
    done
    return 1
}

portal_bridge() {
    local ports="$1" section port
    [ -n "$ports" ] || return 1
    section=$(portal_section network device name br-lan) || {
        section=portal_lan
        uci set "network.$section=device" || return 1
    }
    uci set "network.$section.name=br-lan" || return 1
    uci set "network.$section.type=bridge" || return 1
    uci -q delete "network.$section.ports" || :
    for port in $ports; do
        uci add_list "network.$section.ports=$port" || return 1
    done
    uci -q get network.lan >/dev/null || uci set network.lan=interface || return 1
    uci set network.lan.device=br-lan || return 1
    uci -q delete network.lan.ifname || :
    uci -q delete network.lan.type || :
}

portal_network() {
    local board="$1" target="$2" interfaces="$3" wan='' lan='' port single=0
    if [ "${PORTAL_ENABLE_PPPOE:-0}" = 1 ]; then
        [ -n "$PORTAL_PPPOE_ACCOUNT" ] && [ -n "$PORTAL_PPPOE_PASSWORD" ] || return 1
    fi
    case "$board" in
        bananapi,bpi-r3-mini|radxa,e20c|friendlyarm,nanopi-r5c)
            wan=eth1; lan=eth0 ;;
        *)
            case "$target" in
                x86/*)
                    # x86 保持原来的首口 WAN 习惯；其他板子保留 board.d/DSA 映射。
                    for port in $interfaces; do
                        if [ -z "$wan" ]; then wan=$port; else lan="$lan $port"; fi
                    done
                    [ -n "$wan" ] || return 1
                    if [ -z "$lan" ]; then lan=$wan; wan=''; single=1; fi
                    ;;
            esac
            ;;
    esac
    if [ -n "$lan" ]; then
        for port in $lan $wan; do
            case " $interfaces " in *" $port "*) ;; *) return 1 ;; esac
        done
        portal_bridge "$lan" || return 1
    fi
    if [ "$single" = 1 ]; then
        uci set network.lan.proto=dhcp || return 1
        for port in ipaddr netmask gateway dns; do uci -q delete "network.lan.$port" || :; done
        # 单口不能同时保留另一个绑定同口的 WAN DHCP 客户端。
        uci -q delete network.wan || :
        uci -q delete network.wan6 || :
        uci -q get dhcp.lan >/dev/null || uci set dhcp.lan=dhcp || return 1
        uci set dhcp.lan.interface=lan || return 1
        uci set dhcp.lan.ignore=1 || return 1
    else
        if [ -n "$wan" ]; then
            uci set network.wan=interface || return 1
            uci set "network.wan.device=$wan" || return 1
            uci set network.wan.proto=dhcp || return 1
            uci set network.wan6=interface || return 1
            uci set "network.wan6.device=$wan" || return 1
            uci set network.wan6.proto=dhcpv6 || return 1
            uci -q get dhcp.lan >/dev/null || uci set dhcp.lan=dhcp || return 1
            uci set dhcp.lan.interface=lan || return 1
            uci set dhcp.lan.ignore=0 || return 1
        fi
        uci set network.lan.proto=static || return 1
        uci set "network.lan.ipaddr=$PORTAL_LAN_IP" || return 1
        uci set "network.lan.netmask=$PORTAL_LAN_NETMASK" || return 1
        if [ "${PORTAL_ENABLE_PPPOE:-0}" = 1 ]; then
            uci set network.wan.proto=pppoe || return 1
            uci set "network.wan.username=$PORTAL_PPPOE_ACCOUNT" || return 1
            uci set "network.wan.password=$PORTAL_PPPOE_PASSWORD" || return 1
            uci set network.wan.peerdns=1 || return 1
            uci set network.wan.auto=1 || return 1
            uci set network.wan6.proto=none || return 1
        fi
    fi
    uci commit network || return 1
    uci commit dhcp
}

portal_android_time() {
    local section
    section=$(portal_section dhcp domain name time.android.com) || section=portal_android_time
    uci set "dhcp.$section=domain" || return 1
    uci set "dhcp.$section.name=time.android.com" || return 1
    uci set "dhcp.$section.ip=203.107.6.88" || return 1
    uci commit dhcp
}

portal_access() {
    local section
    if [ "${PORTAL_ALLOW_WAN_INPUT:-1}" = 1 ]; then
        section=$(portal_section firewall zone name wan) || return 1
        uci set "firewall.$section.input=ACCEPT" || return 1
        uci commit firewall || return 1
    fi
    if uci -q get 'dropbear.@dropbear[0]' >/dev/null; then
        uci -q delete 'dropbear.@dropbear[0].Interface' || :
        uci commit dropbear || return 1
    fi
    if uci -q get 'ttyd.@ttyd[0]' >/dev/null; then
        uci -q delete 'ttyd.@ttyd[0].interface' || :
        uci commit ttyd || return 1
    fi
}

portal_forwarding() {
    local src="$1" dest="$2" section
    for section in $(uci -q show firewall | sed -n 's/^firewall\.\([^.=]*\)=forwarding$/\1/p'); do
        if [ "$(uci -q get "firewall.$section.src")" = "$src" ] &&
           [ "$(uci -q get "firewall.$section.dest")" = "$dest" ]; then return 0; fi
    done
    section="portal_${src}_${dest}"
    uci set "firewall.$section=forwarding" || return 1
    uci set "firewall.$section.src=$src" || return 1
    uci set "firewall.$section.dest=$dest"
}

portal_docker() {
    local section
    section=$(portal_section firewall zone name docker) || section=docker
    uci set "firewall.$section=zone" || return 1
    uci set "firewall.$section.name=docker" || return 1
    uci set "firewall.$section.input=ACCEPT" || return 1
    uci set "firewall.$section.output=ACCEPT" || return 1
    uci set "firewall.$section.forward=ACCEPT" || return 1
    uci -q delete "firewall.$section.subnet" || :
    uci add_list "firewall.$section.subnet=172.16.0.0/12" || return 1
    portal_forwarding docker lan || return 1
    portal_forwarding docker wan || return 1
    portal_forwarding lan docker || return 1
    uci commit firewall
}

portal_theme() {
    local section
    # UCI basic section 是当前 KuCat UCode 模板实际使用的配置接口。
    section=$(uci -q show kucat | sed -n 's/^kucat\.\([^.=]*\)=basic$/\1/p' | head -n 1)
    [ -n "$section" ] || section=basic
    uci set "kucat.$section=basic" || return 1
    uci set "kucat.$section.mode=light" || return 1
    uci set "kucat.$section.bkuse=1" || return 1
    uci set "kucat.$section.bklock=1" || return 1
    uci set "kucat.$section.background=0" || return 1
    uci set "kucat.$section.primary_rgbm=252,217,229" || return 1
    uci set "kucat.$section.primary_rgbbody=252,217,229" || return 1
    uci set "kucat.$section.primary_rgbm_ts=0" || return 1
    uci set "kucat.$section.bgqs=1" || return 1
    uci set "kucat.$section.dayword=0" || return 1
    uci set luci.themes.KuCat=/luci-static/kucat || return 1
    uci set luci.main.mediaurlbase=/luci-static/kucat || return 1
    uci commit kucat || return 1
    uci commit luci
}
