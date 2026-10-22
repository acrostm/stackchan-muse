"""Run actual portal JavaScript in a minimal DOM; no network or provider calls."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class Portal(unittest.TestCase):
    def test_network_selection_and_proxy_edit(self):
        script=re.search(r'<script>(.*?)</script>',(ROOT/'firmware/esp32/components/muse/sw_portal.html').read_text(),re.S).group(1)
        harness=r'''
const assert=require('node:assert/strict');
class Element {
 constructor(){this.value='';this.checked=false;this.handlers={};this.children=[];}
 addEventListener(name,fn){this.handlers[name]=fn;} replaceChildren(){this.children=[];}
 add(value){this.children.push(value);} append(value){this.children.push(value);} reset(){}
}
const elements=new Map();
const document={querySelector(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement(){return new Element();}};
let poll,hfStatus={supported:true,requested:false,enabled:false,state:'off'},hfPosts=[],failHF=false;
const window={addEventListener(){},setInterval(fn){poll=fn;return 1;},clearInterval(){}};const localStorage={getItem(){return null;},setItem(){}};
class Option {constructor(name,id){this.text=name;this.value=id;}}
class FormData {constructor(){return new Map(['ssid','password','sdk_token','api_key','app_id','access_key','speaker','proxy_host','proxy_port'].map(name=>[name,document.querySelector('#'+({'proxy_host':'proxy-host','proxy_port':'proxy-port'}[name]||name)).value]));}}
let posted;
async function fetch(path,options){
 if(path==='/handsfree'){
  const data=JSON.parse(options.body);assert.deepEqual(Object.keys(data),['enabled']);assert.equal(typeof data.enabled,'boolean');assert.equal(options.headers['X-Setup-Token'],'fixture');hfPosts.push(data.enabled);
  if(failHF)throw Error('connection lost');
  hfStatus={...hfStatus,requested:data.enabled,state:data.enabled?'starting':'stopping'};
  return {ok:true,json:async()=>hfStatus};
 }
 if(path==='/config'){posted=JSON.parse(options.body);return {ok:true,json:async()=>({ok:true})};}
 assert.equal(path,'/session');return {ok:true,json:async()=>({handsfree:hfStatus,csrf:'fixture',wifi_ssid:'home',wifi_saved:['home','phone'],sdk_configured:true,tts_configured:true,speaker:'zh_female_vv_uranus_bigtts',proxy_profiles:[{ssid:'home',host:'192.168.1.4',port:7897,enabled:true}]})};
}
(async()=>{
'''
        checks=r'''
assert(await settingsReady);
assert.equal($('#handsfree-panel').hidden,false);
await $('#handsfree-on').handlers.click();
assert.equal($('#handsfree-status').textContent,'正在加载本地模型…');
assert.equal($('#handsfree-on').disabled,true);
hfStatus={...hfStatus,enabled:true,state:'wake'};await poll();
assert.equal($('#handsfree-status').textContent,'等待唤醒词');
failHF=true;await $('#handsfree-off').handlers.click();
assert.match($('#handsfree-status').textContent,/状态未确认/);
assert.equal($('#handsfree-off').disabled,false);
failHF=false;await $('#handsfree-off').handlers.click();
assert.equal($('#handsfree-status').textContent,'正在停止…');
hfStatus={...hfStatus,enabled:false,state:'off'};await poll();
assert.equal($('#handsfree-status').textContent,'已关闭');
assert.deepEqual(hfPosts,[true,false,false]);
assert.equal($('#ssid').value,'home');assert.equal($('#proxy-enabled').checked,true);
$('#ssid').value='phone';$('#ssid').handlers.input();
assert.equal($('#proxy-enabled').checked,false);assert.equal($('#proxy-host').value,'');
$('#ssid').value='home';$('#ssid').handlers.input();
assert.equal($('#proxy-enabled').checked,true);assert.equal($('#proxy-host').value,'192.168.1.4');
$('#proxy-enabled').checked=false;$('#proxy-host').value='192.168.1.5';$('#proxy-port').value='1080';
await form.handlers.submit({preventDefault(){}});
assert.equal(posted.ssid,'home');assert.equal(posted.proxy_enabled,false);
assert.equal(posted.proxy_host,'192.168.1.5');assert.equal(posted.proxy_port,'1080');
assert.equal(posted.sdk_token,'');assert.equal(posted.api_key,'');assert.equal(posted.password,'');
$('#proxy-host').value='';await form.handlers.submit({preventDefault(){}});
assert.equal(posted.proxy_host,'');assert.equal(posted.proxy_enabled,false);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'portal.js';file.write_text(harness+script+checks)
            subprocess.run(['node',str(file)],check=True,timeout=15)
