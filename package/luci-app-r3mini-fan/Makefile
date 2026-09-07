include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-r3mini-fan
PKG_VERSION:=1.0.0
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only
LUCI_TITLE:=BPI R3 Mini PWM fan and thermal control
LUCI_DEPENDS:=+kmod-hwmon-pwmfan +rpcd +uci
LUCI_PKGARCH:=all

define Package/$(PKG_NAME)/conffiles
/etc/config/r3mini-fan
endef

include $(TOPDIR)/feeds/luci/luci.mk
# call BuildPackage - OpenWrt buildroot signature
