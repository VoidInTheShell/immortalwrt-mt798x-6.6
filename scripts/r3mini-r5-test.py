#!/usr/bin/env python3
"""Regressions reproducing the r4 dual-band MAC failure and r5 controls."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('autoneg', ROOT / 'scripts/r3mini-autoneg-test.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


class R5Tests(unittest.TestCase):
    def test_actual_multi_profile_mac_merge(self):
        common = ROOT / 'package/mtk/drivers/mt_wifi/src/mt_wifi/embedded/common'
        parser = (common / 'cmm_profile.c').read_text()
        merge = (common / 'multi_profile.c').read_text()
        functions = '\n'.join(helpers.function(parser, name) for name in
                              ('RTMPFindSection', 'RTMPGetKeyParameter', 'RTMPAddKeyParameter', 'RTMPSetKeyParameter'))
        functions += '\n' + helpers.function(merge, 'multi_profile_merge_mac_address')
        code = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wstringop-overflow"
#define IN
#define OUT
#define TRUE 1
#define FALSE 0
#define MAX_PARAM_BUFFER_SIZE 2048
#define MAX_INI_BUFFER_SIZE 16384
#define CONFIG_APSTA_MIXED_SUPPORT
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define MTWF_DBG(...) ((void)0)
#define MTWF_PRINT(...) ((void)0)
#define rtstrstr strstr
#define NdisMoveMemory memmove
#define os_move_mem memmove
#define os_zero_mem(p,n) memset(p,0,n)
#define os_free_mem free
#define os_alloc_mem(a,p,n) (*(p) = malloc(n))
#define os_snprintf_error(n,r) ((r)<0 || (size_t)(r)>=(n))
typedef char RTMP_STRING, CHAR;
typedef unsigned char UCHAR, *PUCHAR;
typedef unsigned long ULONG;
typedef int INT, BOOLEAN;
struct mpf_data { int pf1_num, pf2_num; };
FUNCTIONS
static void check(char *final, char *key, char *expected) {
    char value[25], needle[32];
    assert(RTMPGetKeyParameter(key, value, sizeof(value), final, TRUE));
    assert(!strcmp(value, expected));
    snprintf(needle, sizeof(needle), "\n%s=", key);
    char *first = strstr(final, needle);
    assert(first && !strstr(first + 1, needle));
}
int main(void) {
    char first[MAX_INI_BUFFER_SIZE] = "Default\nMacAddress=02:11:22:33:44:40\nMacAddress1=\nMacAddress2=\nMacAddress3=\nApcliMacAddress1=\n";
    char second[MAX_INI_BUFFER_SIZE] = "Default\nMacAddress=02:11:22:33:44:41\nMacAddress1=\nApcliMacAddress=02:11:22:33:44:51\n";
    char final[MAX_INI_BUFFER_SIZE];
    struct mpf_data mpf = {1, 1};
    strcpy(final, first);
    assert(!multi_profile_merge_mac_address(&mpf, first, second, final));
    check(final, "MacAddress", "02:11:22:33:44:40");
    check(final, "MacAddress1", "02:11:22:33:44:41");
    check(final, "ApcliMacAddress1", "02:11:22:33:44:51");
    /* A second pass must not accumulate duplicate keys. */
    assert(!multi_profile_merge_mac_address(&mpf, first, second, final));
    check(final, "MacAddress1", "02:11:22:33:44:41");
    /* Two VAPs per band: preserve first-band VAP, translate second-band indices. */
    mpf.pf1_num = mpf.pf2_num = 2;
    strcpy(first, "Default\nMacAddress=02:11:22:33:44:40\nMacAddress1=02:11:22:33:44:42\nMacAddress2=\nMacAddress3=\n");
    strcpy(second, "Default\nMacAddress=02:11:22:33:44:41\nMacAddress1=02:11:22:33:44:43\nMacAddress2=02:11:22:33:44:ff\n");
    strcpy(final, first);
    assert(!multi_profile_merge_mac_address(&mpf, first, second, final));
    check(final, "MacAddress1", "02:11:22:33:44:42");
    check(final, "MacAddress2", "02:11:22:33:44:41");
    check(final, "MacAddress3", "02:11:22:33:44:43");
    assert(!strstr(final, "MacAddress4="));
}
'''.replace('FUNCTIONS', functions)
        helpers.run_c(code)

    def test_banner_center(self):
        source = (ROOT / 'files/etc/profile.d/portal-banner.sh').read_text()
        function = helpers.function(source, 'portal_banner_center')
        for value in ('LAN IP: 10.0.1.1 | WAN IP: 203.0.113.1 | Uptime: 123d 23h 59m',
                      'Time: 2026-09-07 15:00:00 | OpenWrt: 24.10.2 | Build: 2026-09-07',
                      'Firmware: PortalWRT 24.10.2 GLaDOS-R3Mini-Autoneg-r6',
                      'Board: Bananapi BPi-R3 Mini | Architecture: aarch64 | Kernel: 6.6.133',
                      'Powered by APERTURE Science'):
            result = subprocess.check_output(['sh', '-c', function + '\nportal_banner_center "$1"', 'test', value], text=True)
            line = result.splitlines()[0]
            self.assertEqual(result, line + '\n')
            left = len(line) - len(line.lstrip())
            right = 128 - len(line)
            self.assertLessEqual(abs(left - right), 1)
        self.assertEqual(max(map(len, source.split("cat <<'LOGO'\n", 1)[1].split('\nLOGO', 1)[0].splitlines())), 128)
        self.assertEqual(source.count('\nportal_banner_center "'), 4)

    def test_fan_active_trips_and_invalid_settings(self):
        source = (ROOT / 'package/luci-app-r3mini-fan/root/etc/init.d/r3mini-fan').read_text()
        self.assertNotIn('> "$zone/trip_point_${trip}_hyst"', source)
        with tempfile.TemporaryDirectory(prefix='r3mini-fan-test-') as tmp:
            path = Path(tmp)
            zone = path / 'thermal_zone0'
            zone.mkdir()
            (zone / 'type').write_text('cpu-thermal\n')
            for i, (kind, temp) in enumerate(zip(('critical', 'hot', 'active', 'active', 'active'),
                                                (125000, 120000, 115000, 85000, 60000))):
                (zone / f'trip_point_{i}_type').write_text(kind + '\n')
                (zone / f'trip_point_{i}_temp').write_text(str(temp) + '\n')
                (zone / f'trip_point_{i}_hyst').write_text('2000\n')
            (path / 'board').write_text('bananapi,bpi-r3-mini\n')
            source = source.replace('/tmp/sysinfo/board_name', str(path / 'board'))
            source = source.replace('/sys/class/thermal', str(path))
            prefix = 'config_load() { :; }; logger() { :; }; config_get() { eval "$1=\\${4}"; }\n'
            subprocess.run(['sh', '-c', prefix + source + '\nstart_service'], check=True)
            self.assertEqual([int((zone / f'trip_point_{i}_temp').read_text()) for i in range(5)],
                             [125000, 120000, 65000, 55000, 45000])
            before = [f.read_bytes() for f in sorted(zone.iterdir())]
            for bad in ('abc', '30', '60', '999999999999999', '45;echo BAD'):
                prefix = 'config_load() { :; }; logger() { :; }; config_get() { eval "$1=\\${4}"; [ "$1" != low ] || low="$BAD"; return 0; }\n'
                result = subprocess.run(['sh', '-c', 'BAD="$1"\n' + prefix + source + '\nstart_service', 'test', bad])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual([f.read_bytes() for f in sorted(zone.iterdir())], before)

    def test_kucat_existing_basic_without_presets(self):
        source = (ROOT / 'package/luci-app-kucat-config/root/usr/bin/kucat-config').read_text()
        prefix = '''
grep() { echo 0; }
seq() { :; }
uci() {
    case "$*" in
        '-q get kucat.@basic[0].mode') echo dark;;
        '-q get kucat.@basic[0].fontmode') echo 0;;
        *) printf '%s\\n' "$*";;
    esac
}
'''
        result = subprocess.run(['sh', '-c', prefix + source], check=True, text=True, capture_output=True)
        self.assertEqual(result.stderr, '')
        self.assertNotIn('set kucat.@basic[0].mode=', result.stdout)
        self.assertNotIn('set kucat.@basic[0].primary_rgbm=', result.stdout)
        # No active preset: reboot must retain the user's custom body color too.
        self.assertNotIn('set kucat.@basic[0].primary_rgbbody=', result.stdout)


if __name__ == '__main__':
    unittest.main()
