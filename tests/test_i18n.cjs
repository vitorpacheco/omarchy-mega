const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'I18n.js'), 'utf8').replace(/^\.pragma library\s*/, '');
const i18n = vm.createContext({});
vm.runInContext(source, i18n);
for (const [setting, locale, expected] of [
  ['auto', 'pt_BR', 'pt'], ['auto', 'es-MX', 'es'], ['auto', 'en_GB', 'en'],
  ['auto', 'fr_FR', 'en'], ['auto', 'C', 'en'], ['auto', 'POSIX', 'en'],
  [undefined, '', 'en'], ['es', 'pt_BR', 'es'], ['en', 'es_ES', 'en'],
  ['pt-PT', 'en_US', 'pt'], ['invalid', 'pt_BR', 'en']
]) assert.equal(i18n.resolve(setting, locale), expected);
for (const [key, translations] of Object.entries(i18n.messages)) {
  assert.equal(translations.length, 3, key);
  for (const value of translations) {
    assert.ok(value.length > 0, key);
    assert.deepEqual(value.match(/%\d+/g) || [], key.match(/%\d+/g) || [], key);
  }
}
const spanishTransfers = i18n.messages['Transferências'][2];
i18n.messages['Transferências'][2] = '';
assert.equal(i18n.translate('es', 'Transferências'), 'Transfers');
i18n.messages['Transferências'][2] = spanishTransfers;
assert.equal(i18n.translate('en', 'Transferências'), 'Transfers');
assert.equal(i18n.translate('es', 'Sincronizações'), 'Sincronizaciones');
assert.equal(i18n.translate('unknown', 'Transferências'), 'Transfers');
assert.equal(i18n.translate('en', '%1 transferência', [1]), '1 transfer');
assert.equal(i18n.translate('es', '%1 transferências', [2]), '2 transferencias');
assert.equal(i18n.translate('en', '%1% de %2', [50, '1 MB']), '50% of 1 MB');
assert.equal(i18n.error('es', 'storage: Não foi possível executar o MEGAcmd.'), 'Almacenamiento: No se pudo ejecutar MEGAcmd.');
assert.equal(i18n.error('en', 'API_EACCESS: example.txt'), 'API_EACCESS: example.txt');
// Every plugin-authored backend diagnostic must have translations.
const backend = fs.readFileSync(path.join(root, 'bin/mega_bridge.py'), 'utf8');
for (const [, text] of backend.matchAll(/MegaError\("([^"]+)"\)/g)) assert.ok(i18n.messages[text], text);
// All explicit UI translation keys exist in the catalog.
for (const file of ['Widget.qml', 'Service.qml']) {
  const qml = fs.readFileSync(path.join(root, file), 'utf8');
  for (const [, key] of qml.matchAll(/(?:root\.)?tr\("([^"]+)"/g)) assert.ok(i18n.messages[key], `${file}: ${key}`);
}
console.log(`Localization checks passed: ${Object.keys(i18n.messages).length} messages, 3 languages.`);
