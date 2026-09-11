#!/usr/bin/env python3
"""Regression checks for the TurboACC control-plane safety boundary."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "package/mtk/applications/luci-app-turboacc-mtk"
INIT = PACKAGE / "root/etc/init.d/turboacc"
DEFAULTS = PACKAGE / "root/etc/uci-defaults/turboacc"
VIEW = PACKAGE / "htdocs/luci-static/resources/view/turboacc.js"


class TurboaccSafetyTests(unittest.TestCase):
    def test_service_never_reconfigures_network_topology(self):
        source = INIT.read_text()
        for config in ("network", "dhcp", "wireless"):
            self.assertNotIn(f"uci set {config}.", source)
            self.assertNotIn(f"uci commit {config}", source)
            self.assertNotIn(f"uci -q delete {config}.", source)

    def test_ap_conversion_is_not_exposed(self):
        self.assertNotIn("fastpath_mh_eth_hnat_ap", INIT.read_text())
        self.assertNotIn("fastpath_mh_eth_hnat_ap", VIEW.read_text())

    def test_upgrade_removes_legacy_ap_setting(self):
        source = DEFAULTS.read_text()
        self.assertIn(
            'uci -q delete "turboacc.config.fastpath_mh_eth_hnat_ap"',
            source,
        )

    def test_hnat_controls_remain_available(self):
        init = INIT.read_text()
        view = VIEW.read_text()
        for option in (
            "fastpath_mh_eth_hnat",
            "fastpath_mh_eth_hnat_v6",
            "fastpath_mh_eth_hnat_bind_rate",
        ):
            self.assertIn(option, init)
            self.assertIn(option, view)


if __name__ == "__main__":
    unittest.main()
