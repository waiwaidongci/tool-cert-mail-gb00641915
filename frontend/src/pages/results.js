import {plot} from '../components/common/chart.js';
import {feedback} from '../components/common/fields.js';
import {empty, metrics, panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {STATUS} from '../constants/enums.js';
import {handler, poll} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, h, link, p} from '../utils/dom.js';
import {date} from '../utils/format.js';

export async function results(route, refresh) {
  const {spec,batches} = workspace;
  const id = route.id || batches[0]?.id;
  if (!id) return panel(spec.pages[3],empty('还没有可查看的对账结果。','#run','前往计算'));
  const job = await workspace.getBatch(id);
  const message = feedback();
  const finished = item => item.status === 'complete' || item.status === 'failed';
  if (!finished(job)) {
    const original = location.hash;
    const status = el('p',{role:'status'},'后台正在配对，完成后会自动展示。');
    poll(()=>workspace.getBatch(id),finished,()=>location.hash===original)
      .then(result=>{if (result && status.isConnected && location.hash===original) refresh();
        else if(status.isConnected) status.textContent='仍在执行，请点击刷新检查。';})
      .catch(error=>{if(status.isConnected) status.textContent=error.message;});
    return panel(job.name,pill(STATUS[job.status],job.status),status,button('刷新',{class:'quiet',onClick:refresh}));
  }
  const download = button('下载对账 CSV',{class:'quiet','data-testid':'export',onClick:event=>
    handler(download,message,()=>workspace.download(`/batches/${job.id}/export`,`${spec.short_name}-${job.id}.csv`))(event)});
  const history = el('label',{class:'field run-picker',for:'run-picker'},el('span',{},'切换对账批次'),
    el('select',{id:'run-picker',onChange:event=>{location.hash=`#results/${event.target.value}`;}},
      (batches.some(item=>item.id===job.id) ? batches : [job,...batches]).map(item=>el('option',{value:item.id,selected:item.id===job.id},item.name))));
  const result = job.result;
  const content = result ? el('section',{class:'analysis','data-testid':'analysis-complete'},
    el('div',{class:'result-head'},p(job.name,'eyeline'),h(2,result.headline),p(result.note,'intro-copy'),
      el('div',{class:'actions'},pill(STATUS[job.status],job.status),download,
        session.canReview && result.ready && button('前往入账复核',{class:'quiet',onClick:()=>{location.hash=`#review/${job.id}`;}}),message)),
    metrics(result.metrics),
    result.charts.map(plot),
    result.tables.map(item=>panel(item.title,table(item.columns,item.rows,{caption:item.title,pageSize:10})))))
    : panel(job.name,pill(STATUS[job.status],job.status),p(job.error,'feedback'),link('返回调整批次',`#run/${job.dataset_id}`,{class:'quiet'}));
  return el('div',{},el('div',{class:'two-col'},el('div',{class:'wide-panel'},content),
    el('aside',{class:'sidebar-panel'},panel('批次来源',history,
      link(`数据批次 #${job.dataset_id}`,`#inputs/${job.dataset_id}`),p(date(job.finished_at),'subtle')),
      result && panel('后续操作',
        link('入账复核',`#review/${job.id}`,{class:'quiet'}),
        link('班报与待核',`#report`,{class:'quiet'})))));
}
