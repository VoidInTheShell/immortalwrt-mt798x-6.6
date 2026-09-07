'use strict';
'require view';
'require form';
'require rpc';
'require poll';

var getStatus = rpc.declare({ object: 'r3mini-fan', method: 'status', expect: { '': {} } });

return view.extend({
	render: function() {
		var m = new form.Map('r3mini-fan', 'PWM 风扇',
			'由内核根据 CPU 温度自动调速，保留过热保护及固定 2°C 回差。R3 Mini 的 PWM 为反向控制：255 为停转端，0 为全速端。');
		var s = m.section(form.TypedSection);
		s.render = function() {
			var status = E('p', {}, '正在读取风扇状态…');
			poll.add(function() {
				return getStatus().then(function(v) {
					status.textContent = !v.available ? '未检测到 pwm-fan 控制器' :
						'CPU：' + (v.temperature / 1000).toFixed(1) + ' °C | PWM：' + v.pwm +
						' | 散热档位：' + v.state + '/' + v.max_state + ' | 温控：' + v.governor +
						' | 生效阈值：' + [v.low_temp, v.medium_temp, v.high_temp].map(function(t) { return t / 1000; }).join('/') + ' °C' +
						' | ' + (v.rpm == null ? '无转速反馈（无法读取 RPM）' : v.rpm + ' RPM');
				});
			}, 5);
			return E('div', { 'class': 'cbi-section' }, [status]);
		};
		s = m.section(form.NamedSection, 'config', 'fan');
		[['low_temp', '低速启动温度', '45'], ['medium_temp', '中速温度', '55'],
		 ['high_temp', '全速温度', '65']].forEach(function(field) {
			var o = s.option(form.Value, field[0], field[1] + '（°C）');
			o.default = field[2];
			o.rmempty = false;
			o.datatype = 'range(35,95)';
			o.validate = function(section, value) {
				var values = {};
				['low_temp', 'medium_temp', 'high_temp'].forEach(function(k) {
					var item = m.lookupOption(k, section)[0];
					values[k] = +(k === field[0] ? value : item.formvalue(section));
				});
				return values.low_temp + 2 < values.medium_temp &&
					values.medium_temp + 2 < values.high_temp || '各档温度必须递增，且间隔大于 2°C 回差';
			};
		});
		return m.render();
	}
});
