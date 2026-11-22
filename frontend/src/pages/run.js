import {datasetField, feedback, field} from '../components/common/fields.js';
import {empty, panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {STATUS} from '../constants/enums.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, link, p} from '../utils/dom.js';
import {date} from '../utils/format.js';

export async function runPage(route, refresh) {
  const {spec,datasets,batches} = workspace;
  const error = feedback();
  const submit = button(`执行${spec.run}`,{type:'submit',class:'primary','data-testid':'start-run'});
  const form = el('form',{class:'fields','data-testid':'run-form',
    onSubmit:handler(submit,error,async event=>{
      const data = new FormData(event.target);
      const item = await workspace.start({dataset_id:Number(data.get('dataset_id')), name:data.get('name')});
      location.hash = `#results/${item.id}`;
    })}, datasetField(datasets,route.id),
    field({key:'name',label:'批次名称',type:'string',max_length:120},`样本${spec.run}`),
    el('div',{class:'actions'},submit),error);
  const batchList = table([
    {label:'对账批次',render:item=>link(item.name,`#results/${item.id}`)},
    {label:'状态',render:item=>pill(STATUS[item.status],item.status)},
    {label:'建议确认',render:item=>item.confirmed_count},
    {label:'待核发票',render:item=>item.pending_invoice_count},
    {label:'时间',render:item=>date(item.created_at)},
  ],batches,{caption:'对账批次',empty:'首次计算后将在此显示后台状态。'});
  return el('div',{class:'two-col'}, el('div',{class:'wide-panel'},
    panel(spec.run,session.canWrite ? (datasets.length ? form : empty('请先导入单据。','#inputs','前往导入'))
      : p('只读角色可以查看历史对账批次。','empty')),
    panel('对账批次记录',batchList)),
    el('aside',{class:'sidebar-panel'},panel('配对口径',el('ul',{class:'method-list'},spec.methodology.map(text=>el('li',{},text))))));
}
