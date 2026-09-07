include $(TOPDIR)/rules.mk

PKG_NAME:=r3mini-defaults
PKG_VERSION:=2026.09.07
PKG_RELEASE:=4
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/r3mini-defaults
  SECTION:=base
  CATEGORY:=Base system
  TITLE:=PortalWRT R3 Mini feature profile defaults
  DEPENDS:=@TARGET_mediatek_filogic_DEVICE_bananapi_bpi-r3-mini +uci
  PKGARCH:=all
endef

define Package/r3mini-defaults/config
  config R3MINI_FULL_EMMC
    bool "Prepare full-feature images for BPI R3 Mini eMMC"
    default y
    help
      Keep the full software image separate from the 128 MiB NAND factory
      layout. The build profile uses a 2 GiB eMMC production partition.
endef

define Build/Compile
endef

define Package/r3mini-defaults/install
	$(INSTALL_DIR) $(1)/etc/uci-defaults $(1)/etc/init.d $(1)/lib/upgrade/keep.d
	$(INSTALL_BIN) ./files/zzzz-r3mini-services $(1)/etc/uci-defaults/zzzz-r3mini-services
	$(INSTALL_BIN) ./files/r3mini-offload-recover $(1)/etc/init.d/r3mini-offload-recover
	$(INSTALL_DIR) $(1)/usr/share/luci/menu.d
	$(INSTALL_DATA) ./files/luci-menu-modem.json $(1)/usr/share/luci/menu.d/r3mini-modem.json
	printf '%s\n' \
		/etc/config/r3mini-feature-defaults-applied \
		/etc/config/r3mini-zerotier-demand-start-applied \
		/etc/config/r3mini-ntp-service-applied \
		/etc/config/r3mini-haproxy3-migration-applied \
		> $(1)/lib/upgrade/keep.d/r3mini-defaults
endef

$(eval $(call BuildPackage,r3mini-defaults))
