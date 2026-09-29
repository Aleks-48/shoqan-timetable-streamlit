export default function(component) {
  const {data,setStateValue,parentElement}=component;
  const node=parentElement.querySelector('span');
  const key='shoqan-day-profile-v1';
  if(data.mode==='blocked'){node.textContent=data.error;return;}
  try {
    const raw=localStorage.getItem(key);
    const saved=raw ? JSON.parse(raw) : null;
    if (data.mode==='load') {
      if(node.dataset.loaded!=='yes') {
        node.dataset.loaded='yes';
        setStateValue('loaded',{payload:saved?.payload||'',revision:saved?.revision||''});
      }
      return;
    }
    if ((saved?.revision||'')!==data.expected && saved?.revision!==data.revision) {
      const error='Данные изменены в другой вкладке. Скачайте свою копию и обновите страницу перед продолжением.';
      node.textContent=error;
      if(node.dataset.error!==error){node.dataset.error=error;setStateValue('receipt',{ok:false,error});}
      return;
    }
    const revision=data.enabled?data.revision:'';
    if(data.enabled) {
      if(saved?.revision!==data.revision) localStorage.setItem(key,JSON.stringify({revision:data.revision,payload:data.payload}));
      node.textContent='✓ Расписание и задания сохранены в этом браузере';
    } else {
      if(saved) localStorage.removeItem(key);
      node.textContent='Сохранение в браузере выключено. Перед закрытием скачайте копию.';
    }
    if(node.dataset.receipt!==revision+'|'+data.enabled) {
      node.dataset.receipt=revision+'|'+data.enabled;
      setStateValue('receipt',{ok:true,revision});
    }
  } catch(error) {
    const message='Браузер не разрешил сохранение или копия повреждена. Скачайте полную копию в настройках.';
    node.textContent=message;
    if(data.mode==='load' && node.dataset.loaded!=='yes') {
      node.dataset.loaded='yes';setStateValue('loaded',{error:message,revision:''});
    } else if(data.mode==='sync' && node.dataset.error!==message) {
      node.dataset.error=message;setStateValue('receipt',{ok:false,error:message});
    }
  }
}

