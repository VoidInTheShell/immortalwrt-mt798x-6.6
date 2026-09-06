-- Host-only test: MM CLI responses are mocked; no router command is executed.
local source = 'feeds/packages/net/modemmanager/files/usr/libexec/rpcd/modemmanager'
local real_print = print
for _, cellular in ipairs({true, false}) do
    local captured
    package.loaded.cjson = nil
    package.preload.cjson = function()
        return {
            decode = function(s)
                if s == 'list' then return {['modem-list']={'/org/freedesktop/ModemManager1/Modem/0'}} end
                if s == 'status 100% available' then
                    local modem = {generic={device='/sys/devices/mock', sim='--', bearers={},
                        ['signal-quality']={value=80}, ['access-technologies']={'lte'}}}
                    if cellular then modem['3gpp']={imei='test-imei', ['operator-name']='100% Test'} end
                    if not cellular then modem.generic.sim=nil; modem.generic.bearers=nil end
                    return {modem=modem}
                end
                if s == 'optional' then return {modem={}} end
                error('unexpected mocked JSON input')
            end,
            encode = function(value) captured=value; return 'mock-json' end
        }
    end
    io.popen = function(command)
        local response
        if command:find('--list-modems', 1, true) then response='list'
        elseif command:find('--signal-get', 1, true) or command:find('--location-get', 1, true) then response='optional'
        elseif command:find('--modem=', 1, true) then response='status 100% available'
        else error('Unexpected command: '..command) end
        return {read=function() return response end, close=function() return true end}
    end
    print = function() end
    arg = {'call', 'info'}
    dofile(source)
    assert(captured and #captured.modem == 1, 'modem disappeared from RPC info')
    assert(captured.modem[1].signal == 80 and captured.modem[1].technology == 'lte')
    if cellular then assert(captured.modem[1].operator == '100% Test')
    else assert(captured.modem[1].imei == nil) end
end
real_print('ModemManager RPC: percent values and absent optional/3GPP data passed')
