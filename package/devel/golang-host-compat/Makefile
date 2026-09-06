# SPDX-License-Identifier: GPL-2.0-only
#
# A pinned host-only Go SDK for packages whose module graph is newer than the
# source-built Go version supplied by the 24.10 packages feed.

include $(TOPDIR)/rules.mk

PKG_NAME:=golang-host-compat
PKG_VERSION:=1.26.8
PKG_RELEASE:=1

# This is the official Linux x86-64 SDK.  It is used on the build host only;
# target binaries are still produced with GOOS/GOARCH and the OpenWrt target
# compiler supplied by golang-package.mk.
PKG_SOURCE:=go$(PKG_VERSION).linux-amd64.tar.gz
PKG_SOURCE_URL:=https://go.dev/dl/ https://dl.google.com/go/ https://mirrors.nju.edu.cn/golang/
PKG_HASH:=d0f743b33e8d8945e6b1f432edd15785c70507121d6e2a723b21285eddf8b57b

PKG_MAINTAINER:=OpenWrt contributors
PKG_LICENSE:=BSD-3-Clause
PKG_LICENSE_FILES:=LICENSE

PKG_HOST_ONLY:=1
HOST_BUILD_DIR:=$(BUILD_DIR_HOST)/go-$(PKG_VERSION)-linux-amd64
HOST_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/host-build.mk
include $(INCLUDE_DIR)/package.mk

HOST_UNPACK:=$(HOST_TAR) -C "$(HOST_BUILD_DIR)" --strip-components=1 -xzf "$(DL_DIR)/$(PKG_SOURCE)"

define Package/golang-host-compat
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=Pinned Go $(PKG_VERSION) host SDK
  URL:=https://go.dev/
  BUILDONLY:=1
endef

define Package/golang-host-compat/description
  A pinned official Go SDK for host-side cross-compilation of packages whose
  module requirements exceed the default OpenWrt Go toolchain.
endef

# The SDK is deliberately kept versioned and has no /bin/go alternative.  The
# consuming package opts into it by prepending this directory to PATH in its
# GO_PKG_BUILD_VARS, so other Go packages keep using the feed toolchain.
define Host/Compile
	@test "$$(uname -s)-$$(uname -m)" = Linux-x86_64 || { echo 'This pinned Go host SDK requires Linux x86_64'; exit 1; }
endef

define Host/Install
	rm -rf "$(STAGING_DIR_HOSTPKG)/lib/go-$(PKG_VERSION)"
	$(INSTALL_DIR) "$(STAGING_DIR_HOSTPKG)/lib/go-$(PKG_VERSION)"
	$(CP) "$(HOST_BUILD_DIR)/." "$(STAGING_DIR_HOSTPKG)/lib/go-$(PKG_VERSION)/"
endef

define Host/Uninstall
	rm -rf "$(STAGING_DIR_HOSTPKG)/lib/go-$(PKG_VERSION)"
endef

$(eval $(call BuildPackage,golang-host-compat))
$(eval $(call HostBuild))
