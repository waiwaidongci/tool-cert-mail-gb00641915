import {feedback, field} from '../components/common/fields.js';
import {empty, panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, link, p} from '../utils/dom.js';

function postForm(job, refresh) {
  const message = feedback();
  const submit = button('确认入账（仅方案一致整组）', {class:'primary', type:'submit', 'data-testid':'post-submit'});
  return el('form', {class:'fields', onSubmit:handler(submit, message, async event => {
    event.preventDefault();
    const data = new FormData(event.target);
    try {
      const outcome = await workspace.post(job.id, {note:data.get('note') || ''});
      message.textContent = outcome.posted.length
        ? `已入账 ${outcome.posted.length} 组：${outcome.posted.join('、')}${outcome.skipped.length ? `；跳过已入账 ${outcome.skipped.length} 组` : ''}`
        : `这些整组此前已入账，本次未重复认领（跳过 ${outcome.skipped.length} 组）`;
    } catch (error) {
      if (error.status === 409) {
        message.textContent = `${error.message} 请回到最新批次重新确认。`;
      } else throw error;
    }
    await refresh();
  })}, field({key:'note', label:'入账说明（可选）', type:'string', required:false, max_length:500}), submit, message);
}

export async function reviewPage(route, refresh) {
  const {spec, batches} = workspace;
  const completed = batches.filter(batch => batch.status === 'complete' && batch.confirmed_count > 0);
  const id = route.id || completed[0]?.id;
  if (!id) return panel(spec.pages[4], empty('暂无可入账的方案一致整组，请先完成一次对账计算。','#run',spec.pages[2]));
  const job = await workspace.getBatch(id);
  if (!job.result) return panel(job.name, empty('当前批次没有可复核结果。',`#results/${job.id}`,'查看批次状态'));
  const groups = job.result.confirmed_groups || [];
  const posted = await workspace.posted();
  const postedByKey = new Map(posted.map(item => [item.group_key, item]));
  const postedKeys = new Set(postedByKey.keys());
  const stillOpen = groups.filter(group => !postedKeys.has(group.group_key));
  const already = groups.filter(group => postedKeys.has(group.group_key));
  const groupTable = table([
    {key:'organization',label:'机构'}, {key:'period',label:'结算期'},
    {key:'invoice_id',label:'发票编号'}, {key:'note_codes',label:'认领验收单'},
    {key:'amount_yuan',label:'配平金额（元）'}, {key:'basis',label:'配对依据'},
  ], stillOpen, {caption:'待入账整组', empty:'本批建议整组均已入账。'});
  const doneTable = already.length && panel('本批已入账（不会重复认领）', table([
    {key:'invoice_id',label:'发票编号'}, {key:'note_codes',label:'验收单'},
    {key:'amount_yuan',label:'金额（元）'},
    {label:'入账人',render:row=>postedByKey.get(row.group_key)?.author || '—'},
  ], already, {caption:'已入账'}));
  return el('div', {class:'two-col'},
    panel(job.name, p(job.result.headline,'intro-copy'),
      link('查看完整配对证据与待核原因',`#results/${id}`,{class:'quiet'}),
      groupTable, doneTable,
      stillOpen.length ? (session.canReview ? postForm(job,refresh) : p('等待复核主管确认入账。','subtle'))
        : pill('本批整组已全部入账','accepted')),
    panel('可入账批次', el('ul',{class:'method-list'}, completed.map(batch =>
      el('li',{}, link(batch.name,`#review/${batch.id}`), ' ', pill(`${batch.confirmed_count} 组`,batch.status))))));
}
