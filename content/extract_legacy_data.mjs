// One-time fixture extraction from the retained visual reference; never run by Django.
import fs from 'node:fs';

const materialSource = fs.readFileSync('src/materials.js', 'utf8')
  .replace(/^import[^\n]*\n/m, '').replaceAll('export const ', 'const ');
const materialData = new Function('assetPath', `${materialSource}; return {documents, topics}`)((value) => value);
const appSource = fs.readFileSync('src/App.jsx', 'utf8');
const contextSource = appSource.slice(appSource.indexOf('const contexts ='), appSource.indexOf('function Brand'));
const appData = new Function('assetPath', `${contextSource}; return {contexts, complianceDocuments}`)((value) => value);
fs.mkdirSync('content/data', {recursive: true});
fs.writeFileSync('content/data/legacy_content.json', JSON.stringify({...materialData, ...appData}, null, 2) + '\n');
