include $(TOPDIR)/rules.mk

# The package name follows the upstream luci-app-mmconfig identity while the
# source is kept in this tree's dedicated package directory.
PKG_NAME:=luci-app-mmconfig
PKG_VERSION:=0.1.2
PKG_RELEASE:=3

PKG_MAINTAINER:=PortalWRT
PKG_LICENSE:=GPL-3.0-only

# The directory name documents the local integration boundary; keep LuCI's
# translation package basename aligned with the upstream package identity.
LUCI_NAME:=luci-app-mmconfig
LUCI_TITLE:=LuCI ModemManager band and mode configuration
LUCI_DESCRIPTION:=Configure ModemManager cellular bands and netifd radio modes
LUCI_DEPENDS:=+luci-proto-modemmanager +modemmanager-rpcd +jsonfilter +uci
LUCI_PKGARCH:=all

define Package/$(PKG_NAME)/conffiles
/etc/config/mmconfig
endef

define Package/$(PKG_NAME)/description
 A LuCI page for selecting ModemManager supported cellular bands.
 Radio mode choices are kept in the matching netifd modemmanager interface.
 This package does not provide a second modem manager or a vendor dialler.
endef

include $(TOPDIR)/feeds/luci/luci.mk

# luci.mk metadata scan marker; keep this package in the standard LuCI build
# path so translations and static resources are indexed by the feed tooling.
# call BuildPackage - OpenWrt buildroot signature
