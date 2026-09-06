# luci-app-mmconfig

This package carries the band-control LuCI view from the `luci-app-mmconfig`
application in `koshev-msk/modemfeed` at commit
`8e4f19d8f11171872c99529166ca7344fe86080a` (2026-08-27), adapted for the
ModemManager-only R3 Mini image.

The page uses the official `modemmanager_helper` and ModemManager JSON
responses. It does not scan modem ports, start a vendor dialler, or install a
second modem manager. Radio modes are edited on the matching netifd
`proto=modemmanager` interface so `allowedmode` and `preferredmode` remain the
single source of truth. Leaving `bands` empty is inert; the page's explicit
`Automatic (all supported bands)` choice stores `bands=any` and sends
ModemManager's automatic-band reset when a previous restriction must be undone.
