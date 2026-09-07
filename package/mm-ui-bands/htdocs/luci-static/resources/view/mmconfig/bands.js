'use strict';
'require form';
'require fs';
'require uci';
'require ui';
'require view';
'require modemmanager_helper as helper';

var MODE_ORDER = [ '2g', '3g', '4g', '5g' ];

/* Keep this order in sync with netifd's modemmanager protocol script. */
var ALLOWED_MODE_CHOICES = [
	'any', '2g', '3g', '3g|2g', '4g', '4g|2g', '4g|3g',
	'4g|3g|2g', '5g', '5g|2g', '5g|3g', '5g|3g|2g', '5g|4g',
	'5g|4g|2g', '5g|4g|3g', '5g|4g|3g|2g'
];

function asArray(value) {
	if (Array.isArray(value))
		return value.slice();

	if (typeof value === 'string' && value.length)
		return value.split(/\s+/);

	return [];
}

function safeDevice(value) {
	return typeof value === 'string' &&
		/^[A-Za-z0-9/][A-Za-z0-9_./:+@=-]*$/.test(value);
}

function safeValue(value) {
	return typeof value === 'string' &&
		/^[A-Za-z0-9][A-Za-z0-9._:+-]*$/.test(value);
}

function uniqueSafeValues(values) {
	var result = [];
	var seen = {};

	asArray(values).forEach(function(value) {
		if (safeValue(value) && !seen[value]) {
			seen[value] = true;
			result.push(value);
		}
	});

	return result;
}

function contains(values, value) {
	return asArray(values).indexOf(value) !== -1;
}

function escapeHtml(value) {
	var entities = {
		'&': '&amp;',
		'<': '&lt;',
		'>': '&gt;',
		'"': '&quot;',
		"'": '&#39;'
	};

	return String(value == null ? '' : value).replace(/[&<>"']/g,
		function(character) { return entities[character]; });
}

function normalizeModeSet(value, permitAny) {
	var tokens;
	var seen = {};
	var result = [];

	if (typeof value !== 'string')
		return null;

	tokens = value.replace(/[|,]/g, ' ').trim();
	if (!tokens.length)
		return null;

	tokens = tokens.split(/\s+/);
	for (var i = 0; i < tokens.length; i++) {
		var token = tokens[i];

		if (token === 'any') {
			if (!permitAny || tokens.length !== 1)
				return null;
			return 'any';
		}
		if (MODE_ORDER.indexOf(token) === -1 || seen[token])
			return null;
		seen[token] = true;
	}

	MODE_ORDER.slice().reverse().forEach(function(mode) {
		if (seen[mode])
			result.push(mode);
	});

	return result.length ? result.join('|') : null;
}

function normalizePreferredMode(value) {
	if (value == null)
		return 'none';

	value = String(value).replace(/\s+/g, '');
	if (!value || value === 'none')
		return 'none';

	return MODE_ORDER.indexOf(value) !== -1 ? value : null;
}

function parseModeRecord(value) {
	var allowed;
	var preferred;

	if (typeof value !== 'string')
		return null;

	allowed = /(?:^|;)\s*allowed:\s*([^;]+)/i.exec(value);
	preferred = /(?:^|;)\s*preferred:\s*([^;]+)/i.exec(value);
	if (!allowed)
		return null;

	allowed = normalizeModeSet(allowed[1], true);
	preferred = normalizePreferredMode(preferred ? preferred[1] : 'none');
	if (!allowed || !preferred || (allowed === 'any' && preferred !== 'none'))
		return null;
	if (preferred !== 'none' && allowed.split('|').indexOf(preferred) === -1)
		return null;

	return { allowed: allowed, preferred: preferred };
}

function parseSupportedModes(values) {
	var result = [];
	var seen = {};

	asArray(values).forEach(function(value) {
		var parsed = parseModeRecord(value);
		var fallback;
		var key;

		/* Older MM builds occasionally expose bare mode names; retain support
		 * for those while preferring the full allowed/preferred records. */
		if (!parsed) {
			fallback = normalizeModeSet(value, false);
			if (fallback)
				parsed = { allowed: fallback, preferred: 'none' };
		}
		if (!parsed)
			return;

		key = parsed.allowed + ';' + parsed.preferred;
		if (!seen[key]) {
			seen[key] = true;
			result.push(parsed);
		}
	});

	return result;
}

function modePairUsable(pair) {
	if (pair.allowed === 'any')
		return pair.preferred === 'none';
	if (pair.allowed.indexOf('|') !== -1)
		return pair.preferred !== 'none' && pair.allowed.split('|').indexOf(pair.preferred) !== -1;
	return pair.preferred === 'none';
}

function allowedModeValid(mode, supportedModes, permitAny) {
	var normalized;

	if (mode === 'any' && permitAny)
		return true;
	normalized = normalizeModeSet(mode, false);
	if (!normalized || ALLOWED_MODE_CHOICES.indexOf(normalized) === -1)
		return false;

	return !!normalized && supportedModes.some(function(pair) {
		return pair.allowed === normalized && modePairUsable(pair);
	});
}

function modePairSupported(allowed, preferred, supportedModes, enforceNetifd) {
	var normalizedAllowed = normalizeModeSet(allowed || 'any', true);
	var normalizedPreferred = normalizePreferredMode(preferred);

	if (!normalizedAllowed || !normalizedPreferred)
		return false;
	if (enforceNetifd !== false) {
		if (normalizedAllowed.indexOf('|') !== -1 &&
			(normalizedPreferred === 'none' ||
			 normalizedAllowed.split('|').indexOf(normalizedPreferred) === -1))
			return false;
		if (normalizedAllowed.indexOf('|') === -1 && normalizedPreferred !== 'none')
			return false;
	}

	return supportedModes.some(function(pair) {
		return pair.allowed === normalizedAllowed && pair.preferred === normalizedPreferred;
	});
}

function modeLabel(mode) {
	var labels = {
		'any': _('Any'),
		'2g': _('2G only'),
		'3g': _('3G only'),
		'4g': _('4G only'),
		'5g': _('5G only')
	};

	if (labels[mode])
		return labels[mode];

	return mode.split('|').map(function(part) {
		return part.toUpperCase();
	}).join(' + ');
}

function parseCurrentModes(value) {
	return parseModeRecord(value);
}

function modemRecord(entry) {
	var modem = entry && entry.modem;
	var generic = modem && modem.generic;
	var supportedBands;
	var currentBands;
	var rawSupportedModes;
	var rawCurrentModes;
	var supportedModes;
	var currentModes;
	var invalidModes = false;

	if (!generic || !safeDevice(generic.device))
		return null;

	supportedBands = uniqueSafeValues(generic['supported-bands']).filter(function(value) {
		/* `any` is MM's automatic sentinel, not a checkbox band. */
		return value !== 'any';
	});
	currentBands = uniqueSafeValues(generic['current-bands']);
	rawSupportedModes = asArray(generic['supported-modes']);
	rawCurrentModes = generic['current-modes'];
	supportedModes = parseSupportedModes(rawSupportedModes);
	rawSupportedModes.forEach(function(value) {
		if (!parseModeRecord(value) && !normalizeModeSet(value, false))
			invalidModes = true;
	});
	currentModes = parseCurrentModes(rawCurrentModes);
	if (rawCurrentModes != null && !currentModes)
		invalidModes = true;
	if (currentModes && supportedModes.length &&
		!modePairSupported(currentModes.allowed, currentModes.preferred, supportedModes, false))
		invalidModes = true;

	return {
		modem: modem,
		generic: generic,
		device: generic.device,
		supportedBands: supportedBands,
		currentBands: currentBands,
		supportedModes: supportedModes,
		currentModes: currentModes,
		invalidModes: invalidModes,
		invalidBands: asArray(generic['supported-bands']).some(function(value) {
			return !safeValue(value);
		}),
		invalidCurrentBands: asArray(generic['current-bands']).some(function(value) {
			return value !== 'any' && (!safeValue(value) || !contains(supportedBands, value));
		})
	};
}

function findNetwork(device) {
	var matches = [];

	uci.sections('network', 'interface', function(section) {
		/* Match the complete proto and device values, never a substring. */
		if (section.proto === 'modemmanager' && section.device === device)
			matches.push(section);
	});

	return {
		matches: matches,
		section: matches.length === 1 ? matches[0] : null
	};
}

function networkValue(network, option) {
	if (!network)
		return null;

	return uci.get('network', network['.name'], option);
}

function setNetworkValue(network, option, value) {
	if (!network)
		return;

	if (value == null || value === '' || value === 'any' || value === 'none')
		uci.unset('network', network['.name'], option);
	else
		uci.set('network', network['.name'], option, value);
}

function modemTitle(record, index) {
	var generic = record && record.generic;
	var manufacturer = generic && generic.manufacturer;
	var model = generic && generic.model;
	var title = [ manufacturer, model ].filter(function(value) {
		return typeof value === 'string' && value.length;
	}).join(' ');

	return title || (_('Modem %d').format(index + 1));
}

function modemInfoHtml(record, networkInfo, index) {
	var generic = record.generic;
	var cellular = record.modem['3gpp'] || {};
	var current = generic['current-modes'];
	var networkText = _('No matching ModemManager network interface');
	var networkClass = 'mmconfig-info-warning';
	var html = '<div class="mmconfig-modem-info">';

	if (networkInfo.matches.length === 1) {
		networkText = _('Network interface: ') +
				networkInfo.section['.name'];
		networkClass = 'mmconfig-info-value';
	}
	else if (networkInfo.matches.length > 1) {
		networkText = _('Multiple matching ModemManager interfaces; mode writes are disabled');
	}

	html += '<div class="mmconfig-info-row"><strong>' +
		escapeHtml(modemTitle(record, index || 0)) + '</strong>';
	if (cellular['operator-name'] && cellular['operator-name'] !== '--')
		html += '<span class="mmconfig-info-separator">•</span><span>' +
			escapeHtml(cellular['operator-name']) + '</span>';
	html += '</div>';
	html += '<div class="mmconfig-info-row"><span class="mmconfig-info-label">' +
		escapeHtml(_('ModemManager device')) + '</span><code>' +
		escapeHtml(record.device) + '</code></div>';
	html += '<div class="mmconfig-info-row"><span class="mmconfig-info-label">' +
		escapeHtml(_('Current modes')) + '</span><span>' +
		escapeHtml(current || _('Unavailable')) + '</span></div>';
	html += '<div class="mmconfig-info-row ' + networkClass + '">' +
		escapeHtml(networkText) + '</div>';
	if (record.invalidBands || record.invalidCurrentBands || record.invalidModes)
		html += '<div class="mmconfig-info-row mmconfig-info-warning">' +
				escapeHtml(_('ModemManager reported an invalid band or mode value; it will not be sent back.')) +
			'</div>';
	html += '</div>';

	return html;
}

function groupBands(bands) {
	var groups = {};
	var order = [ '2g', '3g', '4g', '5g' ];

	asArray(bands).forEach(function(value) {
		var match = /^(utran|eutran|ngran)-(\d+)$/.exec(value);
		var key = '2g';
		var title = _('2G / GSM');
		var generationOrder = 1;
		var number = null;
		var label = value;

		if (match) {
			key = { utran: '3g', eutran: '4g', ngran: '5g' }[match[1]];
			title = {
				'3g': _('3G / UMTS'),
				'4g': _('4G / LTE'),
				'5g': _('5G / NR')
			}[key];
			generationOrder = order.indexOf(key) + 1;
			number = parseInt(match[2], 10);
			label = match[1] === 'ngran' ? 'n' + match[2] : 'B' + match[2];
		}

		groups[key] = groups[key] || {
			key: key,
			title: title,
			order: generationOrder,
			bands: []
		};
		groups[key].bands.push({ value: value, label: label, number: number });
	});

	Object.keys(groups).forEach(function(key) {
		groups[key].bands.sort(function(a, b) {
			if (a.number != null && b.number != null)
				return a.number - b.number;
			if (a.number != null)
				return -1;
			if (b.number != null)
				return 1;
			return a.value.localeCompare(b.value);
		});
	});

	return Object.keys(groups).map(function(key) {
		return groups[key];
	}).sort(function(a, b) {
		return a.order - b.order;
	});
}

var BandValue = form.Value.extend({
	supportedBands: [],
	initialBands: [],
	configuredBands: null,

	cfgvalue: function(section_id) {
		return this.configuredBands !== null ? this.configuredBands : this.initialBands;
	},

	formvalue: function(section_id) {
		var node = document.getElementById(this.cbid(section_id));
		var automatic;

		if (!node)
			return [];

		automatic = node.querySelector('input[type="checkbox"][data-band-any]');
		if (automatic && automatic.checked)
			return [ 'any' ];

		return Array.prototype.slice.call(node.querySelectorAll(
			'input[type="checkbox"][data-band-value]:checked')).map(function(input) {
			return input.getAttribute('data-band-value');
		});
	},

	validate: function(section_id, value) {
		var values = asArray(value);
		var seen = {};

		if (values.indexOf('any') !== -1)
			return values.length === 1 ? true : _('Automatic mode cannot be combined with specific bands.');

		for (var i = 0; i < values.length; i++) {
			if (!safeValue(values[i]) || !contains(this.supportedBands, values[i]))
				return _('One or more selected bands are not supported by this modem.');
			if (seen[values[i]])
				return _('A band was selected more than once.');
			seen[values[i]] = true;
		}

		return true;
	},

	write: function(section_id, value) {
		return this.map.data.set('mmconfig', section_id, 'bands', asArray(value));
	},

	remove: function(section_id) {
		return this.map.data.unset('mmconfig', section_id, 'bands');
	},

	renderWidget: function(section_id) {
		var container = E('div', {
			'class': 'mmconfig-bands',
			'id': this.cbid(section_id)
		});
		var automaticInput;
		var automaticSelected = this.configuredBands !== null &&
			asArray(this.configuredBands).length === 1 && this.configuredBands[0] === 'any';
		var selected = {};
		var groups = groupBands(this.supportedBands);

		asArray(this.configuredBands !== null ? this.configuredBands : this.initialBands)
			.forEach(function(value) { selected[value] = true; });

		automaticInput = E('input', {
			'type': 'checkbox',
			'data-band-any': '1',
			'change': function() {
				var inputs;
				var i;

				if (!this.checked)
					return;
				inputs = container.querySelectorAll('input[type="checkbox"][data-band-value]');
				for (i = 0; i < inputs.length; i++)
					inputs[i].checked = false;
			}
		});
		automaticInput.checked = automaticSelected;
		container.appendChild(E('label', { 'class': 'mmconfig-band-any' }, [
			automaticInput,
			E('span', {}, _('Automatic (all supported bands)'))
		]));

		if (!groups.length) {
			container.appendChild(E('div', { 'class': 'mmconfig-bands-empty' },
				_('No supported bands were reported by ModemManager.')));
			return container;
		}

		groups.forEach(function(group) {
			var groupNode = E('div', { 'class': 'mmconfig-band-group' });
			var header = E('div', { 'class': 'mmconfig-band-group-header cbi-rowstyle-2' });
			var actions = E('span', { 'class': 'mmconfig-band-actions' });
			var grid = E('div', { 'class': 'mmconfig-band-grid' });

			actions.appendChild(E('button', {
				'type': 'button',
				'class': 'btn cbi-button cbi-button-neutral mmconfig-band-action',
				'click': function() {
					automaticInput.checked = false;
					var inputs = groupNode.querySelectorAll(
						'input[type="checkbox"][data-band-value]');
					for (var i = 0; i < inputs.length; i++)
						inputs[i].checked = true;
				}
				}, _('All')));
			actions.appendChild(E('button', {
				'type': 'button',
				'class': 'btn cbi-button cbi-button-neutral mmconfig-band-action',
				'click': function() {
					automaticInput.checked = false;
					var inputs = groupNode.querySelectorAll(
						'input[type="checkbox"][data-band-value]');
					for (var i = 0; i < inputs.length; i++)
						inputs[i].checked = false;
				}
			}, _('None')));

			header.appendChild(E('strong', { 'class': 'mmconfig-band-group-title' }, group.title));
			header.appendChild(actions);
			groupNode.appendChild(header);

			group.bands.forEach(function(band, index) {
				var id = this.cbid(section_id) + '-' + index + '-' +
					band.value.replace(/[^A-Za-z0-9_-]/g, '-');
				var input = E('input', {
					'type': 'checkbox',
					'id': id,
					'data-band-value': band.value,
					'change': function() {
						if (this.checked)
							automaticInput.checked = false;
					}
				});

				input.checked = !!selected[band.value];
				grid.appendChild(E('label', {
					'class': 'mmconfig-band-item',
					'for': id,
					'title': band.value
				}, [ input, E('span', { 'class': 'mmconfig-band-label' }, band.label) ]));
			}, this);

			groupNode.appendChild(grid);
			container.appendChild(groupNode);
		}, this);

		return container;
	}
});

function addModeOptions(section, record, networkInfo) {
	var supported = record ? record.supportedModes : [];
	var network = networkInfo.section;
	var allowed = section.option(form.ListValue, '_allowedmode',
		_('Allowed network technology'), _('This is stored on the matching ModemManager network interface.'));
	var preferred;
	var choices = ALLOWED_MODE_CHOICES.filter(function(mode) {
		return mode === 'any' || allowedModeValid(mode, supported, false);
	});
	var preferredChoices;

	choices.forEach(function(mode) {
		allowed.value(mode, modeLabel(mode));
	});
	allowed.rmempty = false;
	allowed.default = 'any';
	allowed.cfgvalue = function() {
		var value = networkValue(network, 'allowedmode');

		if (!value)
			return 'any';
		return allowedModeValid(value, supported, false) ?
			normalizeModeSet(value, false) : 'any';
	};
	allowed.validate = function(section_id, value) {
		if (!allowedModeValid(value, supported, true))
			return _('The selected allowed mode is not supported by this modem.');
		return true;
	};
	allowed.write = function(section_id, value) {
		if (network)
			setNetworkValue(network, 'allowedmode', value === 'any' ? null : value);
	};
	allowed.remove = function() {
		if (network)
			uci.unset('network', network['.name'], 'allowedmode');
	};

	preferred = section.option(form.ListValue, '_preferredmode',
		_('Preferred network technology'), _('A preference is valid only inside the allowed mode set.'));
	preferred.value('none', _('None'));
	preferredChoices = [];
	supported.forEach(function(pair) {
		if (modePairUsable(pair) && pair.preferred !== 'none' &&
			preferredChoices.indexOf(pair.preferred) === -1)
			preferredChoices.push(pair.preferred);
	});
	preferredChoices.forEach(function(mode) {
		preferred.value(mode, mode.toUpperCase());
	});
	preferred.rmempty = false;
	preferred.default = 'none';
	preferred.cfgvalue = function() {
		var value = networkValue(network, 'preferredmode');
		var allowedValue = networkValue(network, 'allowedmode');

		return value && allowedValue && modePairSupported(allowedValue, value, supported) ?
			normalizePreferredMode(value) : 'none';
	};
	preferred.validate = function(section_id, value) {
		var allowedValue = allowed.formvalue(section_id) || 'any';

		if (allowedValue === 'any' && value === 'none')
			return true;
		if (!modePairSupported(allowedValue, value, supported))
			return _('The selected allowed/preferred mode pair is not supported by this modem.');
		return true;
	};
	preferred.write = function(section_id, value) {
		if (network)
			setNetworkValue(network, 'preferredmode', value === 'none' ? null : value);
	};
	preferred.remove = function() {
		if (network)
			uci.unset('network', network['.name'], 'preferredmode');
	};

	ALLOWED_MODE_CHOICES.forEach(function(mode) {
		if (mode !== 'any' && mode.indexOf('|') !== -1 && choices.indexOf(mode) !== -1)
			preferred.depends('_allowedmode', mode);
	});

	if (!network || networkInfo.matches.length !== 1 || !supported.length ||
		(record && record.invalidModes)) {
		allowed.readonly = true;
		preferred.readonly = true;
	}
}

function addActions(map) {
	// UI-only controls must not depend on an existing UCI section.
	var section = map.section(form.TypedSection, 'actions', _('ModemManager actions'));
	var discover;
	var apply;

	section.anonymous = true;
	section.addremove = false;
	section.cfgsections = function() { return [ 'actions' ]; };
	section.parse = function() { return Promise.resolve(); };

	discover = section.option(form.Button, '_discover', null);
	discover.inputtitle = _('Discover ModemManager devices');
	discover.inputstyle = 'positive';
	discover.onclick = function() {
		return map.save().then(function() {
			return fs.exec_direct('/usr/libexec/mm-ui-bands', [ 'discover' ]);
		}).then(function() {
			window.location.reload();
		});
	};

	apply = section.option(form.Button, '_apply', null);
	apply.inputtitle = _('Apply saved modem settings');
	apply.inputstyle = 'button';
	apply.onclick = function() {
		return map.save().then(function() {
			return fs.exec_direct('/usr/libexec/mm-ui-bands', [ 'apply' ]);
		}).then(function() {
			ui.addNotification(null, E('p', {}, [ _('ModemManager settings applied.') ]), 'success');
		}, function(error) {
			ui.addNotification(null, E('p', {}, [
				_('ModemManager settings could not be applied: %s').format(error.message || error)
			]), 'error');
		});
	};
}

function ensureDiscoveredSections(records) {
	var configured = {};

	uci.sections('mmconfig', 'modem', function(section) {
		if (safeDevice(section.device))
			configured[section.device] = true;
	});

	records.forEach(function(record) {
		if (!configured[record.device]) {
			var sid = uci.add('mmconfig', 'modem');
			uci.set('mmconfig', sid, 'device', record.device);
			configured[record.device] = true;
		}
	});
}

return view.extend({
	load: function() {
		var modemTask = helper.getModems().then(function(modems) {
			return Array.isArray(modems) ? modems : [];
		}, function() {
			return [];
		});

		return Promise.all([ uci.load('mmconfig'), uci.load('network'), modemTask ]).then(function(data) {
			var records = [];

			data[2].forEach(function(entry) {
				var record = modemRecord(entry);
				if (record)
					records.push(record);
			});

			/* This keeps a page with an empty mmconfig useful after hotplug. */
			ensureDiscoveredSections(records);
			data[2] = records;
			return data;
		});
	},

	render: function(data) {
		var records = data[2];
		var byDevice = {};
		var map = new form.Map('mmconfig', _('ModemManager band and mode configuration'),
				_('Devices are discovered through ModemManager. A missing band list keeps the modem default policy; use Automatic to reset an explicit band restriction.') +
			'<br />' + _('Radio modes follow the allowedmode and preferredmode values of the matching Network interface.') +
			'<br />' + _('Saving a setting can briefly reconnect that one cellular interface.'));
		var sections;
		var style = document.createElement('style');

		style.textContent = this.getCSS();
		document.head.appendChild(style);

		records.forEach(function(record) {
			byDevice[record.device] = record;
		});
		addActions(map);

		sections = uci.sections('mmconfig', 'modem');
		sections.forEach(function(section, index) {
			var record = byDevice[section.device];
			var networkInfo = record ? findNetwork(record.device) : { matches: [], section: null };
				var named = map.section(form.NamedSection, section['.name'], 'modem', modemTitle(record, index));
			var device = named.option(form.HiddenValue, 'device', null);
			var info;
			var bands;
			var configuredBands;
			var selectedBands;

			named.anonymous = false;
			named.addremove = false;
			device.default = section.device || '';
			device.rmempty = false;
			device.readonly = true;

			if (!record) {
				info = named.option(form.DummyValue, '_status', null);
				info.rawhtml = true;
				info.default = '<div class="mmconfig-info-warning">' +
					escapeHtml(_('This saved device is not currently reported by ModemManager.')) +
					'</div>';
			} else {
				info = named.option(form.DummyValue, '_info', null);
				info.rawhtml = true;
					info.default = modemInfoHtml(record, networkInfo, index);

				addModeOptions(named, record, networkInfo);

				configuredBands = uci.get('mmconfig', section['.name'], 'bands');
				configuredBands = configuredBands == null ? null : asArray(configuredBands);
				if (configuredBands !== null && configuredBands.some(function(value) {
					return !contains(record.supportedBands, value);
				}))
					configuredBands = uniqueSafeValues(configuredBands).filter(function(value) {
						return contains(record.supportedBands, value);
					});

				selectedBands = configuredBands !== null ? configuredBands :
					record.currentBands.filter(function(value) {
						return contains(record.supportedBands, value);
					});

				bands = named.option(BandValue, 'bands', _('Bands'),
					_('Only bands reported as supported by ModemManager can be selected.'));
				bands.supportedBands = record.supportedBands;
				bands.initialBands = selectedBands;
				bands.configuredBands = configuredBands;
				bands.rmempty = true;
			}
		});

		if (!sections.length) {
				var empty = map.section(form.TypedSection, 'empty', _('ModemManager status'));
			var message;

				empty.anonymous = true;
				empty.addremove = false;
				empty.cfgsections = function() { return [ 'empty' ]; };
				empty.parse = function() { return Promise.resolve(); };
			message = empty.option(form.DummyValue, '_message', null);
			message.rawhtml = true;
			message.default = '<div class="mmconfig-info-warning">' +
				escapeHtml(records.length ?
					_('No modem configuration could be created from the ModemManager response.') :
					_('No ModemManager device is currently available. Connect a modem and use Discover ModemManager devices.')) +
				'</div>';
		}

		return map.render();
	},

	getCSS: function() {
		return [
			'.mmconfig-modem-info { border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 12px; margin: 8px 0 12px; }',
			'.mmconfig-info-row { display: flex; align-items: baseline; gap: 8px; margin: 3px 0; }',
			'.mmconfig-info-label { color: #718096; min-width: 8em; }',
			'.mmconfig-info-separator { color: #a0aec0; }',
			'.mmconfig-info-value { color: #2f855a; }',
				'.mmconfig-info-warning { color: #9b2c2c; }',
				'.mmconfig-bands { border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden; margin-top: 4px; }',
				'.mmconfig-band-any { display: flex; align-items: center; gap: 6px; padding: 9px 12px; border-bottom: 1px solid #e2e8f0; font-weight: 600; cursor: pointer; }',
				'.mmconfig-band-group + .mmconfig-band-group { border-top: 1px solid #e2e8f0; }',
			'.mmconfig-band-group-header { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 12px; }',
			'.mmconfig-band-group-title { font-size: .95em; }',
			'.mmconfig-band-actions { display: flex; gap: 4px; }',
			'.mmconfig-band-action { padding: 2px 8px; font-size: .85em; }',
			'.mmconfig-band-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(72px, 1fr)); gap: 6px; padding: 10px 12px 12px; }',
			'.mmconfig-band-item { display: flex; align-items: center; gap: 6px; min-height: 30px; padding: 4px 6px; border: 1px solid #e2e8f0; border-radius: 4px; cursor: pointer; user-select: none; }',
			'.mmconfig-band-item:hover { background: #f8fafc; }',
			'.mmconfig-band-label { font-weight: 500; }',
			'.mmconfig-bands-empty { padding: 10px 12px; border: 1px solid #e2e8f0; border-radius: 6px; color: #718096; }'
		].join('\n');
	}
});
