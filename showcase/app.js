'use strict';
const steps = [
  { owner:'第 1 步 · 帮你看要求', title:'先把比赛规则看明白。', description:'打开活动官网，找出要做什么、什么时候截止、需要准备什么材料。省掉你一页页复制粘贴。', detail:'它交回：带原文出处的规则清单。', rows:['要做什么','什么时候交','准备哪些材料'], foot:'规则有原文，后面才有依据。' },
  { owner:'第 2 步 · 帮你想个能做的题目', title:'把“想做点什么”，变成一个题目。', description:'结合规则和你给的方向，提出几个能做、能检验的小题目，再选一个继续。现阶段，主要做资料整理和对照指南。', detail:'它交回：选题、资料来源，以及怎样才算做完。', rows:['这件作品给谁看','去哪里找可靠资料','最后需要交出什么'], foot:'先把题目定清楚，再开始写。' },
  { owner:'第 3 步 · 把想法做出来', title:'从想法，写出能运行的程序。', description:'读取抓到的原文，生成整理资料的程序，再把内容做成带出处的网页。让一个题目变成可以打开看的东西。', detail:'它交回：程序、整理结果和引用出处。', rows:['整理资料的程序','有出处的内容','可以打开的作品页'], foot:'交回来的是实际文件和能打开的页面。' },
  { owner:'第 4 步 · 先试一遍，有错就改', title:'写完先跑，出错就改。', description:'把做好的程序真的运行一遍，看看有没有报错、内容能不能对上出处。再故意少给点资料，检查它会不会乱编。', detail:'它交回：测试结果；有问题就带着错误继续修。', rows:['程序能不能正常运行','引用能不能对上原文','缺了资料会不会乱编'], foot:'修不好就停止，不把失败当成功。' },
  { owner:'第 5 步 · 人能看懂，页面也能看清', title:'做出来，也得让人看得懂。', description:'先把难懂的术语换成大白话和生活比方，再用电脑和手机打开看看。字太挤、排版不好读，就改好以后再检查。', detail:'它交回：真实截图、问题记录和复验结果。', rows:['第一次看的人能不能懂','电脑和手机是否看得清','改完以后，再检查一遍'], foot:'比方也要核对原意，不能为了好懂讲错了。' },
  { owner:'第 6 步 · 替你整理材料、交作品', title:'材料准备好，获得授权后交作业。', description:'你登录并同意自动提交后，它把作品放到 Yours（作品分享页），试试别人能不能打开，再填报名表，保存截图和收件编号。', detail:'它交回：作品链接、过程截图和测试提交回执。', rows:['上传作品材料','检查访客能否打开','填表并保存收件回执'], foot:'后续测试投稿按约定加标记；收件不等于获奖。' }
];
const tabs = [...document.querySelectorAll('[data-step]')];
let current = 0, timer = null;
const play = document.getElementById('play-demo');
function stopDemo(){ if(timer) clearInterval(timer); timer=null; if(play){play.textContent='自动演示 ▶';play.setAttribute('aria-pressed','false');} }
function showStep(index, focus=false){
  current=index; const step=steps[index];
  tabs.forEach((tab,i)=>{tab.setAttribute('aria-selected',String(i===index));tab.tabIndex=i===index?0:-1;});
  document.getElementById('step-panel').setAttribute('aria-labelledby','step-'+index);
  for(const [id,key] of [['step-owner','owner'],['step-title','title'],['step-description','description'],['step-detail','detail'],['artifact-foot','foot']]) document.getElementById(id).textContent=step[key];
  const artifact=document.getElementById('artifact-content'); artifact.replaceChildren();
  step.rows.forEach((text,i)=>{const p=document.createElement('p'),number=document.createElement('span');number.textContent=String(i+1).padStart(2,'0');p.append(number,document.createTextNode(text));artifact.append(p);});
  document.getElementById('step-progress').textContent=`第 ${index+1} 步 / 共 6 步`;
  if(focus) tabs[index].focus();
}
if(tabs.length){
  tabs.forEach((tab,i)=>{tab.addEventListener('click',()=>{stopDemo();showStep(i);});tab.addEventListener('keydown',event=>{let index;if(event.key==='ArrowRight')index=(i+1)%steps.length;else if(event.key==='ArrowLeft')index=(i+steps.length-1)%steps.length;else if(event.key==='Home')index=0;else if(event.key==='End')index=steps.length-1;else return;event.preventDefault();stopDemo();showStep(index,true);});});
  play.setAttribute('aria-pressed','false');
  play.addEventListener('click',()=>{if(timer){stopDemo();return;}if(current===steps.length-1)showStep(0);play.textContent='暂停演示 Ⅱ';play.setAttribute('aria-pressed','true');timer=setInterval(()=>{if(current<steps.length-1)showStep(current+1);else stopDemo();},2300);});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stopDemo();});
}
let toastTimer;
function toast(message){const box=document.getElementById('toast');if(!box)return;box.textContent=message;box.classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>box.classList.remove('visible'),3500);}
document.querySelectorAll('[data-copy]').forEach(button=>button.addEventListener('click',async()=>{
  const value=button.dataset.copy;let copied=false;
  try{await navigator.clipboard.writeText(value);copied=true;}catch{
    const area=document.createElement('textarea');area.value=value;area.setAttribute('readonly','');area.style.position='fixed';area.style.opacity='0';document.body.append(area);area.select();try{copied=document.execCommand('copy');}catch{}area.remove();button.focus();
  }
  toast(copied?'访问码已复制：'+value:'访问码：'+value+'，请手动复制');
}));
const dialog=document.getElementById('preview-dialog');let lastPreview;
if(dialog){
  document.querySelectorAll('[data-preview]').forEach(button=>button.addEventListener('click',()=>{stopDemo();lastPreview=button;document.getElementById('preview-title').textContent=button.dataset.title;const img=document.getElementById('preview-image');img.src=button.dataset.preview;img.alt=button.dataset.title+'的实际运行截图';dialog.showModal();}));
  document.getElementById('close-preview').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
  dialog.addEventListener('close',()=>lastPreview?.focus());
}
