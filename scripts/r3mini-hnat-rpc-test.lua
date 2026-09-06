-- Host-only RPC regression harness; no real router files or services accessed.
local target = "package/mtk/applications/luci-app-turboacc-mtk/root/usr/libexec/rpcd/luci.turboacc"
local hook = "disabled"
local serialized, printed, input_used
package.preload["luci.jsonc"] = function()
  return {
    stringify = function(value) serialized = value; return value and "{}" or "null" end,
    new = function() return { parse = function() return true end, get = function() return {} end } end
  }
end
package.preload["nixio.fs"] = function()
  return {
    readfile = function(path)
      if path:match("hook_toggle$") then return hook end
      if path:match("refcnt$") then return "0" end
      return "cubic"
    end,
    stat = function(path)
      if path == "/sys/kernel/debug/hnat" or path == "/sys/module/mtk_warp" or path == "/sys/module/mt_wifi" then return "dir" end
    end,
    access = function(path) return not path:match("refcnt$") end
  }
end
package.preload["luci.util"] = function()
  return { trim = function(value) return (value:gsub("^%s+", ""):gsub("%s+$", "")) end,
           ubus = function() return { kernel = "6.6.133" } end }
end
package.preload["luci.sys"] = function() return { call = function() return 0 end } end
local original_print, original_read, original_open, original_exit = print, io.read, io.open, os.exit
print = function(_) printed = printed + 1 end
io.read = function() if not input_used then input_used = true; return "{}" end end
io.open = function()
  local lines = { " PPE_NUM = 2 ", "BIND_PPE0=12", "ALL_PPE0=16384" }
  return { lines = function() local n=0; return function() n=n+1; return lines[n] end end,
           close = function() end }
end
os.exit = function(code) assert(code == 0, "unexpected RPC failure") end
local function call(method)
  printed, input_used, serialized = 0, false, nil
  arg = { "call", method }
  assert(loadfile(target))()
  assert(printed == 1, "RPC must emit exactly one JSON value")
  assert(type(serialized) == "table", "RPC must return an object")
  return serialized
end
local disabled = call("getFastPathStat")
assert(disabled.type == nil, "WHNAT config alone must not report active HNAT")
assert(disabled.warp_loaded and disabled.wifi_loaded and disabled.wireless_configured)
hook = "enabled"
assert(call("getFastPathStat").type == "MediaTek HNAT")
assert(call("getMTKPPEStat").PPE_NUM == "2", "PPE keys/values need whitespace trimming")
call("getSystemFeatures")
call("getFullConeStat")
call("getTCPCCAStat")
print, io.read, io.open, os.exit = original_print, original_read, original_open, original_exit
print("TurboACC RPC: single JSON, runtime state and PPE parsing checks passed")
