# R3 Mini third-party implementation audit

Final integration follow-up: [implementation.md](implementation.md) records
additional root fixes after this package audit. QoSmate now persists its
offload journal in `/etc/qosmate.d/offload-state`, accepts textual debugfs
readback while writing numeric toggles, and has a boot recovery helper.
Disabled stop/reload does not remove foreign queues; daed and MTK HQoS have
mutual exclusion checks. A firmware-managed marker prevents the upstream
script self-updater from overwriting these board fixes. The LuCI recipes
retain a `call BuildPackage` scan marker without evaluating BuildPackage twice;
QoSmate views are placed under the menu's qosmate namespace during Prepare.
The final snapshots in `patches/r3mini-sources/` supersede earlier patch exports.

This document records the package work completed before the R3 Mini firmware
compile.  It covers the third-party package trees only; the full firmware was
not compiled in this pass as requested.

## QoSmate

The backend package in `package/qosmate` now installs the complete runtime
set expected by its init script:

* `qosmate.sh`, `qosmate-autorate.sh` and `qosmate-autorate-tc.sh`;
* both init scripts (`qosmate` and `qosmate-autorate`);
* the iface hotplug hook;
* `/etc/qosmate.d/qosmate-defaults`, copied from the packaged configuration;
* all five `tc` distribution files; and
* the runtime dependencies that the backend checks itself (`luci-lib-jsonc`,
      `lua`, `jq` and `coreutils-sleep`) in addition to the qdisc and networking
      dependencies.

The upstream `usr/lib/tc/m_xt.so` is a prebuilt x86-64 ELF with no aarch64
variant, and none of the QoSmate scripts loads it.  The R3 Mini install rule
therefore excludes this incompatible shared object; the original source file
is retained only as upstream reference material and is never copied into the
ARM64 package.

The shipped `/etc/config/qosmate` has `global.enabled='0'` and the autorate
section remains disabled.  An image can therefore include the package and
LuCI page without creating qdiscs, IFB devices, nftables tables, or an
autostart symlink.  The hotplug hook exits while that option is zero and only
reacts to the configured WAN after an explicit enable/start.  An explicit
`/etc/init.d/qosmate start` still enables the service, as required for a user
who chooses to turn it on.

QoSmate's old stop path deleted its own packaged hotplug file and its start
path generated a broad hook dynamically.  The package now ships a filtered
WAN hook and keeps it across stop/start cycles.  The init script also snapshots
the generic firewall offload flags and the MediaTek TurboACC fields
`fastpath`, `fastpath_mh_eth_hnat` and `fastpath_mh_eth_hnat_v6`.  While QoSmate
is active it temporarily disables software/hardware flow offloading and the
TurboACC fast path, and writes `0` to the HNAT debugfs hook when available.
On a normal stop or shutdown it restores the saved values and removes the
persistent journal. A restart keeps the snapshot across the stop/start pair.
If a user changes one of the forced UCI values while QoSmate is active, the
restore helper leaves that changed value in place; this prevents an old
snapshot from overwriting an explicit choice.
When the MTK HNAT debugfs control is available, restoration reapplies the IPv6
HNAT and bind-rate settings before the saved hook value is written.  The hook
is restored only while it is still at the temporary zero value, so a runtime
change made during shaping is preserved.

The health check treats the intentional `service:disabled`/`global.enabled=0`
state as healthy and reports runtime nft/tc state as off.  Once the service is
enabled, it resumes checking the nftables table and configured qdiscs.

## LuCI package definition fixes

`package/luci-app-qosmate/Makefile` now installs the missing
`luci.qosmate_stats` RPC backend.  Its translation and package generation is
provided by `feeds/luci/luci.mk`; the hand-written duplicate
`BuildPackage` call was removed.

`package/luci-app-onliner/luci-app-onliner/Makefile` now likewise relies on
the standard `luci.mk` package generation and has no second `BuildPackage`
definition.  The resulting metadata contains one `luci-app-onliner` package
and one translation family, avoiding the duplicate-definition/translation
errors seen in the earlier mixed layout.

## NetSpeedTest source and integration

The source under `package/netspeedtest` is a shallow copy of the requested
public repository `https://github.com/sirpdboy/netspeedtest`, at commit
`0c936e9dd513b2915229871b088b85ca817f5083` (`v5.2.1`).  It supplies the three
separate package definitions:

| Package | Version | Runtime role |
| --- | --- | --- |
| `luci-app-netspeedtest` | `5.2.1-r20260322` | LuCI pages, WAN test wrapper, Homebox/iperf3 controls |
| `homebox` | `1.0.1` | optional LAN web throughput server |
| `ookla-speedtest` | `1.2.0` | official Speedtest CLI client |

The package source's ARM64 downloads were checked separately.  The Homebox
archive is `homebox-linux-arm64-musl-v1.0.1.tar.gz` with SHA-256
`e645229b4cffef9ab1d4b3989f1b9523f487bf3f570c4391c4b62522de3e6b7f`; the
Ookla archive is `ookla-speedtest-1.2.0-linux-aarch64.tgz` with SHA-256
`3953d231da3783e2bf8904b6dd72767c5c6e533e163d3742fd0437affa431bd3`.
The verified download and archive-member record is in
`netspeedtest-aarch64-downloads.json`.

The upstream LuCI tree bundled the old Python `speedtest` script at
`/usr/bin/speedtest` while also selecting the external `speedtest-cli` package
in the migrated configuration.  Both provide the same path, and the old
script does not implement the Ookla command line used by the current wrapper.
The bundled copy and its Python-only dependencies were removed.  The official
client is installed as `/usr/bin/ookla-speedtest`, so it can coexist with an
optional external `speedtest-cli` fallback at `/usr/bin/speedtest` without a
file collision.  The wrapper still detects that fallback when it is present.

The wrapper was converted from Bash to POSIX shell so it runs with OpenWrt's
default ash.  Its Bash-only array selection was replaced with POSIX field
iteration, and its Bash file-descriptor lock was replaced by an atomic lock
directory with stale-PID recovery.  `--help` now runs successfully under the
host `/bin/sh`, which exercises the argument path without executing any
downloaded target binary.

The latest tree had a stale ACL reference to a nonexistent
`luci.netspeedtest` ubus object and omitted direct permissions needed by its
pages.  The ACL now includes the init script, `/bin/ash`, and the UCI config
write/read path, and removes the unused ubus object.  The post-install helper
no longer tries to chmod the removed Python file or restart a nonexistent RPC
backend; it reloads rpcd and refreshes the LuCI cache instead.  Homebox and
iperf3 stay off until their page explicitly enables them, so installing the
package does not start a resident Homebox process.  No Node or npm target
dependency is present.

## Validation performed

The following checks passed in the workspace:

```text
make -s prepare-tmpinfo
sh -n package/qosmate/etc/init.d/qosmate
sh -n package/qosmate/etc/qosmate.sh
sh -n package/qosmate/etc/qosmate-autorate.sh
sh -n package/qosmate/etc/qosmate-autorate-tc.sh
sh -n package/qosmate/etc/init.d/qosmate-autorate
sh -n package/qosmate/etc/hotplug.d/iface/13-qosmateHotplug
sh -n package/netspeedtest/luci-app-netspeedtest/root/usr/bin/netspeedtest.sh
sh -n package/netspeedtest/luci-app-netspeedtest/root/etc/init.d/netspeedtest
sh -n package/netspeedtest/luci-app-netspeedtest/root/etc/uci-defaults/zzz_luci-app-netspeedtest
python3 -m json.tool package/netspeedtest/luci-app-netspeedtest/root/usr/share/luci/menu.d/luci-app-netspeedtest.json
python3 -m json.tool package/netspeedtest/luci-app-netspeedtest/root/usr/share/rpcd/acl.d/luci-app-netspeedtest.json
/bin/sh package/netspeedtest/luci-app-netspeedtest/root/usr/bin/netspeedtest.sh --help
git -C package/qosmate diff --check
git -C package/luci-app-qosmate diff --check
git -C package/luci-app-onliner diff --check
git -C package/netspeedtest diff --check
```

The generated package metadata contains one entry each for `qosmate`,
`luci-app-qosmate`, `luci-app-onliner`, `luci-app-netspeedtest`, `homebox`
and `ookla-speedtest`.  `luci-app-qosmate` exposes the statistics RPC package
file through its install rule, and `luci.mk` is the only package-generation
mechanism in both LuCI Makefiles.

`prepare-tmpinfo` emitted three existing unrelated dependency warnings for
`rpcd-mod-rad3-enc`, `kmod-mhi-wwan`, and `kmod-qca-nss-drv`; they are recorded
for the parent build preparation and were not changed here.  No full firmware
compile and no downloaded ARM binary execution were performed.  The nested
repository base revisions and exact diff commands are recorded in
`patches/r3mini-local/README.md`.
