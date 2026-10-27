const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../platform/frontend');
const vue = require(root + '/node_modules/vue');
const ts = require(root + '/node_modules/typescript');
const {parse, compileScript, compileTemplate} = require(root + '/node_modules/@vue/compiler-sfc');
function setup(file, props = {}) {
  const {descriptor} = parse(fs.readFileSync(root + '/src/' + file + '.vue', 'utf8'));
  const script = compileScript(descriptor, {id:file});
  const module = {exports:{}}; const events=[];
  new Function('require','module','exports',ts.transpileModule(script.content,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(name => name === 'vue' ? {...vue,onMounted(){},onBeforeUnmount(){}} : name === 'vue-router' ? {onBeforeRouteLeave(){}} : {},module,module.exports);
  return {state:module.exports.default.setup(props,{expose(){},emit:(...args)=>events.push(args)}),events,descriptor,script};
}
const {state:editor,events}=setup('components/EnvironmentVariablesEditor',{modelValue:'{"count":2,"empty":null}'});
editor.rows.value[0].text='not a number';editor.publish();
assert.equal(events.at(-1)[1],false);
const before=events.filter(event=>event[0]==='update:modelValue').length;
const target={value:'json'};editor.changeMode({target});
assert.equal(target.value,'rows');assert.equal(editor.mode.value,'rows');
assert.equal(editor.rows.value[0].text,'not a number');assert.match(editor.error.value,/先修复/);
assert.equal(events.filter(event=>event[0]==='update:modelValue').length,before);
editor.rows.value[0].text='3';editor.publish();target.value='json';editor.changeMode({target});
assert.equal(editor.mode.value,'json');
assert.deepEqual(JSON.parse(events.findLast(event=>event[0]==='update:modelValue')[1]),{count:3,empty:null});
// Verify the real compiled fieldset wraps every form control and follows all busy flags.
const {state:env,descriptor,script}=setup('pages/EnvironmentsPage');
const template=compileTemplate({source:descriptor.template.content,filename:'EnvironmentsPage.vue',id:'env',compilerOptions:{bindingMetadata:script.bindings}});
const moduleResult={exports:{}};
new Function('require','module','exports',ts.transpileModule(template.code,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(()=>({...vue,resolveComponent:name=>({name})}),moduleResult,moduleResult.exports);
const warn=console.warn;console.warn=()=>{};
try {
 for(const flag of ['saving','deleting','detailLoading']) {
  env[flag].value=true;
  const nodes=[];
  function visit(node) {if(Array.isArray(node)) return node.forEach(visit);if(!node||typeof node!=='object')return;nodes.push(node);if(Array.isArray(node.children))visit(node.children);else if(node.children&&typeof node.children==='object')if(node.type?.name!=='el-table-column')for(const slot of Object.values(node.children))if(typeof slot==='function')visit(slot());}
  visit(moduleResult.exports.render({},[],{},vue.proxyRefs(env),{},{}));
  const form=nodes.find(node=>node.type==='form');assert(form);
  const fieldset=form.children.find(node=>node.type==='fieldset');assert.equal(fieldset.props.disabled,true,flag);
  assert.equal(form.children.filter(node=>typeof node.type==='string').length,1,'all native form contents must be inside disabled fieldset');
  env[flag].value=false;
 }
} finally {console.warn=warn;}
console.log('PASS: invalid variable rows cannot switch mode or lose input; repaired rows switch; null stays null; all environment fields disabled during save/delete/read');
