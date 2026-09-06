# Go toolchain compatibility

Final download follow-up: the SDK was successfully downloaded from
`https://mirrors.nju.edu.cn/golang/go1.26.8.linux-amd64.tar.gz` and verified as
SHA-256 `d0f743b33e8d8945e6b1f432edd15785c70507121d6e2a723b21285eddf8b57b`.
The mirror is now an additional hash-checked recipe fallback. The earlier TLS
failure described below has been resolved for this workspace. Actual target
package compilation remains outside this preparation pass.

核查日期：2026-09-06。

The 24.10 packages feed in this tree builds its default host Go toolchain from
source as Go 1.23.12.  `feeds/packages/lang/golang/golang-package.mk` also
sets `GOTOOLCHAIN=local`, so a module's `go` line cannot silently download a
newer toolchain during a package build.  This is the right reproducibility
policy, but it exposes the following compatibility boundary:

| source/package | module declaration checked | selected compiler |
| --- | --- | --- |
| filebrowser 2.43.0 | `go 1.24` | pinned host SDK 1.26.8 |
| mihomo-meta 1.19.30 (`with_gvisor`) | `go 1.20`; dependency graph includes modules dated 2026-08 | pinned host SDK 1.26.8 |
| mihomo-alpha (2026-08-16 snapshot, `with_gvisor`) | same source family and build tags | pinned host SDK 1.26.8 |
| daed 1.27.0 | dae-wing declares `go 1.22.0` and `toolchain go1.23.6` | feed Go 1.23.12 |
| tailscale 1.80.3 | `go 1.23.1` | feed Go 1.23.12 |
| xray-core 25.2.21 | `go 1.23` | feed Go 1.23.12 |

The exact source module files used for this audit are retained outside the
source tree as `/tmp/r3mini-filebrowser-go.mod`,
`/tmp/r3mini-mihomo-go.mod`, `/tmp/r3mini-tailscale-go.mod`, and
`/tmp/r3mini-xray-go.mod`.  They were read in full before changing recipes.
Mihomo's declared `go 1.20` alone is not enough evidence for its current
dependency graph: the selected graph contains newer MetaCubeX forks of
gVisor, quic-go, tailscale and related packages, so it is isolated on the
newer SDK until an actual target build proves otherwise.

## Implemented strategy

`package/devel/golang-host-compat/Makefile` adds the host-only package
`golang-host-compat/host`.  It downloads the official Linux x86-64 Go SDK
`go1.26.8.linux-amd64.tar.gz` from `go.dev/dl` (with `dl.google.com/go` as a
mirror) and verifies SHA-256
`d0f743b33e8d8945e6b1f432edd15785c70507121d6e2a723b21285eddf8b57b`.
The SDK is installed only at
`$(STAGING_DIR_HOSTPKG)/lib/go-1.26.8`; the package deliberately does not
create `/bin/go` or a global alternative.  It therefore cannot change the
compiler selected by unrelated Go packages.

The filebrowser and both mihomo variants now declare
`golang-host-compat/host` instead of `golang/host`.  After including the
existing Go package framework, each app appends the SDK's `bin` directory to
`GO_PKG_BUILD_VARS`:

```make
GO_PKG_BUILD_VARS += \
	PATH="$(STAGING_DIR_HOSTPKG)/lib/go-1.26.8/bin:$$$$PATH"
```

The framework continues to supply target `GOOS`, `GOARCH`, cgo compiler
variables, `GOMODCACHE`, `GOENV=off`, and `GOTOOLCHAIN=local`.  The SDK is a
host executable; the resulting filebrowser/mihomo binaries are still cross
compiled for the selected OpenWrt target with the target compiler.  No global
Go version bump, main `.config` edit, target Node package, or firmware build
is part of this change.

## Upstream comparison

The checked out `feeds/packages` branch is the 24.10 single-version recipe.
The available upstream `origin/master` revision
`8509f551edb7beb4a6324afca4d84b2bea404b66` (2026-09-03) has since introduced
`golang-version.mk`, `GO_DEFAULT_VERSION`/`GO_HOST_VERSION`, and versioned
`golang1.27` packages.  That is the maintained long-term direction for a
feed-wide multi-version Go setup.  Backporting that framework wholesale would
also change the target Go packaging and expose older dae/gVisor/quic-go code
to a newer compiler.  The local host-only SDK keeps the same per-package
selection idea while limiting the change to the two modern dependency graphs
that require it.

## Verification completed

The following checks were completed without compiling firmware:

* The four retained module files were inspected, including their `go` lines
  and dependency requirements.
* The official Go download metadata was checked for the 1.26.8 Linux x86-64
  archive and the recipe hash recorded above.
* The active full download job was allowed to finish before changing the
  selected package recipes; the filebrowser, mihomo, tailscale and xray source
  download locks were free before those recipes were edited.
* The compatibility package is host-only, has no target package payload, and
  installs no unversioned Go alternative.  The selected recipes use the
  isolated host dependency and append to the existing recursive
  `GO_PKG_BUILD_VARS` variable after the framework include.

## Checks still requiring a package compile

These are intentionally left for the target build pass:

1. Download and hash verification of the 1.26.8 SDK through the OpenWrt
   `golang-host-compat/host` target.
2. Host extraction/installation and a verbose command check showing that
   filebrowser and mihomo invoke the versioned SDK path while daed, tailscale
   and xray continue to invoke the feed Go toolchain.
3. A target aarch64/musl compile of filebrowser 2.43.0, including its frontend
   step, and of the selected mihomo variant with `with_gvisor`.
4. cgo/linker and runtime checks for the resulting binaries, especially the
   gVisor, quic-go and WireGuard code paths; no claim of firmware or device
   runtime compatibility is made here.
5. A clean parallel package build to ensure the host-only SDK dependency and
   the existing Node host dependencies do not create a dependency cycle or
   race in the generated package metadata.
