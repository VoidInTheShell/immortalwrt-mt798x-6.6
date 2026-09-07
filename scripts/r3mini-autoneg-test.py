#!/usr/bin/env python3
"""Host regressions for PHY wiring and the actual HNAT PPD selection C code.

These tests do not emulate PPE hardware or replace cable/throughput tests.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HNAT = ROOT / 'target/linux/mediatek/files-6.6/drivers/net/ethernet/mediatek/mtk_hnat'
DTS = ROOT / 'target/linux/mediatek/dts/mt7986a-bananapi-bpi-r3-mini.dts'
PATCH = ROOT / 'target/linux/mediatek/patches-6.6/9999-04-hnat-independent-ppd.patch'


def function(source, name):
    start = source.rfind('\n', 0, source.index(name + '(')) + 1
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def run_c(code):
    with tempfile.TemporaryDirectory(prefix='r3mini-autoneg-test-') as temp:
        path = Path(temp)
        (path / 'test.c').write_text(code)
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', str(path / 'test.c'),
                        '-o', str(path / 'test')], check=True)
        subprocess.run([str(path / 'test')], check=True,
                       env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})


class AutonegTests(unittest.TestCase):
    def test_board_attaches_both_real_phys(self):
        text = DTS.read_text()
        eth = text[text.index('&eth {'):text.index('&i2c0 {')]
        self.assertNotIn('fixed-link', eth)
        self.assertIn('mediatek,hnat-ppd;', eth)
        self.assertIn('mtketh-ppd = "ppe0";', text)
        self.assertIn('mediatek,ppd-isolated;', text)
        for index, address in ((0, 14), (1, 15)):
            mac = re.search(r'gmac' + str(index) + r': mac@\d+ \{(.*?)\};', eth, re.S)[1]
            self.assertIn('phy-mode = "2500base-x";', mac)
            self.assertIn('phy-handle = <&phy' + str(address) + '>;', mac)
            phy = re.search(r'phy' + str(address) + r': ethernet-phy@([ef]) \{(.*?)\};', eth, re.S)
            self.assertEqual(int(phy[1], 16), address)
            self.assertIn('airoha,phy-handle;', phy[2])
            self.assertIn('airoha,pnswap-rx;', phy[2])
            self.assertIn('IRQ_TYPE_EDGE_FALLING', phy[2])

    def test_live_ppd_selection_compiled_from_driver(self):
        source = (HNAT / 'hnat_nf_hook.c').read_text()
        code = '\n\n'.join(function(source, name) for name in
                           ('hnat_ppd_detach', 'hnat_ppd_usable',
                            'hnat_update_ppd', 'hnat_get_ppd'))
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
enum { NETREG_REGISTERED, NETREG_UNREGISTERING };
struct net_device {
    const char *name;
    bool running, carrier;
    int reg_state;
};
struct list_head { int unused; };
static struct net_device devices[] = {
    {"eth0", true, false, 0}, {"eth1", true, false, 0},
    {"ra0", true, true, 0}, {"br-lan", true, true, 0},
    {"ppe0", true, true, 0}
};
static struct net_device *lowers[4];
static int init_net, eth1_in_br;
static struct net_device *ppd_dev;
static struct net_device *ppd_rxdev;
static int hook_toggle = 1, rx_error, detach_count;
static struct { char ppd[16], wan[16]; struct net_device *g_ppdev, *g_wandev;
    bool ppd_isolated; }
    priv = { .ppd = "eth0", .wan = "eth1" }, *hnat_priv = &priv;
#define ASSERT_RTNL() ((void)0)
#define rcu_assign_pointer(p, v) ((p) = (v))
#define rcu_dereference(p) (p)
#define atomic_set(p, v) (*(p) = (v))
#define netif_running(d) ((d)->running)
#define netif_carrier_ok(d) ((d)->carrier)
#define netdev_err(...) ((void)0)
static void hnat_ppd_rx_handler(void) {}
static int netdev_rx_handler_register(struct net_device *dev,
                                     void (*fn)(void), void *data)
{ (void)dev; (void)fn; (void)data; return rx_error; }
static void netdev_rx_handler_unregister(struct net_device *dev)
{ assert(dev); ++detach_count; }
#define netdev_for_each_lower_dev(br, dev, pos) \
    for (size_t i = 0; (void)(pos), (void)(br), i < 4 && ((dev) = lowers[i]); ++i)
static struct net_device *__dev_get_by_name(int *net, const char *name)
{
    (void)net;
    for (size_t i = 0; i < 5; ++i)
        if (!strcmp(devices[i].name, name)) return &devices[i];
    return NULL;
}
'''
        cases = r'''
int main(void)
{
    /* Non-opt-in boards retain the legacy physical PPD selection. */
    lowers[0] = &devices[0]; lowers[1] = &devices[2];
    hnat_update_ppd(NULL);
    assert(!hnat_get_ppd()); assert(ppd_dev == &devices[2]);
    /* 100/1000/2500 copper all provide the same carrier eligibility. */
    devices[0].carrier = true;
    hnat_update_ppd(NULL);
    assert(hnat_get_ppd() == &devices[0]); assert(ppd_dev == &devices[0]);
    assert(eth1_in_br == 0);
    /* Only WAN online: shared DMA uses GMAC1; bridge returns via WiFi. */
    devices[0].carrier = false; devices[1].carrier = true;
    hnat_update_ppd(NULL);
    assert(hnat_get_ppd() == &devices[1]); assert(eth1_in_br == 1);
    assert(ppd_dev == &devices[2]);
    /* Carrier changes before the notifier: packet-path check catches it. */
    devices[1].carrier = false;
    assert(!hnat_get_ppd());
    devices[0].carrier = devices[1].carrier = true;
    hnat_update_ppd(NULL);
    assert(hnat_get_ppd() == &devices[0]);
    /* GOING_DOWN / UNREGISTER must exclude the still-UP device. */
    hnat_update_ppd(&devices[0]);
    assert(hnat_get_ppd() == &devices[1]); assert(ppd_dev == &devices[2]);
    devices[0].reg_state = NETREG_UNREGISTERING;
    hnat_update_ppd(NULL);
    assert(hnat_get_ppd() == &devices[1]);
    /* No return bridge / no active lower: never reuse a stale rx pointer. */
    hnat_update_ppd(&devices[3]); assert(!hnat_get_ppd()); assert(!ppd_dev);
    lowers[0] = NULL;
    hnat_update_ppd(NULL); assert(!hnat_get_ppd()); assert(!ppd_dev);
    /* Preferred interface and physical selection survive bridge changes. */
    lowers[0] = &devices[2];
    devices[0].reg_state = NETREG_REGISTERED;
    strcpy(priv.ppd, "eth1");
    hnat_update_ppd(NULL); assert(hnat_get_ppd() == &devices[1]);
    devices[1].running = false;
    hnat_update_ppd(NULL); assert(hnat_get_ppd() == &devices[0]);
    /* Module/notifier startup before the named devices exist. */
    devices[0].name = "absent0"; devices[1].name = "absent1";
    hnat_update_ppd(NULL);
    assert(!hnat_get_ppd()); assert(!hnat_priv->g_wandev);
    /* R3 Mini: NO cable, internal DMA and bridge return remain usable. */
    priv.ppd_isolated = true;
    strcpy(priv.ppd, "ppe0");
    devices[0].name = "eth0"; devices[1].name = "eth1";
    devices[0].carrier = devices[1].carrier = false;
    hnat_update_ppd(NULL);
    assert(hnat_get_ppd() == &devices[4]);
    assert(ppd_dev == &devices[3]); assert(ppd_rxdev == &devices[4]);
    assert(!eth1_in_br);
    /* Neither physical link loss nor removing all bridge slaves changes TX. */
    lowers[0] = NULL;
    hnat_update_ppd(&devices[0]); assert(hnat_get_ppd() == &devices[4]);
    hnat_update_ppd(&devices[1]); assert(hnat_get_ppd() == &devices[4]);
    /* External recirculation does not need br-lan; CPU helper checks it. */
    hnat_update_ppd(&devices[3]);
    assert(hnat_get_ppd() == &devices[4]); assert(!ppd_dev);
    /* Actual DMA down must not fall back to a physical device. */
    devices[0].carrier = true;
    devices[4].carrier = false;
    assert(!hnat_get_ppd());
    hnat_update_ppd(NULL); assert(!hnat_get_ppd());
    devices[4].carrier = true;
    hnat_update_ppd(NULL); assert(hnat_get_ppd() == &devices[4]);
    /* Unregister excludes still-UP endpoint and removes the RX callback. */
    hnat_update_ppd(&devices[4]);
    assert(!hnat_get_ppd()); assert(!ppd_rxdev); assert(detach_count == 1);
    /* Hook collision must not publish a broken TX path. */
    rx_error = -1;
    hnat_update_ppd(NULL); assert(!hnat_get_ppd()); assert(!ppd_rxdev);
    rx_error = 0;
    hnat_update_ppd(NULL); assert(hnat_get_ppd() == &devices[4]);
    hook_toggle = 0;
    hnat_update_ppd(NULL); assert(!hnat_get_ppd()); assert(!ppd_rxdev);
    hook_toggle = 1;
    hnat_update_ppd(NULL); assert(hnat_get_ppd() == &devices[4]);
    puts("PPD actual-C state-transition checks passed");
    return 0;
}
'''
        run_c(harness + code + cases)

    def test_internal_dma_reference_and_completion_identity(self):
        added = '\n'.join(line[1:] for line in PATCH.read_text().splitlines()
                          if line.startswith('+') and not line.startswith('+++'))
        code = '\n'.join(function(added, name) for name in
                         ('mtk_tx_netdev', 'mtk_ppd_open', 'mtk_ppd_stop'))
        run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#define MTK_MAX_DEVS 3
#define MTK_PPD_ID MTK_MAX_DEVS
struct net_device;
struct mtk_eth { struct net_device *netdev[3], *ppd; int refs, fail, closes; };
struct mtk_mac { struct mtk_eth *hw; bool dma_up; };
struct net_device { struct mtk_mac mac; bool carrier, queue; };
#define netdev_priv(d) (&(d)->mac)
#define netif_carrier_on(d) ((d)->carrier = true)
#define netif_carrier_off(d) ((d)->carrier = false)
#define netif_start_queue(d) ((d)->queue = true)
#define netif_tx_disable(d) ((d)->queue = false)
static int mtk_dma_open(struct mtk_eth *eth)
{ if (eth->fail) return -1; ++eth->refs; return 0; }
static int mtk_dma_close(struct mtk_eth *eth)
{ assert(eth->refs > 0); --eth->refs; ++eth->closes; return 0; }
''' + code + r'''
int main(void)
{
    struct mtk_eth eth = {0};
    struct net_device ppd = {.mac.hw = &eth}, phy = {0};
    eth.ppd = &ppd; eth.netdev[0] = &phy;
    assert(mtk_tx_netdev(&eth, MTK_PPD_ID) == &ppd);
    assert(mtk_tx_netdev(&eth, 0) == &phy);
    assert(!mtk_tx_netdev(&eth, 2)); assert(!mtk_tx_netdev(&eth, 100));
    assert(!mtk_ppd_open(&ppd));
    assert(eth.refs == 1 && ppd.carrier && ppd.queue);
    ++eth.refs; /* A physical interface opens the shared ring. */
    assert(!mtk_ppd_stop(&ppd));
    assert(eth.refs == 1 && !ppd.carrier && !ppd.queue);
    assert(!mtk_ppd_stop(&ppd)); assert(eth.refs == 1); /* No double put. */
    --eth.refs; /* Last physical interface goes down. */
    eth.fail = 1;
    assert(mtk_ppd_open(&ppd) == -1); assert(!mtk_ppd_stop(&ppd));
    assert(!eth.refs && eth.closes == 1);
    eth.fail = 0;
    assert(!mtk_ppd_open(&ppd)); assert(eth.refs == 1);
    assert(!mtk_ppd_stop(&ppd)); assert(!eth.refs);
    return 0;
}
''')

    def test_internal_return_keeps_bridge_egress_and_vlan_handling(self):
        text = (HNAT / 'hnat_nf_hook.c').read_text()
        code = function(text, 'do_hnat_ext_to_ge2')
        self.assertIn('if (cpu_return)', code)
        self.assertIn('dev_queue_xmit(skb);', code)
        self.assertIn('if (!cpu_return && ext_vlan', code)
        self.assertIn('netdev_rx_handler_register(tx, hnat_ppd_rx_handler', text)
        self.assertIn('netdev_rx_handler_unregister(ppd_rxdev)', text)
        cpu = function(text, 'do_hnat_cpu_to_ge')
        self.assertLess(cpu.index('rcu_access_pointer(ppd_dev)'), cpu.index('skb_push'))

    def test_internal_endpoint_does_not_program_a_third_mac(self):
        text = PATCH.read_text()
        self.assertIn('+\tcase MTK_PPD_ID:', text)
        self.assertIn('+\t\tdata = PSE_PPE0_PORT << TX_DMA_FPORT_SHIFT_V2;', text)
        self.assertIn('IFF_DONT_BRIDGE | IFF_NO_ADDRCONF', text)
        self.assertIn('mtk_ppd_xdp_setup(eth, prog)', text)
        self.assertIn('dev->phydev->interface == PHY_INTERFACE_MODE_2500BASEX', text)
        self.assertIn('+\t\ts.base.speed = SPEED_2500;', text)

    def test_injection_checks_before_modifying_packets(self):
        text = (HNAT / 'hnat_nf_hook.c').read_text()
        for name in ('do_hnat_ext_to_ge', 'do_hnat_cpu_to_ge', 'do_hnat_mape_w2l_fast'):
            code = function(text, name)
            self.assertLess(code.index('hnat_get_ppd()'), code.index('skb_push(') if
                            'skb_push(' in code else code.index('skb_pull('))
            self.assertNotIn('__dev_get_by_name', code)
            self.assertNotIn('skb->dev = hnat_priv->g_ppdev', code)

    def test_cached_devices_have_no_unmatched_puts(self):
        for file in ('hnat_nf_hook.c', 'hnat.c', 'hnat_debugfs.c'):
            text = (HNAT / file).read_text()
            self.assertNotRegex(text, r'dev_put\(hnat_priv->g_(ppdev|wandev)\)')


if __name__ == '__main__':
    unittest.main()
